"""v2.9.0+ WBI 签名实现。

B 站自 2023-03 起对部分 Web 端 API 强制启用 WBI 鉴权，
包括"用户投稿视频"(`/x/space/wbi/arc/search`)、专栏、动态、搜索等。
所有带分页的查询接口必须在 query 中附带 `w_rid`（签名）和 `wts`（时间戳）。

签名三步：
  1. 从 `/x/web-interface/nav` 接口取 `img_key` + `sub_key`（每日刷新）
  2. 64 位固定重排表打乱 → `mixin_key`（32 位）
  3. 参数排序 + URL 编码 + 拼 mixin_key + MD5 → `w_rid`

参考：
  - https://github.com/Bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
  - https://socialsisteryi.github.io/bilibili-API-collect/docs/misc/sign/wbi.html
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests


# 64 位固定重排表（提取自 B 站 index.js，长期稳定）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# nav 接口（不需要 WBI 签名）
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"


def get_mixin_key(orig: str) -> str:
    """64 位重排 → 取前 32 位 → mixin_key。

    orig = img_key + sub_key（拼接后正好 64 位 hex）
    """
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB if i < len(orig))[:32]


def enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    """为请求参数添加 wbi 签名（w_rid + wts），**就地修改并返回**。

    关键步骤：
      1. 加 wts（当前 Unix 时间戳，整数）
      2. 按 key 字典序排序
      3. 过滤 value 中的 "!'()" 字符
      4. URL 编码（用 urllib.parse.urlencode）
      5. 拼上 mixin_key → MD5 → w_rid
    """
    mixin_key = get_mixin_key(img_key + sub_key)
    # 1. 加时间戳
    signed = dict(params)
    signed["wts"] = int(time.time())
    # 2. 按 key 排序
    signed = dict(sorted(signed.items()))
    # 3. 过滤特殊字符
    signed = {
        k: "".join(c for c in str(v) if c not in "!'()")
        for k, v in signed.items()
    }
    # 4. URL 编码（urllib 默认安全字母大写，符合 B 站期望）
    query = urllib.parse.urlencode(signed)
    # 5. MD5
    w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    signed["w_rid"] = w_rid
    return signed


def get_wbi_keys(
    sess: Optional[requests.Session] = None,
    timeout: float = 10.0,
) -> Tuple[str, str]:
    """从 nav 接口获取最新的 img_key + sub_key。

    返回：(img_key, sub_key)
    抛出：网络错误 / 解析错误时抛出异常（不静默失败）
    """
    s = sess or requests.Session()
    s.headers.setdefault("User-Agent", (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ))
    s.headers.setdefault("Referer", "https://www.bilibili.com/")

    r = s.get(NAV_URL, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"nav 接口返回错误：code={data.get('code')}, msg={data.get('message')}")

    wbi_img = data.get("data", {}).get("wbi_img", {})
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")
    if not img_url or not sub_url:
        raise RuntimeError("nav 接口响应缺少 wbi_img.img_url / sub_url（可能未登录？）")

    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


class WbiKeyCache:
    """缓存 img_key / sub_key，TTL 12 小时（小于 B 站 24h 刷新周期）。

    用法：
        cache = WbiKeyCache()
        img_key, sub_key = cache.get()  # 自动从 nav 拉取 / 复用缓存
    """

    DEFAULT_TTL_HOURS = 12.0
    CACHE_FILE = "data/wbi_keys.json"

    def __init__(
        self,
        sess: Optional[requests.Session] = None,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        cache_file: Optional[str] = None,
    ):
        self.sess = sess or requests.Session()
        self.ttl = timedelta(hours=ttl_hours)
        self.cache_file = Path(cache_file) if cache_file else Path(self.CACHE_FILE)
        self._img_key: Optional[str] = None
        self._sub_key: Optional[str] = None
        self._fetched_at: Optional[datetime] = None
        self._lock = threading.Lock()
        # 启动时尝试从文件加载
        self._load_from_file()

    def get(self, force_refresh: bool = False) -> Tuple[str, str]:
        """获取 wbi keys，必要时自动刷新。

        force_refresh=True 时忽略缓存，立即重新拉取。
        """
        with self._lock:
            now = datetime.now()
            if (
                not force_refresh
                and self._img_key
                and self._sub_key
                and self._fetched_at
                and (now - self._fetched_at) < self.ttl
            ):
                return self._img_key, self._sub_key
            # 拉新 key
            self._img_key, self._sub_key = get_wbi_keys(sess=self.sess)
            self._fetched_at = now
            self._save_to_file()
            return self._img_key, self._sub_key

    def invalidate(self) -> None:
        """手动让缓存失效（下次 get 重新拉取）。"""
        with self._lock:
            self._img_key = None
            self._sub_key = None
            self._fetched_at = None
            try:
                if self.cache_file.exists():
                    os.remove(self.cache_file)
            except OSError:
                pass

    def _load_from_file(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            fetched_at = datetime.fromisoformat(d["fetched_at"])
            if datetime.now() - fetched_at < self.ttl:
                self._img_key = d["img_key"]
                self._sub_key = d["sub_key"]
                self._fetched_at = fetched_at
        except Exception:
            # 损坏的缓存文件，忽略
            pass

    def _save_to_file(self) -> None:
        if self._img_key is None or self._sub_key is None or self._fetched_at is None:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({
                    "img_key": self._img_key,
                    "sub_key": self._sub_key,
                    "fetched_at": self._fetched_at.isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except OSError:
            # 缓存写失败不影响主流程
            pass

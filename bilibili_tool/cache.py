"""JSON 缓存 + 断点续传 + 字段新鲜度 + 跨 AV/BV 双索引。

设计哲学：
- B 站数据是"实时更新"的——抓一次播放量 1000，几小时后可能 5000
- 所以 cache 不能无限保留。需要按字段类型区分：
  * 静态字段（标题、UP主、发布时间、时长...）：视频发布后基本不变 → 永远 cache
  * 动态字段（播放、点赞、收藏...）：实时变 → 按 max_age 过期
  * 失败状态（not_found / failed）：视频失效不会"复活" → 永远 cache
- 跨 AV/BV 双索引：同一视频的 BV 号和 AV 号都指向同一条 cache 记录
  * 用户输入 "BV1xxx 170001"，第一次跑就只发 1 个请求，第二次更不用说

**v2.8.0 扩展**：Cache 类现在支持任意 dataclass（通过 record_class + key_func 注入），
用于 video / article / bangumi 三种独立 cache 文件。

使用：
  # 视频（默认行为，VideoInfo 专用 key_func）
  cache = Cache("data/cache.json")

  # 专栏（ArticleInfo 专用 key_func）
  cache = Cache("data/cache_article.json", record_class=ArticleInfo, key_func=article_keys)

  # 番剧（BangumiInfo 专用 key_func）
  cache = Cache("data/cache_bangumi.json", record_class=BangumiInfo, key_func=bangumi_keys)
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Type

from .models import ArticleInfo, BangumiInfo, VideoInfo


# ---- key_func 工厂 ----

def _video_keys(info: VideoInfo) -> List[str]:
    """VideoInfo 专用：跨 BV / AV / raw 三种 ID 索引。"""
    keys = []
    if info.bvid:
        keys.append(f"bv:{info.bvid}")
    if info.aid:
        keys.append(f"av:{info.aid}")
    if not keys and info.raw_input:
        keys.append(f"raw:{info.raw_input}")
    return keys


def _article_keys(info: ArticleInfo) -> List[str]:
    """ArticleInfo 专用：按 cv_id 索引。"""
    keys = []
    if info.cv_id:
        keys.append(f"cv:{info.cv_id}")
    if not keys and info.raw_input:
        keys.append(f"raw:{info.raw_input}")
    return keys


def _bangumi_keys(info: BangumiInfo) -> List[str]:
    """BangumiInfo 专用：按 ss_id / ep_id / raw 索引。

    同一条番剧的 ss + ep 都指向同一份（实际数据用 season_id 抓的）。
    """
    keys = []
    if info.season_id:
        keys.append(f"ss:{info.season_id}")
    if info.ep_id:
        keys.append(f"ep:{info.ep_id}")
    if not keys and info.raw_input:
        keys.append(f"raw:{info.raw_input}")
    return keys


# ---- 内容指纹（用于去重双索引 / 各种 ID） ----

def _video_fingerprint(d: dict) -> tuple:
    return (d.get("bvid") or "", d.get("aid"), d.get("raw_input") or "")


def _article_fingerprint(d: dict) -> tuple:
    return (d.get("cv_id") or "", d.get("raw_input") or "")


def _bangumi_fingerprint(d: dict) -> tuple:
    return (d.get("season_id"), d.get("ep_id"), d.get("raw_input") or "")


# ---- 向后兼容的旧 API（VideoInfo） ----

def _all_keys(info: VideoInfo) -> List[str]:
    """一条 VideoInfo 可能对应的所有 cache key。**保留旧 API 兼容**。"""
    return _video_keys(info)


def _primary_key(info: VideoInfo) -> str:
    """取第一个可用的 key。**保留旧 API 兼容**。"""
    keys = _all_keys(info)
    return keys[0] if keys else f"raw:{info.raw_input}"


def parse_duration(s: str) -> Optional[int]:
    """把 '1h' / '24h' / '7d' / '30m' / '0' / '' 解析为秒数。
    失败或 'never'/'always'/None 返回 None（表示不设过期）。
    """
    if s is None:
        return None
    s = s.strip().lower()
    if s in ("", "never", "always", "inf", "infinite", "-1"):
        return None
    if s in ("0", "no", "off"):
        return 0
    if not s:
        return None
    # 数字 + 单位
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if s[-1] in units:
        try:
            n = int(s[:-1])
            return n * units[s[-1]]
        except ValueError:
            return None
    # 纯数字按小时
    try:
        return int(s) * 3600
    except ValueError:
        return None


# ---- 通用 Cache 类（v2.8.0 重构） ----

class Cache:
    """通用 JSON 缓存，支持任意 dataclass。

    构造参数：
      path            缓存文件路径
      record_class    记录类（默认 VideoInfo，**保留旧行为**）
      key_func        计算缓存 key 的函数（默认 _video_keys）
      fingerprint     计算去重指纹的函数（默认 _video_fingerprint）
    """

    def __init__(
        self,
        path: str,
        *,
        record_class: Type = VideoInfo,
        key_func: Callable[[Any], List[str]] = None,
        fingerprint: Callable[[dict], tuple] = None,
    ):
        self.path = path
        self.record_class = record_class
        self.key_func = key_func or _video_keys
        self.fingerprint = fingerprint or _video_fingerprint

        self._data: Dict[str, dict] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self._data = loaded
            except (json.JSONDecodeError, OSError):
                # 损坏的缓存不要影响主流程，直接当空
                self._data = {}
        # 升级：旧 cache 是单 key 索引，遍历 records 重新 put 让它变成多索引
        self._upgrade_multi_index()

    def _all_keys(self, info) -> List[str]:
        """根据 key_func 计算一条记录的所有 key。"""
        return self.key_func(info)

    def _upgrade_multi_index(self) -> None:
        """检查每条记录的字段，把缺失的 key 补上。

        旧版本 cache 只按一种 key 索引（如只 bv:），新版本按多种 key 索引
        （如 bv: + av: / cv: / ss: + ep:）。
        """
        upgrades = []
        seen_payloads: set = set()
        for key, payload in list(self._data.items()):
            if id(payload) in seen_payloads:
                continue
            seen_payloads.add(id(payload))
            # 还原一条 record 对象，让 key_func 算所有应有的 key
            try:
                rec = self.record_class(**payload)
            except TypeError:
                continue
            wanted_keys = set(self.key_func(rec))
            for w in wanted_keys:
                if w not in self._data:
                    upgrades.append((w, payload))
        for w, payload in upgrades:
            self._data[w] = payload

    def has(self, info) -> bool:
        return any(k in self._data for k in self._all_keys(info))

    def get(self, info) -> Optional[Any]:
        """不管新鲜度，直接拿 cache 记录。尝试所有可能的 key。"""
        for k in self._all_keys(info):
            d = self._data.get(k)
            if d:
                return self.record_class(**d)
        return None

    def is_fresh(self, info, max_age_seconds) -> bool:
        """判断 cache 是否还在新鲜度内。

        max_age_seconds:
          None  / < 0  → 永远新鲜（信任 cache）
          0            → 永远不新鲜（不信任 cache）
          正数         → 抓取时间距今不超过这个秒数就算新鲜
        """
        if max_age_seconds is None or max_age_seconds < 0:
            return True
        if max_age_seconds == 0:
            return False
        if not info.fetched_at:
            return False
        try:
            fetched = datetime.strptime(info.fetched_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        age = (datetime.now() - fetched).total_seconds()
        return age <= max_age_seconds

    def get_fresh(self, info, max_age_seconds) -> Optional[Any]:
        """拿 cache 记录，但**只在新鲜度内**才返回；否则返回 None。

        失败/失效状态（status != "ok"）**永远算新鲜**。
        """
        cached = self.get(info)
        if not cached:
            return None
        if cached.status != "ok":
            return cached
        return cached if self.is_fresh(cached, max_age_seconds) else None

    def put(self, info) -> None:
        """存一条记录，**按所有可能的 key 同时索引**。"""
        keys = self._all_keys(info)
        if not keys:
            keys = [f"raw:{getattr(info, 'raw_input', '')}"]
        payload = info.to_dict() if hasattr(info, "to_dict") else dict(info.__dict__)
        for k in keys:
            self._data[k] = payload

    def all_records(self) -> List[Any]:
        """返回去重后的所有记录（多索引会指向同一份 dict，需要去重）。"""
        seen: set = set()
        out: List[Any] = []
        for d in self._data.values():
            fp = self.fingerprint(d)
            if fp in seen:
                continue
            seen.add(fp)
            try:
                out.append(self.record_class(**d))
            except TypeError:
                # 字段不匹配（升级中可能遇到）—— 跳过
                continue
        return out

    def unique_count(self) -> int:
        """返回去重后的实际记录数。"""
        return len(self.all_records())

    def save(self) -> None:
        """原子写入：先写临时文件再 rename，避免中断时损坏。"""
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        dir_ = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(prefix=".cache.", suffix=".json", dir=dir_)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def stats(self) -> Dict[str, int]:
        ok = sum(1 for d in self.all_records() if d.status == "ok")
        fail = sum(1 for d in self.all_records() if d.status in ("failed", "not_found"))
        return {"total": self.unique_count(), "ok": ok, "failed": fail}

"""B 站视频信息获取器：单条 / 批量，带错误分类与简单重试。"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, List, Optional, Callable

import requests

from .models import VideoInfo, explain_code
from .parser import ParsedItem


VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class BilibiliVideoFetcher:
    """B 站视频数据获取器（单线程 + 轻量重试）。"""

    # 不重试的 code（一旦确认是稿件不可见，再试也没用）
    NO_RETRY_CODES = {62002, 62004, 62012, -404, 404, 412}

    def __init__(
        self,
        *,
        sess: Optional[requests.Session] = None,
        max_retries: int = 2,
        timeout: float = 10.0,
    ):
        self.sess = sess or requests.Session()
        self.sess.headers.update(DEFAULT_HEADERS)
        self.max_retries = max_retries
        self.timeout = timeout

    # ---- 单条 ----
    def fetch(self, target) -> VideoInfo:
        """target 可以是 ParsedItem，或 aid(int/str)，或 bvid 字符串。"""
        info = self._build_skeleton(target)
        try:
            params = self._build_params(info)
            response = self.sess.get(
                VIEW_URL, params=params, timeout=self.timeout
            )
            data = response.json()
        except requests.RequestException as e:
            info.status = "failed"
            info.error = f"网络错误: {e}"
            return info
        except ValueError as e:
            info.status = "failed"
            info.error = f"响应非 JSON: {e}"
            return info

        code = data.get("code")
        info.api_code = code
        if code == 0 and data.get("data"):
            self._hydrate(info, data["data"])
        else:
            info.status = "not_found" if code in self.NO_RETRY_CODES else "failed"
            info.error = explain_code(code)
        return info

    def fetch_with_retry(self, target) -> VideoInfo:
        """带重试的 fetch：网络错误 / 非黑名单 code 才重试。"""
        last = self.fetch(target)
        for _ in range(self.max_retries):
            if last.is_ok or (last.api_code in self.NO_RETRY_CODES):
                break
            time.sleep(0.6)
            last = self.fetch(target)
        return last

    # ---- 批量 ----
    def batch_fetch(
        self,
        targets: Iterable,
        *,
        delay: float = 0.5,
        progress_cb: Optional[Callable[[int, int, VideoInfo], None]] = None,
    ) -> List[VideoInfo]:
        results: List[VideoInfo] = []
        items = list(targets)
        total = len(items)
        for i, t in enumerate(items, 1):
            info = self.fetch_with_retry(t)
            results.append(info)
            if progress_cb:
                progress_cb(i, total, info)
            if i < total and delay > 0:
                time.sleep(delay)
        return results

    # ---- 内部 ----
    def _build_skeleton(self, target) -> VideoInfo:
        if isinstance(target, ParsedItem):
            raw = target.raw or target.value
            kind = target.kind
            if target.kind == "av":
                return VideoInfo(raw_input=raw, input_kind=kind, aid=int(target.value))
            if target.kind == "bv":
                return VideoInfo(raw_input=raw, input_kind=kind, bvid=target.value)
            if target.kind == "short_url":
                return VideoInfo(raw_input=raw, input_kind=kind, status="failed", error="未解析的短链")
            return VideoInfo(raw_input=raw, input_kind=kind, status="failed", error="未知类型")
        # 字符串 / 数字
        s = str(target).strip()
        if not s:
            return VideoInfo(raw_input=s, status="failed", error="空输入")
        if s.isdigit():
            return VideoInfo(raw_input=s, input_kind="av", aid=int(s))
        if s.upper().startswith("BV"):
            return VideoInfo(raw_input=s, input_kind="bv", bvid=s)
        return VideoInfo(raw_input=s, input_kind="raw", status="failed", error="无法识别输入")

    def _build_params(self, info: VideoInfo) -> dict:
        if info.bvid:
            return {"bvid": info.bvid}
        if info.aid:
            return {"aid": info.aid}
        return {}

    def _hydrate(self, info: VideoInfo, vd: dict) -> None:
        info.status = "ok"
        info.aid = vd.get("aid", info.aid)
        info.bvid = vd.get("bvid", info.bvid)
        info.title = vd.get("title", "") or ""
        owner = vd.get("owner") or {}
        info.up_mid = owner.get("mid")
        info.up_name = owner.get("name", "") or ""
        info.tname = vd.get("tname", "") or ""

        stat = vd.get("stat") or {}
        info.view = stat.get("view")
        info.danmaku = stat.get("danmaku")
        info.reply = stat.get("reply")
        info.favorite = stat.get("favorite")
        info.coin = stat.get("coin")
        info.share = stat.get("share")
        info.like = stat.get("like")

        if vd.get("pubdate"):
            info.pubdate = datetime.fromtimestamp(vd["pubdate"]).strftime("%Y-%m-%d %H:%M:%S")
        if vd.get("ctime"):
            info.ctime = datetime.fromtimestamp(vd["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
        info.duration = vd.get("duration", 0) or 0

        desc = vd.get("desc", "") or ""
        info.desc = desc[:200] + ("..." if len(desc) > 200 else "")
        info.pic = vd.get("pic", "") or ""

        if info.bvid:
            info.url = f"https://www.bilibili.com/video/{info.bvid}"
        elif info.aid:
            info.url = f"https://www.bilibili.com/video/av{info.aid}"

        info.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

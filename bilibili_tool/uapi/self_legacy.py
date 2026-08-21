"""v2.10.0+ self-legacy provider: 旧端点 /x/space/arc/search（无 WBI，仅作最末位降级）。

旧端点没有 WBI 鉴权，但 B 站 2024 加了风控（-799 请求过于频繁）。
仅在 self-wbi + uapis.cn 都限流时尝试。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import requests

from .base import ArchiveProvider, UapiError, UapiRateLimitError
from ..author import AuthorVideoFetcher


class SelfLegacyProvider(ArchiveProvider):
    """自主旧端点调用 B 站（无 WBI，仅作最末位降级）。

    端点：/x/space/arc/search
    优点：与 self-wbi 同一套 fetcher，只是切换到 legacy 分支
    缺点：B 站风控严（-799），不适合作为主路径
    """

    name = "self-legacy"
    description = (
        "B 站旧端点 /x/space/arc/search（无 WBI，风控严，"
        "仅作最末位降级）"
    )
    requires_key = False
    key_hint = ""
    key_prefix = ""

    LEGACY_URL = "https://api.bilibili.com/x/space/arc/search"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        sess: Optional[requests.Session] = None,
        timeout: float = 10.0,
        interval_ms: int = 250,  # v3.0.9+ 翻页间隔
        **kwargs,
    ):
        super().__init__(api_key=None, interval_ms=interval_ms)
        self.sess = sess or requests.Session()
        self.sess.headers.setdefault("User-Agent", (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        self.timeout = timeout

    def fetch_author_archives(
        self,
        uid: int,
        *,
        days: Optional[int] = None,
        max_count: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ) -> List[dict]:
        """调旧端点 /x/space/arc/search（无 WBI 签名）。

        B 站风控严（-799），-799 转 UapiRateLimitError 让降级链能识别。
        """
        if not isinstance(uid, int) or uid <= 0:
            raise ValueError(f"uid 必须是正整数，got: {uid!r}")

        all_archives: List[dict] = []
        pn = 1
        ps = 50  # 旧端点最大 50
        while True:
            try:
                r = self.sess.get(
                    self.LEGACY_URL,
                    params={"mid": uid, "pn": pn, "ps": ps, "order": "pubdate"},
                    timeout=self.timeout,
                )
                data = r.json()
            except requests.Timeout as e:
                raise UapiError(f"self-legacy 超时：{e}") from e
            except Exception as e:
                raise UapiError(f"self-legacy 网络错误：{e}") from e

            # B 站风控：-799 / -403
            code = data.get("code")
            if code == -799:
                # 请求过于频繁
                raise UapiRateLimitError(
                    "B 站 -799 请求过于频繁（self-legacy）",
                )
            if code == -403:
                raise UapiError("B 站 -403 非法访问（self-legacy）")
            if code != 0:
                raise UapiError(
                    f"B 站 self-legacy 返回 code={code}: {data.get('message')}"
                )

            vlist = ((data.get("data") or {}).get("list") or {}).get("vlist") or []
            if not vlist:
                break

            for arc in vlist:
                ts = arc.get("created", 0) or 0
                if since and ts < int(since.timestamp()):
                    return all_archives
                if until and ts >= int(until.timestamp()):
                    continue
                # 字段归一化
                all_archives.append({
                    "aid": arc.get("aid"),
                    "bvid": arc.get("bvid"),
                    "title": arc.get("title"),
                    "pic": arc.get("pic"),
                    "duration": arc.get("length", ""),
                    "pubdate": ts,
                    "play": arc.get("play", 0),
                    "_source": "self-legacy",
                })
                if max_count and len(all_archives) >= max_count:
                    return all_archives

            if len(vlist) < ps:
                break
            pn += 1
            # v3.0.9+ 翻页节流：避开 B 站 -799（请求过于频繁）
            self._sleep_interval()

        # 客户端 keyword 过滤
        if keyword:
            keyword_lower = keyword.lower()
            all_archives = [
                a for a in all_archives
                if keyword_lower in (a.get("title", "") or "").lower()
            ]
            if max_count:
                all_archives = all_archives[:max_count]

        return all_archives

"""v2.10.0+ self-wbi provider: 适配现有的 AuthorVideoFetcher（WBI 签名主路径）。

直接复用 v2.9.1+ 已实现的 /x/space/wbi/arc/search + WBI 签名。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .base import ArchiveProvider
from ..author import AuthorVideoFetcher


class SelfWbiProvider(ArchiveProvider):
    """自主 WBI 签名调用 B 站官方接口。

    优点：
      - 免费 / 无第三方 / 隐私可控
      - 与 v2.9.1+ WBI 主路径一致
      - 不需要 API key

    缺点：
      - 受 B 站风控直接打击（HTTP 412 / -799）
      - 需要 wbi key 缓存（12h 自动刷新）

    失败时（限流 / -403 / -799）由调用方决定是否降级到其他 provider。
    """

    name = "self-wbi"
    description = (
        "自主 WBI 签名调用 B 站官方接口（v2.9.1+，免费，受 B 站风控）"
    )
    requires_key = False
    key_hint = ""
    key_prefix = ""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        fetcher: Optional[AuthorVideoFetcher] = None,
        interval_ms: int = 300,  # v3.0.9+ 翻页间隔（透传给 AuthorVideoFetcher）
        **kwargs,
    ):
        # self-wbi 不需要 key，忽略 api_key 参数
        super().__init__(api_key=None, interval_ms=interval_ms)
        # v3.0.9+：把 interval 透传给 AuthorVideoFetcher
        self.fetcher = fetcher or AuthorVideoFetcher(interval_ms=interval_ms)

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
        """调用 AuthorVideoFetcher 抓 UP 主投稿。

        AuthorVideoFetcher 已实现：
          - wbi 鉴权主端点
          - 限流时返回空列表（不会自动重试）

        **B 站限流（-799）转 UapiRateLimitError**，方便降级链识别。
        其他错误（HTTP 412 / 鉴权失败）转 UapiError。
        """
        from .base import UapiError, UapiRateLimitError  # 避免循环引用
        import requests

        try:
            archives = self.fetcher.fetch_author_archives_raw(
                uid=uid,
                days=days,
                max_count=max_count,
                since=since,
                until=until,
            )
        except requests.Timeout as e:
            raise UapiError(f"self-wbi 超时：{e}") from e
        except requests.RequestException as e:
            raise UapiError(f"self-wbi 网络错误：{e}") from e

        # 注：AuthorVideoFetcher 已把 -799 / 404 转成"返回空列表"
        # 所以这里的 archives 永远是干净的结果
        # 但若 fetcher 抛了 B 站业务错误（理论不会），会冒泡成 UapiError

        # 客户端 keyword 过滤（wbi 端点不原生支持）
        if keyword:
            keyword_lower = keyword.lower()
            archives = [
                a for a in archives
                if keyword_lower in (a.get("title", "") or "").lower()
            ]
            if max_count:
                archives = archives[:max_count]

        return archives

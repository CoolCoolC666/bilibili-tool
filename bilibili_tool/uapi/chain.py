"""v2.10.0+ 降级链: 按顺序尝试每个 provider, 限流时自动降级。

设计原则（用户要求"以限流为标识"）：
  - UapiRateLimitError → 自动降级到下一个 provider
  - 其他错误（UapiAuthError / UapiNotFoundError / UapiTimeoutError / UapiError）→ 直接抛
    （降级无意义：换 key 才行 / 资源不存在 / 换 provider 不会变快）

v3.0.5+：增加"数据完整性"检查
  - chain 抓取时记录实际抓到 N 条 + provider 报告的 total（如 uapis 字段）
  - 差距过大时，archives 加 `_completeness` 字段（"ok" / "partial" / "unknown"）
  - 提示前端展示
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from .base import ArchiveProvider, UapiRateLimitError


class AuthorArchiveChain:
    """降级链: 按顺序尝试每个 provider, 限流时降级。

    使用示例：

        chain = AuthorArchiveChain([
            SelfWbiProvider(),                              # 自主 WBI（默认）
            UapisCnProvider(api_key="uapi-xxxxxx"),         # uapis 兜底
            SelfLegacyProvider(),                            # 旧端点（最末位）
        ])

        archives = chain.fetch_author_archives(uid=483307278, days=30)
    """

    def __init__(self, providers: List[ArchiveProvider]):
        if not providers:
            raise ValueError("providers 不能为空")
        self.providers = providers

    def __repr__(self) -> str:
        names = [p.name for p in self.providers]
        return f"AuthorArchiveChain({' → '.join(names)})"

    def fetch_author_archives(
        self,
        uid: int,
        *,
        days: Optional[int] = None,
        max_count: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        keyword: Optional[str] = None,
        unlimited: bool = False,  # v3.0.5+：显式不限时间
    ) -> List[dict]:
        """按顺序尝试每个 provider。

        限流（UapiRateLimitError）触发降级。
        其他错误直接抛（不降级）。

        v3.0.5+：返回的 archives 列表中每个 dict 都有 `_source` 字段
        标明数据来源；第一个 dict 还有 `_completeness` / `_chain` 元信息
        （如: "_completeness": "ok"|"partial"|"unknown",
              "_chain": "self-wbi", "_provider_total": 262, "_actual_count": 71）
        """
        # v3.0.5+：unlimited=True 时把所有时间参数设为 None
        if unlimited:
            days = None
            since = None
            until = None

        last_rate_limit_err: Optional[UapiRateLimitError] = None
        tried_names: List[str] = []
        for provider in self.providers:
            tried_names.append(provider.name)
            try:
                archives = provider.fetch_author_archives(
                    uid=uid,
                    days=days,
                    max_count=max_count,
                    since=since,
                    until=until,
                    keyword=keyword,
                )
                # v3.0.5+：附加完整性元信息到第一条
                if archives:
                    completeness, meta = self._assess_completeness(provider, archives)
                    archives[0]["_completeness"] = completeness
                    archives[0]["_chain"] = provider.name
                    archives[0].update(meta)
                return archives
            except UapiRateLimitError as e:
                last_rate_limit_err = e
                continue
        if last_rate_limit_err:
            raise UapiRateLimitError(
                f"所有 provider 都限流（{tried_names}）：{last_rate_limit_err}",
            ) from last_rate_limit_err
        raise RuntimeError("AuthorArchiveChain: 未知状态")

    @staticmethod
    def _assess_completeness(provider, archives: List[dict]) -> tuple:
        """评估数据完整性。

        已知问题（2026-08-21 诊断）：
          - uapis.cn `/archives` 端点分页有 bug：total 字段在不同页之间不一致
            （pn=1: total=262, pn=2: total=71）
            → 实际拿到 71 条 / 262 条 = 27%（缺 73%）
          - self-wbi 端点：分页正常，但受 B 站风控（-799）影响

        评估策略：
          - provider.report_total: 从 provider 实例读（如有）
          - 实际拉取数 len(archives)
          - 差距 > 50% → "partial"（数据可能不完整）
          - 差距 < 10% → "ok"
          - 不知道 total → "unknown"
        """
        actual = len(archives)
        # provider 实例可能有 report_total 属性（v3.0.5+ 新增）
        reported = getattr(provider, "last_reported_total", None)
        meta = {
            "_actual_count": actual,
            "_provider_total": reported,
        }
        if reported is None or reported <= 0:
            return "unknown", meta
        ratio = actual / reported
        if ratio < 0.5:
            return "partial", meta
        if ratio >= 0.9:
            return "ok", meta
        return "partial", meta


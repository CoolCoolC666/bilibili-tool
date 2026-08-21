"""v2.10.0+ B 站 UP 主数据 provider 抽象层。

本包把"自主调用（WBI / 旧端点）"和"第三方 UAPI（uapis.cn 等）"
统一成同一个 `ArchiveProvider` 接口。

降级链（`AuthorArchiveChain`）按顺序尝试每个 provider，
**仅限流错误（UapiRateLimitError）触发降级**——其他错误（鉴权 /
资源不存在 / 网络）直接抛，因为换 provider 不能解决这些问题。

包含：
  - ArchiveProvider: 抽象基类
  - SelfWbiProvider: 自主 WBI 签名（默认主路径，免费，受 B 站风控）
  - SelfLegacyProvider: 旧端点（无 WBI，最末位降级）
  - UapisCnProvider: uapis.cn 5 端点（国产第三方兜底）
  - AuthorArchiveChain: 降级链
"""
from .base import (
    ArchiveProvider,
    UapiError,
    UapiRateLimitError,
    UapiAuthError,
    UapiNotFoundError,
    UapiTimeoutError,
)
from .self_wbi import SelfWbiProvider
from .self_legacy import SelfLegacyProvider
from .uapis_cn import UapisCnProvider
from .chain import AuthorArchiveChain


__all__ = [
    # 抽象 + 异常
    "ArchiveProvider",
    "UapiError",
    "UapiRateLimitError",
    "UapiAuthError",
    "UapiNotFoundError",
    "UapiTimeoutError",
    # Provider 实现
    "SelfWbiProvider",
    "SelfLegacyProvider",
    "UapisCnProvider",
    # 降级链
    "AuthorArchiveChain",
]

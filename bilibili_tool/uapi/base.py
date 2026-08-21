"""v2.10.0+ B 站 UP 主数据 provider 抽象基类。

设计目标：
  1. 把"自主调用（WBI / 旧端点）"和"第三方 UAPI（uapis.cn 等）"统一成同一个接口
  2. 限流时支持自动降级（见 chain.py）
  3. 错误类型分层（限流 vs 鉴权 vs 资源不存在 vs 网络）—— 只有限流触发降级

使用示例：

    from bilibili_tool.uapi import (
        SelfWbiProvider, UapisCnProvider, AuthorArchiveChain,
    )

    chain = AuthorArchiveChain([
        SelfWbiProvider(),                              # 自主 WBI（默认）
        UapisCnProvider(api_key="uapi-xxxxxx"),         # uapis 兜底
    ])

    archives = chain.fetch_author_archives(
        uid=483307278,
        days=30,
        max_count=20,
    )
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional


# ============================================================================
# 异常分层
# ============================================================================

class UapiError(Exception):
    """UAPI 调用错误的基类。

    v3.1.0+ 增强：
      - 支持 `details` 字段（uapis FAQ Q32 结构 1/2 的额外信息）
      - 支持 `docs` 字段（结构 3 跳转链接，如积分耗尽时返回 upgrade / usage URL）
    """
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[dict] = None,
        docs: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.details = details
        self.docs = docs


class UapiRateLimitError(UapiError):
    """限流错误。**触发降级链**：自动切换到下一个 provider。

    uapis.cn 文档：HTTP 429；自身错误码 RATE_LIMITED。
    B 站：-799 请求过于频繁。
    """
    pass


class UapiAuthError(UapiError):
    """鉴权错误。**不触发降级**（换 key 才行，不换 provider）。

    uapis.cn 文档：HTTP 401；错误码 UNAUTHORIZED。
    """
    pass


class UapiNotFoundError(UapiError):
    """资源不存在。**不触发降级**（资源不在所有 provider 上都不存在）。

    uapis.cn 文档：HTTP 404；错误码 NOT_FOUND。
    """
    pass


class UapiTimeoutError(UapiError):
    """超时错误。**不触发降级**（降级可能更慢）。

    requests.exceptions.Timeout 包装。
    """
    pass


# ============================================================================
# 抽象基类
# ============================================================================

class ArchiveProvider(ABC):
    """UP 主投稿列表的 provider 基类。

    子类必须实现：
      - fetch_author_archives: 核心方法

    子类可重写：
      - health_check: 健康检查（默认用 fetch_author_archives + max_count=1 试探）
      - fetch_user_info / fetch_video_info / fetch_video_replies / fetch_live_room:
        仅当子类支持时才实现；不实现则抛 NotImplementedError。
    """

    # ---- 元信息（子类重写） ----
    name: str = "base"
    description: str = ""
    requires_key: bool = True
    key_hint: str = ""      # 输入框 placeholder
    key_prefix: str = ""    # 密钥前缀校验（如 "uapi-"）

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        interval_ms: int = 250,
        **kwargs,
    ):
        """provider 通用初始化。

        参数：
          api_key: 第三方 API 密钥（uapis 等需要；self-wbi/self-legacy 忽略）
          interval_ms: 翻页请求间隔（毫秒），用于节流避开上游 429 / -799
            - v3.0.9+ 引入，由 Web 端"数据源设置 → 请求间隔"控制
            - 默认 250ms = 4 QPS，对应 uapis.cn 访客档位
            - uapis FAQ Q13 推荐档：访客 4 QPS / 登录 7 QPS / 入门 10 / 标准 20 / 专业 30
            - uapis FAQ Q15 推荐：平均每分钟不超过 40 次（≥ 1500ms/次，保守值）
            - 不影响单次端点调用（userinfo / videoinfo / replies / liveroom）
        """
        self.api_key = api_key
        self.interval_ms = max(0, int(interval_ms))
        # 子类可重写 __init__ 干更多事

    # ---- 核心：抓 UP 主投稿 ----

    @abstractmethod
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
        """按 UP 主 UID 抓投稿视频。

        参数：
          uid: B 站 UP 主 mid（数字 ID）
          days: 最近 N 天（None=不限制）
          max_count: 最多抓多少条（None=不限制）
          since: 起始日期（含），datetime（naive 视为北京时间）
          until: 结束日期（不含），datetime
          keyword: 标题关键词过滤（uapis.cn 支持，旧端点不支持）

        返回：archive 字典列表（至少含 bvid / aid / title / pubdate / duration / play）
        抛出：UapiError 子类
        """
        ...

    # ---- 可选：抓其他元数据 ----

    def fetch_user_info(self, uid: int) -> dict:
        """抓 UP 主用户信息。子类未支持则抛 NotImplementedError。"""
        raise NotImplementedError(f"{self.name} 不支持 fetch_user_info")

    def fetch_video_info(
        self,
        aid: Optional[int] = None,
        bvid: Optional[str] = None,
    ) -> dict:
        """抓单个视频详情。子类未支持则抛 NotImplementedError。"""
        raise NotImplementedError(f"{self.name} 不支持 fetch_video_info")

    def fetch_video_replies(
        self,
        oid: int,
        *,
        sort: str = "time",
        ps: int = 20,
        pn: int = 1,
    ) -> dict:
        """抓视频评论。子类未支持则抛 NotImplementedError。"""
        raise NotImplementedError(f"{self.name} 不支持 fetch_video_replies")

    def fetch_live_room(
        self,
        *,
        mid: Optional[int] = None,
        room_id: Optional[int] = None,
    ) -> dict:
        """抓直播间信息。子类未支持则抛 NotImplementedError。"""
        raise NotImplementedError(f"{self.name} 不支持 fetch_live_room")

    # ---- 健康检查 ----

    def health_check(self) -> bool:
        """轻量级健康检查：抓 1 条测试 UP 主（bilibili 官方 UID 2 = bishi）。

        默认实现调用 fetch_author_archives(max_count=1)。
        子类可重写为更轻量的调用（如 fetch_user_info(2)）。
        """
        try:
            self.fetch_author_archives(2, max_count=1)
            return True
        except Exception:
            return False

    # ---- 内部 ----

    def _sleep_interval(self) -> None:
        """v3.0.9+ 翻页节流：按 `interval_ms` sleep。

        设计原则：
          - 只用于"翻页之间"（uapis `/archives` pn 递增、self-legacy pn 递增、self-wbi pn 递增）
          - 单次端点调用（userinfo / videoinfo 等）不需要 sleep
          - interval_ms = 0 → 不 sleep（向后兼容旧硬编码行为）
        """
        if self.interval_ms > 0:
            time.sleep(self.interval_ms / 1000.0)

    def _validate_key(self) -> None:
        """验证密钥格式（不调远程）。子类 __init__ 末尾调用。

        设计原则：
          - requires_key=True + 无 key → 抛 UapiAuthError
          - requires_key=False + 无 key → 静默通过（访客模式合法）
          - 有 key → 校验 key_prefix
        """
        if not self.requires_key:
            # 不强制要求 key（支持访客模式），但如果有 key 就校验格式
            if self.api_key and self.key_prefix:
                if not self.api_key.startswith(self.key_prefix):
                    raise UapiAuthError(
                        f"{self.name} 的 key 必须以 {self.key_prefix!r} 开头，"
                        f"got: {self.api_key[:8]!r}..."
                    )
            return
        if not self.api_key:
            raise UapiAuthError(
                f"{self.name} 需要 API key（{self.key_hint or '请查官方文档'}）"
            )
        if self.key_prefix and not self.api_key.startswith(self.key_prefix):
            raise UapiAuthError(
                f"{self.name} 的 key 必须以 {self.key_prefix!r} 开头，"
                f"got: {self.api_key[:8]!r}..."
            )

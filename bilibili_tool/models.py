"""数据模型定义。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# B 站状态码语义
CODE_MESSAGES = {
    0: "成功",
    -101: "未登录",
    -102: "被封禁",
    -103: "风控校验失败",
    -104: "撞限流",
    -111: "csrf 校验失败",
    -400: "请求错误",
    -403: "权限不足",
    -404: "视频不存在",
    62002: "稿件不可见",
    62004: "稿件审核中",
    62012: "仅自己可见",
    412: "请求被拦截（失效/下架）",
}


def explain_code(code: Optional[int]) -> str:
    if code is None:
        return "无响应"
    return CODE_MESSAGES.get(code, f"未知错误码 {code}")


@dataclass
class VideoInfo:
    """单条视频的统一数据结构。"""

    # 用户提供的原始输入
    raw_input: str = ""
    input_kind: str = ""  # av / bv / url / short_url

    # B 站 ID（优先 BV，便于直接拼链接）
    aid: Optional[int] = None
    bvid: str = ""

    # 基础信息
    title: str = ""
    up_mid: Optional[int] = None
    up_name: str = ""
    tname: str = ""  # 分区

    # 统计
    view: Optional[int] = None
    danmaku: Optional[int] = None
    reply: Optional[int] = None
    favorite: Optional[int] = None
    coin: Optional[int] = None
    share: Optional[int] = None
    like: Optional[int] = None

    # 时间
    pubdate: str = ""
    ctime: str = ""
    duration: int = 0  # 秒

    # 描述 / 封面
    desc: str = ""
    pic: str = ""

    # 链接
    url: str = ""

    # 状态
    status: str = "pending"  # ok / failed / not_found
    api_code: Optional[int] = None
    error: str = ""

    fetched_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    @property
    def display_title(self) -> str:
        return self.title or f"({self.bvid or self.aid or self.raw_input})"


@dataclass
class FetchSummary:
    """一次批量抓取的统计。"""
    total: int = 0
    ok: int = 0
    failed: int = 0
    from_cache: int = 0
    elapsed_sec: float = 0.0
    started_at: str = ""
    finished_at: str = ""

    def as_text(self) -> str:
        return (
            f"总输入 {self.total} | 成功 {self.ok} | 失败 {self.failed} "
            f"| 缓存命中 {self.from_cache} | 耗时 {self.elapsed_sec:.1f}s"
        )

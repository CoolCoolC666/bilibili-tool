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
    -509: "请求过于频繁（专栏/番剧 API 限流，等几分钟再试）",
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
class ArticleInfo:
    """单条专栏（read/cv{数字} 旧版 + opus/{数字} 新版）的统一数据结构。

    API 端点：
      - /x/article/view?id={cv_id}        （cv_id 是数字 ID；opus_id 数字直接当 cv 用）

    注意：抓正文需要登录 cookie，本版本只抓摘要/标题/作者/统计等公开字段。
    """

    # 用户提供的原始输入
    raw_input: str = ""
    input_kind: str = ""  # "article"

    # B 站专栏 ID（CV = column view 缩写）
    cv_id: str = ""

    # 基础信息
    title: str = ""
    author_mid: Optional[int] = None
    author_name: str = ""

    # 统计（动态字段，1h 内有效）
    view: Optional[int] = None
    like: Optional[int] = None
    favorite: Optional[int] = None
    coin: Optional[int] = None
    share: Optional[int] = None
    reply: Optional[int] = None

    # 字数（静态字段）
    words: Optional[int] = None

    # 时间
    ctime: str = ""
    pubtime: str = ""

    # 描述 / 封面
    summary: str = ""  # 摘要（静态字段）
    banner: str = ""   # 封面图 URL
    pic: str = ""      # 备用封面（旧版字段名）

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
        return self.title or f"(cv{self.cv_id or self.raw_input})"


@dataclass
class BangumiInfo:
    """单条番剧（ss{数字} 整季 + ep{数字} 单集）的统一数据结构。

    API 端点：
      - 整季：/pgc/view/pc/season?season_id={ss_id}
      - 单集：/pgc/view/pc/season?ep_id={ep_id}        （返回时也会带 season_id）

    为简化，**统一返回整季的元数据**（title/cover/desc/评分/总集数），
    ep_id 形式会自动取到 season_id 再查。
    """

    # 用户提供的原始输入
    raw_input: str = ""
    input_kind: str = ""  # "bangumi_ss" | "bangumi_ep"

    # B 站番剧 ID
    season_id: Optional[int] = None   # ss
    ep_id: Optional[int] = None       # ep

    # 基础信息
    title: str = ""
    alias: str = ""        # 别名
    type_name: str = ""    # 类型（如"国创"/"动画"）

    # 统计（动态字段）
    view: Optional[int] = None      # 整季播放
    favorite: Optional[int] = None
    coins: Optional[int] = None
    danmaku: Optional[int] = None
    reply: Optional[int] = None
    share: Optional[int] = None
    like: Optional[int] = None

    # 评分（静态字段）
    rating_score: Optional[float] = None
    rating_count: Optional[int] = None

    # 元数据
    total_ep: Optional[int] = None   # 总集数
    status_text: str = ""            # 状态文字（"已完结"/"连载中"）
    publish_date: str = ""           # 上线日期

    # 描述 / 封面
    desc: str = ""
    cover: str = ""

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
        if self.title:
            return self.title
        if self.season_id:
            return f"(ss{self.season_id})"
        if self.ep_id:
            return f"(ep{self.ep_id})"
        return f"({self.raw_input})"


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

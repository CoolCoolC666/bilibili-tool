"""v2.10.0+ uapis.cn 第三方 B 站聚合 API 实现（5 端点）。

官方文档：https://uapis.cn/docs
鉴权：Authorization: Bearer uapi-xxx
基址：https://uapis.cn/api/v1

5 个端点：
  1. GET /social/bilibili/archives    — UP 主投稿列表（核心）
  2. GET /social/bilibili/userinfo    — UP 主信息
  3. GET /social/bilibili/videoinfo   — 单视频详情
  4. GET /social/bilibili/replies     — 视频评论
  5. GET /social/bilibili/liveroom    — 直播间

密钥来源（按优先级）：
  1. 显式传入 api_key
  2. 环境变量 UAPIS_CN_API_KEY
  3. 都不传 → 抛 UapiAuthError
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

import requests

from .base import (
    ArchiveProvider,
    UapiError,
    UapiRateLimitError,
    UapiAuthError,
    UapiNotFoundError,
    UapiTimeoutError,
)


# UTC+8 北京时间
TZ_BJ = timezone(timedelta(hours=8))


class UapisCnProvider(ArchiveProvider):
    """uapis.cn B 站第三方聚合 API。

    支持三种调用模式（按优先级）：
      1. **登录用户模式**：传 `api_key`（`uapi-` 开头）—— 3500 积分/月，7 QPS
      2. **访客模式**：不传 `api_key`（按 IP 算）—— 1500 积分/月，4 QPS
      3. **环境变量**：环境变量 `UAPIS_CN_API_KEY` 已设则等同登录模式

    优点：
      - 国产 + 中文文档 + 中文客服
      - 穷鬼友好：访客免费（1500 积分/月）+ 登录 3500 积分/月 + 资源包 ¥4.9 起
      - 5 个端点覆盖本项目所有需求

    缺点：
      - 数据过第三方服务器（隐私 + 数据主权）
      - 15 分钟缓存（最新视频可能滞后；命中缓存按**半价向下取整**——
        B 站 5 端点 4 积分 → 命中缓存扣 2 积分；其他 1 积分档 → 0 积分）
      - 第三方服务有倒闭风险
      - 访客额度按 IP 算，切网络会重新计（不稳定）
    """

    name = "uapis.cn"
    description = (
        "国产第三方 B 站聚合 API（中文文档，访客 1500 积分/月 4 QPS，"
        "登录 3500 积分/月 7 QPS，5 端点 × 4 积分/次，15 分钟缓存）"
    )
    requires_key = False  # 访客模式不需要 key
    key_hint = "可选：Bearer uapi-xxxxxxxx（从 https://uapis.cn 注册获取）。留空按访客模式（1500 积分/月，4 QPS）"
    key_prefix = "uapi-"

    BASE_URL = "https://uapis.cn/api/v1"
    # 积分消耗参考（2026-08-21 FAQ 调研，5 个 B 站端点都是 4 积分/AI 服务档）
    CREDIT_COST = {
        "archives": 4,    # UP 主投稿（AI 服务 4 积分）
        "userinfo": 4,    # UP 主信息
        "videoinfo": 4,   # 单视频详情
        "replies": 4,     # 视频评论
        "liveroom": 4,    # 直播间
    }
    # 缓存时间（参考 FAQ Q10）
    CACHE_TTL = {
        "archives": "15 分钟",
        "userinfo": "15 分钟",
        "videoinfo": "15 分钟",
        "replies": "5 分钟",
        "liveroom": "2 分钟",
    }
    # 模式限制
    RATE_LIMIT = {
        "visitor": "4 QPS / 1500 积分/月",
        "logged_in": "7 QPS / 3500 积分/月",
        "starter_pack": "10 QPS",
        "standard_pack": "20 QPS",
        "pro_pack": "30 QPS",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        sess: Optional[requests.Session] = None,
        timeout: float = 10.0,
        interval_ms: int = 250,  # v3.0.9+ 翻页间隔
        disable_cache: bool = False,  # v3.1.0+ 绕过 15 分钟服务端缓存（Q12）
    ):
        # 先存 key（优先级 1: 传入；优先级 2: 环境变量）
        if not api_key:
            api_key = os.environ.get("UAPIS_CN_API_KEY")
        super().__init__(api_key=api_key, interval_ms=interval_ms)
        # 验证 key 格式（不调远程）—— 没 key 跳过（访客模式合法）
        self._validate_key()
        # v3.1.0+ Q12：disableCache 绕过服务端缓存
        # - TypeScript SDK 用 `disableCache: true`（驼峰），其他语言 SDK 不一定支持
        # - 非 SDK 推荐 URL 加 `_t=<timestamp>` 时间戳（FAQ Q12 原话）
        # - 服务端缓存键包含查询参数，所以加 _t 能让每次请求都是新键 → 绕过
        # - 用途：截断重试拿到陈旧缓存时强制重新查上游
        self.disable_cache = bool(disable_cache)

        self.sess = sess or requests.Session()
        self.sess.headers.setdefault("User-Agent", "bilibili_tool_v2/2.10.0 (uapis.cn client)")
        # 仅当有 key 时设置 Authorization 头（访客模式不携带）
        if self.api_key:
            self.sess.headers["Authorization"] = f"Bearer {self.api_key}"
        self.timeout = timeout
        # 标记模式（外部可读）
        self.is_visitor = not self.api_key

    @property
    def mode(self) -> str:
        """当前调用模式（'visitor' 无 key / 'logged_in' 有 key）。"""
        return "visitor" if self.is_visitor else "logged_in"

    # ---- 核心：UP 主投稿 ----

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
        """查询 B 站投稿。

        端点：GET /api/v1/social/bilibili/archives
        文档：https://uapis.cn/docs/api-reference/get-social-bilibili-archives
        单次消耗：5 积分

        时间过滤：客户端按 publish_time 倒序截断（uapis.cn 返回顺序已是按 pubdate 倒序）。
        """
        if not isinstance(uid, int) or uid <= 0:
            raise ValueError(f"uid 必须是正整数，got: {uid!r}")

        # 时间范围归一化
        start_ts = self._to_ts(since) if since else None
        end_ts = self._to_ts(until) if until else None
        if days and not since:
            now = datetime.now(TZ_BJ)
            start_ts = int((now - timedelta(days=days)).timestamp())

        all_videos: List[dict] = []
        pn = 1
        ps = 20  # uapis.cn 默认 + 上限
        last_reported_total = 0  # v3.0.5+：记录 uapis 报告的 total（用于评估完整性）
        while True:
            params: Dict[str, str] = {
                "mid": str(uid),
                "ps": str(ps),
                "pn": str(pn),
                "orderby": "pubdate",
            }
            if keyword:
                params["keywords"] = keyword

            data = self._request("/social/bilibili/archives", params)
            videos = data.get("videos", [])
            # 记录 total（不同页可能不一致——这是 uapis 已知 bug）
            if "total" in data:
                last_reported_total = data["total"]
            if not videos:
                break

            for v in videos:
                ts = v.get("publish_time", 0) or 0
                if start_ts and ts < start_ts:
                    # 倒序排列：遇到早于 since 的就到末尾了
                    self.last_reported_total = last_reported_total
                    return all_videos
                if end_ts and ts >= end_ts:
                    continue
                all_videos.append(self._normalize_archive(v))
                if max_count and len(all_videos) >= max_count:
                    self.last_reported_total = last_reported_total
                    return all_videos

            total = data.get("total", 0)
            if pn * ps >= total:
                break
            pn += 1
            # v3.0.9+ 翻页节流：按 interval_ms sleep（避开 429 / 月度额度过快耗尽）
            self._sleep_interval()
        # v3.0.5+：保存 last_reported_total 给 chain 评估完整性
        self.last_reported_total = last_reported_total
        return all_videos

    # ---- 端点 2：UP 主信息 ----

    def fetch_user_info(self, uid: int) -> dict:
        """查询 B 站用户公开信息。

        端点：GET /api/v1/social/bilibili/userinfo
        文档：https://uapis.cn/docs/api-reference/get-social-bilibili-userinfo
        单次消耗：4 积分（AI 服务档，B 站 5 端点同价）
        """
        if not isinstance(uid, int) or uid <= 0:
            raise ValueError(f"uid 必须是正整数，got: {uid!r}")
        return self._request("/social/bilibili/userinfo", {"uid": str(uid)})

    # ---- 端点 6（v3.1.0+）：剩余额度 ----

    def fetch_usage(self) -> dict:
        """查询 API 端点使用统计（**免费端点，0 积分**）。

        端点：GET /api/v1/status/usage
        文档：https://uapis.cn/docs/api-reference/get-status-usage
        作用：返回当前账号/访客的剩余积分、QPS、各端点调用统计

        v3.1.0+ 新增：用于 Web 端"数据源设置"卡显示剩余额度（Q26 推荐）。
        """
        return self._request("/status/usage", {})

    # ---- 端点 3：单视频详情 ----

    def fetch_video_info(
        self,
        aid: Optional[int] = None,
        bvid: Optional[str] = None,
    ) -> dict:
        """查询 B 站视频详细信息。

        端点：GET /api/v1/social/bilibili/videoinfo
        文档：https://uapis.cn/docs/api-reference/get-social-bilibili-videoinfo
        单次消耗：3 积分

        aid 与 bvid 任选其一。
        """
        if not aid and not bvid:
            raise ValueError("aid 或 bvid 至少要传一个")
        params: Dict[str, str] = {}
        if aid:
            params["aid"] = str(aid)
        if bvid:
            params["bvid"] = bvid
        return self._request("/social/bilibili/videoinfo", params)

    # ---- 端点 4：视频评论 ----

    def fetch_video_replies(
        self,
        oid: int,
        *,
        sort: str = "time",
        ps: int = 20,
        pn: int = 1,
    ) -> dict:
        """查询 B 站视频评论。

        端点：GET /api/v1/social/bilibili/replies
        文档：https://uapis.cn/docs/api-reference/get-social-bilibili-replies
        单次消耗：3 积分

        参数：
          oid: 视频 aid
          sort: 排序方式（0/time, 1/like, 2/reply, 3/hot）
          ps: 每页 1-20（默认 20）
          pn: 页码从 1 开始
        """
        if not isinstance(oid, int) or oid <= 0:
            raise ValueError(f"oid 必须是正整数，got: {oid!r}")
        if not 1 <= ps <= 20:
            raise ValueError(f"ps 必须在 1-20 之间，got: {ps}")
        return self._request("/social/bilibili/replies", {
            "oid": str(oid),
            "sort": sort,
            "ps": str(ps),
            "pn": str(pn),
        })

    # ---- 端点 5：直播间 ----

    def fetch_live_room(
        self,
        *,
        mid: Optional[int] = None,
        room_id: Optional[int] = None,
    ) -> dict:
        """查询 B 站直播间信息。

        端点：GET /api/v1/social/bilibili/liveroom
        文档：https://uapis.cn/docs/api-reference/get-social-bilibili-liveroom
        单次消耗：2 积分

        mid 与 room_id 任选其一。
        """
        if not mid and not room_id:
            raise ValueError("mid 或 room_id 至少要传一个")
        params: Dict[str, str] = {}
        if mid:
            params["mid"] = str(mid)
        if room_id:
            params["room_id"] = str(room_id)
        return self._request("/social/bilibili/liveroom", params)

    # ---- 内部 ----

    def _request(self, path: str, params: dict) -> dict:
        """发起 GET 请求并按状态码/错误码分类抛 UapiError 子类。

        v3.1.0+ Q12：当 disable_cache=True 时，给 params 加 `_t=<ms_timestamp>`
        让每次请求都是新缓存键，强制绕过 15 分钟服务端缓存。
        """
        url = f"{self.BASE_URL}{path}"
        # v3.1.0+ Q12 关闭缓存：URL 加时间戳戳（不影响业务参数）
        if self.disable_cache:
            import time
            params = dict(params)  # 拷贝避免修改上游调用方传入的 dict
            params["_t"] = str(int(time.time() * 1000))
        try:
            r = self.sess.get(url, params=params, timeout=self.timeout)
        except requests.Timeout as e:
            raise UapiTimeoutError(
                f"请求超时：{url}（{self.timeout}s）",
            ) from e
        except requests.RequestException as e:
            raise UapiError(
                f"网络错误：{url}（{type(e).__name__}）",
            ) from e

        # 解析 JSON
        try:
            data = r.json()
        except ValueError as e:
            raise UapiError(
                f"响应非 JSON（HTTP {r.status_code}）：{r.text[:200]}",
                status_code=r.status_code,
            ) from e

        # v3.1.0+ Q32 兼容：uapis.cn 错误响应有 4 种结构
        # 1. 标准: {"code": "INVALID_PARAMETER", "message": "...", "details": {...}}
        # 2. 简化: {"error": "INVALID_PARAMETER", "details": "..."}
        # 3. 积分不足: {"error": "INSUFFICIENT_CREDITS", "message": "...", "docs": {upgrade, usage}}
        # 4. 限流类: {"code": 429, "message": "Rate limit exceeded", "limit": 10}
        # 读取顺序：code（字符串） > error > message（FAQ Q32 推荐）
        def _extract_code_and_msg() -> tuple:
            code = data.get("code")
            if isinstance(code, str) and code:
                # 结构 1: code 是字符串（最常见）
                return code, data.get("message", code)
            err = data.get("error")
            if isinstance(err, str) and err:
                # 结构 2/3: 没有 code，用 error 字段
                msg = data.get("message") or data.get("details") or err
                return err, msg
            # 兜底：没有 code 也没有 error
            return None, data.get("message", "未知错误")
        code, msg = _extract_code_and_msg()
        # 额外字段（结构 3 有 docs 跳转链接；结构 4 有 limit）
        details = data.get("details")
        docs = data.get("docs")
        limit = data.get("limit")

        # 状态码 → 异常类型映射（参考 uapis.cn FAQ Q33 错误码表）
        if r.status_code == 200:
            return data
        if r.status_code == 400:
            # 参数错误 / INVALID_PARAMETER / UNSUPPORTED_FORMAT / FILE_REQUIRED / CONVERSION_FAILED
            raise UapiError(
                msg, status_code=400, code=code, details=details,
            )
        if r.status_code == 401:
            # 鉴权失败（key 错 / 过期 / UNAUTHORIZED / AUTHENTICATION_REQUIRED）
            raise UapiAuthError(
                msg, status_code=401, code=code, details=details,
            )
        if r.status_code == 402:
            # 账户积分耗尽（仅登录用户，Q16：访客不会遇到 402）
            raise UapiError(
                msg, status_code=402, code=code, details=details,
            )
        if r.status_code == 403:
            # 403 CORS_FORBIDDEN / IP not allowed / API path not allowed / ACCESS_DENIED
            raise UapiError(
                msg, status_code=403, code=code, details=details,
            )
        if r.status_code == 404:
            # 资源不存在（NOT_FOUND / AVATAR_NOT_FOUND / NO_TRACKING_DATA / NO_MATCH）
            raise UapiNotFoundError(
                msg, status_code=404, code=code, details=details,
            )
        if r.status_code == 413:
            # 请求体过大（REQUEST_ENTITY_TOO_LARGE）
            raise UapiError(
                msg, status_code=413, code=code, details=details,
            )
        if r.status_code == 429:
            # 限流：VISITOR_MONTHLY_QUOTA_EXHAUSTED / SERVICE_BUSY / RATE_LIMIT_EXCEEDED
            # **触发降级**（除非是 quota_exhausted 永久耗尽——这种情况再降级也浪费）
            err_cls = UapiError if (code == "VISITOR_MONTHLY_QUOTA_EXHAUSTED") else UapiRateLimitError
            raise err_cls(
                msg, status_code=429, code=code, details=details,
            )
        if r.status_code == 500:
            # INTERNAL_SERVER_ERROR
            raise UapiError(
                msg, status_code=500, code=code, details=details,
            )
        if r.status_code == 502:
            # 上游服务异常（API_ERROR / UPSTREAM_ERROR）
            raise UapiError(
                msg, status_code=502, code=code, details=details,
            )
        if r.status_code == 503:
            # SERVICE_UNAVAILABLE
            raise UapiError(
                msg, status_code=503, code=code, details=details,
            )
        if r.status_code == 504:
            # 网关超时 / UPSTREAM_TIMEOUT
            raise UapiError(
                msg, status_code=504, code=code, details=details,
            )
        # 其他 4xx / 5xx
        raise UapiError(
            f"HTTP {r.status_code}: {msg}",
            status_code=r.status_code, code=code, details=details,
        )

    def _normalize_archive(self, v: dict) -> dict:
        """把 uapis.cn 响应归一化成跟 B 站 vlist 一致的字段。

        方便上游 `author_list.py` / `author_detail.py` 复用。
        """
        return {
            "aid": v.get("aid"),
            "bvid": v.get("bvid"),
            "title": v.get("title"),
            "pic": v.get("cover"),
            "duration": v.get("duration"),
            "pubdate": v.get("publish_time"),
            "play": v.get("play_count"),
            "state": v.get("state"),
            "is_ugc_pay": v.get("is_ugc_pay"),
            "is_interactive": v.get("is_interactive"),
            # 元数据：标记数据来源（方便 debug + 降级追踪）
            "_source": "uapis.cn",
        }

    def _to_ts(self, dt: datetime) -> int:
        """datetime → B 站时间戳（秒）。naive 视为北京时间。"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_BJ)
        return int(dt.timestamp())

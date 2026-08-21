"""v2.9.0+ 按 UP 主 UID 抓取其投稿视频列表。

v2.9.0-alpha 尝试：
  1. 新端点 `/x/polymer/web-space/home/seek_arc` —— 已 404 下线
  2. 旧端点 `/x/space/arc/search` —— 已被 WBI 风控替代

v2.9.1+ 升级：
  1. **主端点** `/x/space/wbi/arc/search` —— B 站 2023-03 起的官方接口，需要 WBI 签名
  2. **降级** 第三方 / 旧端点（保留兼容）

WBI 签名机制见 `wbi.py`。

输出：List[ParsedItem]（kind=bv/av），可无缝接入现有的抓取流水线
（缓存 / 视频元数据 / 去重 / 导出）。
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

import requests

from .parser import ParsedItem
from .models import VideoInfo
from .wbi import WbiKeyCache, enc_wbi


# UTC+8 北京时间
TZ_BJ = timezone(timedelta(hours=8))


class AuthorVideoFetcher:
    """按 UP 主 UID 抓取其投稿视频列表（B 站空间 API）。

    输出 ParsedItem（kind="bv" 或 "av"），可接入 BilibiliVideoFetcher 抓元数据。
    """

    # v2.9.1+：主端点是 wbi 鉴权的 arc/search
    WBI_ARC_SEARCH_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
    # 旧端点保留作为降级（无 wbi，但风控严）
    ARC_SEARCH_URL = "https://api.bilibili.com/x/space/arc/search"
    # 原 seek_arc 端点已 404，仅留作常量引用，不调用
    SEEK_ARC_URL = "https://api.bilibili.com/x/polymer/web-space/home/seek_arc"
    PS_MAX = 50  # B 站单页最多 50 条

    def __init__(
        self,
        *,
        sess: Optional[requests.Session] = None,
        timeout: float = 10.0,
        max_retries: int = 2,
        wbi_cache: Optional[WbiKeyCache] = None,
        interval_ms: int = 300,  # v3.0.9+ 翻页间隔（默认 300ms = 3.3 QPS）
    ):
        self.sess = sess or requests.Session()
        # 仿浏览器请求头（wbi 端点对 UA / Referer 不严格但更稳）
        self.sess.headers.setdefault("User-Agent", (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ))
        self.sess.headers.setdefault("Referer", "https://www.bilibili.com/")
        self.timeout = timeout
        self.max_retries = max_retries
        # wbi key 缓存（每 12h 自动刷新）
        self.wbi_cache = wbi_cache or WbiKeyCache(sess=self.sess)
        # v3.0.9+ 翻页间隔：min 0 = 不 sleep；默认 300ms 保留旧行为
        self.interval_ms = max(0, int(interval_ms))

    def fetch_author_videos(
        self,
        uid: int,
        *,
        days: Optional[int] = None,
        max_count: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        include_short: bool = True,
    ) -> List[ParsedItem]:
        """按 UP 主 UID 抓取其投稿视频，返回 ParsedItem 列表。

        参数：
          uid: B 站 UP 主 mid（数字 ID）
          days: 最近 N 天（None=不限制）
          max_count: 最多抓多少条（None=不限制）
          since: 起始日期（包含），datetime 对象（naive 视为北京时间）
          until: 结束日期（不包含），datetime 对象
          include_short: 是否包含短视频（默认 True）

        返回：ParsedItem 列表（kind="bv"，raw 为原始 BV 号）
        抛出：
          ValueError: uid 无效
          RuntimeError: 两个端点都失败
        """
        if not isinstance(uid, int) or uid <= 0:
            raise ValueError(f"uid 必须是正整数，got: {uid!r}")

        # 归一化时间范围（datetime → 时间戳秒）
        start_ts, end_ts = self._normalize_time_range(days, since, until)

        # 抓所有页（分页直到拿完或达到 max_count）
        archives = list(self._iter_author_archives(uid, start_ts, end_ts, max_count))

        # 转 ParsedItem
        items: List[ParsedItem] = []
        for arc in archives:
            bvid = arc.get("bvid") or ""
            aid = arc.get("aid") or 0
            if bvid:
                items.append(ParsedItem(kind="bv", value=bvid, raw=bvid))
            elif aid:
                items.append(ParsedItem(kind="av", value=str(aid), raw=str(aid)))
        return items

    def fetch_author_archives_raw(
        self,
        uid: int,
        *,
        days: Optional[int] = None,
        max_count: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> List[dict]:
        """按 UP 主 UID 抓取其投稿视频，返回原始 archive 字典列表。

        与 fetch_author_videos 的区别：
          - 返回 raw dict（含 bvid / aid / title / duration / pubdate / tid），
            而不是 ParsedItem。**适合阶段 1 列表导出（CSV）**。
          - 时间参数 / 端点 / 限流逻辑完全复用。

        返回：archive 字典列表（每个 dict 至少含 bvid / aid / pubdate）。
        抛出：ValueError（uid 无效）
        """
        if not isinstance(uid, int) or uid <= 0:
            raise ValueError(f"uid 必须是正整数，got: {uid!r}")

        start_ts, end_ts = self._normalize_time_range(days, since, until)
        return list(self._iter_author_archives(uid, start_ts, end_ts, max_count))

    # ---- 内部 ----

    def _normalize_time_range(
        self,
        days: Optional[int],
        since: Optional[datetime],
        until: Optional[datetime],
    ) -> tuple:
        """把 days/since/until 归一化成 (start_ts, end_ts) 元组。

        优先级：since/until 显式给定的优先；没给则用 days 算。
        全部为 None → (None, None) 不过滤。
        """
        # 显式 since/until 优先
        if since is not None or until is not None:
            start_ts = self._to_ts(since) if since is not None else None
            end_ts = self._to_ts(until) if until is not None else None
            return (start_ts, end_ts)
        # 用 days 算（默认北京时间当日 0 点起算）
        if days is not None and days > 0:
            now = datetime.now(TZ_BJ)
            since_dt = now - timedelta(days=days)
            # 用 since 当天的 00:00:00 作为起点（不精确到时分秒，避免漏掉当天发的）
            since_dt = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return (self._to_ts(since_dt), None)
        return (None, None)

    def _to_ts(self, dt: datetime) -> int:
        """datetime → B 站时间戳（秒）。naive 视为北京时间。"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_BJ)
        return int(dt.timestamp())

    def _iter_author_archives(
        self,
        uid: int,
        start_ts: Optional[int],
        end_ts: Optional[int],
        max_count: Optional[int],
    ) -> List[dict]:
        """分页拉 UP 主所有投稿，按时间倒序（在内存里按 start/end 过滤 + max_count 截断）。

        返回：所有满足条件的 archive 字典列表

        v2.9.1+：wbi 端点优先；失败时降级到旧端点（无 wbi，但 B 站 2024 加了风控）。
        """
        collected: List[dict] = []
        for pn in range(1, 100):  # 最多 100 页 = 5000 条
            # 主路径：wbi 鉴权的 arc/search
            page = self._fetch_page_arc_search(uid, pn, ps=self.PS_MAX)
            if page is None:
                # 降级：seek_arc 端点（实际已 404，保留作 fallback）
                page = self._fetch_page_seek_arc(uid, pn, ps=self.PS_MAX)
            if not page:
                break
            for arc in page:
                ts = self._extract_pubdate(arc)
                if start_ts is not None and ts < start_ts:
                    # 按时间倒序——一旦早于 start_ts 就到末尾了
                    return collected
                if end_ts is not None and ts >= end_ts:
                    continue
                collected.append(arc)
                if max_count is not None and len(collected) >= max_count:
                    return collected
            if len(page) < self.PS_MAX:
                # 最后一页
                break
            # v3.0.9+：用 interval_ms 替换硬编码 0.3s 延迟
            if self.interval_ms > 0:
                time.sleep(self.interval_ms / 1000.0)
        return collected

    def _fetch_page_seek_arc(self, uid: int, pn: int, ps: int) -> Optional[List[dict]]:
        """原 seek_arc 端点：/x/polymer/web-space/home/seek_arc

        v2.9.1+：此端点已 404，仅作 fallback 保留。
        """
        try:
            r = self.sess.get(
                self.SEEK_ARC_URL,
                params={
                    "mid": uid,
                    "pn": pn,
                    "ps": ps,
                    "order": "pubdate",
                    "platform": "web",
                    "web_location": "1550101",
                    "tid": 0,
                    "order_needed": "true",
                },
                timeout=self.timeout,
            )
            data = r.json()
        except Exception as e:
            return None
        if data.get("code") != 0:
            return None
        items = (data.get("data") or {}).get("items") or []
        out: List[dict] = []
        for item in items:
            out.extend(item.get("archives") or [])
        return out

    def _fetch_page_arc_search(self, uid: int, pn: int, ps: int) -> Optional[List[dict]]:
        """v2.9.1+ 主端点：/x/space/wbi/arc/search

        B 站 2023-03 起强制 WBI 鉴权。我们：
          1. 从缓存取 wbi keys（12h 自动刷新）
          2. 对参数做 WBI 签名（w_rid + wts）
          3. 解析 data.list.vlist[]

        返回：vlist 列表（B 站端点单页最大 50 条，所以 ps 上限 50）
        失败：None（让调用方走 fallback）
        """
        try:
            img_key, sub_key = self.wbi_cache.get()
        except Exception:
            # 取 key 失败（网络/未登录）—— 返回 None 让 fallback 处理
            return None
        # 构造业务参数（不带 w_rid/wts，由 enc_wbi 加）
        raw_params = {
            "mid": uid,
            "pn": pn,
            "ps": ps,
            "tid": 0,
            "order": "pubdate",
            "keyword": "",
        }
        signed = enc_wbi(raw_params, img_key, sub_key)
        try:
            r = self.sess.get(
                self.WBI_ARC_SEARCH_URL,
                params=signed,
                timeout=self.timeout,
            )
            data = r.json()
        except Exception:
            return None
        # 风控：-403 (v_voucher) → 让缓存 key 失效，下次重试
        if data.get("code") == -403:
            self.wbi_cache.invalidate()
            return None
        if data.get("code") != 0:
            return None
        vlist = (data.get("data") or {}).get("list") or {}
        return vlist.get("vlist") or []

    def _extract_pubdate(self, arc: dict) -> int:
        """从 archive 字典里提 pubdate 时间戳（秒）。"""
        # 新端点 archives 字段是 pubdate（秒级）
        ts = arc.get("pubdate")
        if ts is None:
            # 旧端点 vlist 字段是 created（秒级）
            ts = arc.get("created")
        if ts is None:
            return 0
        try:
            return int(ts)
        except (TypeError, ValueError):
            return 0

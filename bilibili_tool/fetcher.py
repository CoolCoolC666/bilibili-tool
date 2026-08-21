"""B 站信息获取器：视频 / 专栏 / 番剧 三类。
单条 / 批量，带错误分类与简单重试。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, List, Optional, Callable

import requests

from .models import ArticleInfo, BangumiInfo, VideoInfo, explain_code
from .parser import ParsedItem


VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
ARTICLE_VIEW_URL = "https://api.bilibili.com/x/article/view"
BANGUMI_VIEW_URL = "https://api.bilibili.com/pgc/view/pc/season"
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


class BilibiliArticleFetcher:
    """B 站专栏（read/cv + opus）数据获取器。

    API: GET /x/article/view?id={cv_id}
    返回: {code, data: {title, author: {mid, name}, stats: {view, like, ...}, ...}}

    注意：抓正文（content 字段）需要登录 cookie，本版本只抓公开字段。
    """

    NO_RETRY_CODES = {-404, 404, 65001, 65002}

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

    def fetch(self, target) -> ArticleInfo:
        """target 可以是 ParsedItem (kind=article)，或 cv_id 字符串/数字。"""
        info = self._build_skeleton(target)
        if info.status == "failed":
            return info
        try:
            response = self.sess.get(
                ARTICLE_VIEW_URL, params={"id": info.cv_id}, timeout=self.timeout
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

    def fetch_with_retry(self, target) -> ArticleInfo:
        last = self.fetch(target)
        for _ in range(self.max_retries):
            if last.is_ok or (last.api_code in self.NO_RETRY_CODES):
                break
            time.sleep(0.6)
            last = self.fetch(target)
        return last

    def batch_fetch(
        self,
        targets: Iterable,
        *,
        delay: float = 0.5,
        progress_cb: Optional[Callable[[int, int, ArticleInfo], None]] = None,
    ) -> List[ArticleInfo]:
        results: List[ArticleInfo] = []
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

    def _build_skeleton(self, target) -> ArticleInfo:
        if isinstance(target, ParsedItem):
            raw = target.raw or target.value
            if target.kind == "article":
                return ArticleInfo(raw_input=raw, input_kind="article", cv_id=target.value)
            return ArticleInfo(raw_input=raw, input_kind=target.kind, status="failed", error="非 article 类型")
        s = str(target).strip()
        if not s:
            return ArticleInfo(raw_input=s, status="failed", error="空输入")
        return ArticleInfo(raw_input=s, input_kind="raw", cv_id=s)

    def _hydrate(self, info: ArticleInfo, d: dict) -> None:
        info.status = "ok"
        info.title = d.get("title", "") or ""

        # 旧版 author 是 dict；新版可能直接给 mid/name 字段
        author = d.get("author") or {}
        if isinstance(author, dict):
            info.author_mid = author.get("mid")
            info.author_name = author.get("name", "") or ""
        else:
            # opus 可能是 string 或 author 字段缺失
            info.author_mid = d.get("mid") or d.get("author_mid")
            info.author_name = d.get("author_name", "") or d.get("up_name", "") or ""

        # 统计
        stats = d.get("stats") or {}
        info.view = stats.get("view")
        info.like = stats.get("like")
        info.favorite = stats.get("favorite")
        info.coin = stats.get("coin")
        info.share = stats.get("share")
        info.reply = stats.get("reply")

        # 备用顶层字段（有些 API 把 stats 拍平到顶层）
        for k in ("view", "like", "favorite", "coin", "share", "reply"):
            if getattr(info, k) is None and d.get(k) is not None:
                setattr(info, k, d.get(k))

        info.words = d.get("words")
        info.summary = d.get("summary", "") or ""
        # 封面：新版 banner / 旧版 pic
        info.banner = d.get("banner", "") or d.get("originImageUrls", [""])[0] if d.get("originImageUrls") else (d.get("banner", "") or "")
        info.pic = d.get("pic", "") or ""

        # 时间
        if d.get("ctime"):
            info.ctime = datetime.fromtimestamp(d["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
        if d.get("pubtime"):
            info.pubtime = datetime.fromtimestamp(d["pubtime"]).strftime("%Y-%m-%d %H:%M:%S")
        elif d.get("publish_time"):
            info.pubtime = datetime.fromtimestamp(d["publish_time"]).strftime("%Y-%m-%d %H:%M:%S")

        # 链接
        info.url = f"https://www.bilibili.com/read/cv{info.cv_id}" if info.cv_id else ""
        if not info.url and info.cv_id:
            info.url = f"https://www.bilibili.com/opus/{info.cv_id}"

        info.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BilibiliBangumiFetcher:
    """B 站番剧（ss + ep）数据获取器。

    API: GET /pgc/view/pc/season?season_id=xxx 或 ?ep_id=xxx
    返回: {code, result: {title, cover, evaluate, rating, total_ep, status, publish, ...}}

    为简化，**统一返回整季的元数据**。ep_id 形式会先查到 season_id 再查。
    """

    NO_RETRY_CODES = {-404, 404}

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

    def fetch(self, target) -> BangumiInfo:
        info = self._build_skeleton(target)
        if info.status == "failed":
            return info
        # 如果是 ep_id 形式，先尝试拿到 season_id
        if info.ep_id and not info.season_id:
            season_id_from_ep = self._lookup_season_id_by_ep(info.ep_id)
            if season_id_from_ep:
                info.season_id = season_id_from_ep
        # 主请求用 season_id
        try:
            params = {"season_id": info.season_id} if info.season_id else {"ep_id": info.ep_id}
            response = self.sess.get(
                BANGUMI_VIEW_URL, params=params, timeout=self.timeout
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
        # PGC API 用的是 "code" + "message" + "result"
        if code == 0 and data.get("result"):
            self._hydrate(info, data["result"])
        else:
            info.status = "not_found" if code in self.NO_RETRY_CODES else "failed"
            info.error = explain_code(code) if code else (data.get("message", "") or "未知错误")
        return info

    def fetch_with_retry(self, target) -> BangumiInfo:
        last = self.fetch(target)
        for _ in range(self.max_retries):
            if last.is_ok or (last.api_code in self.NO_RETRY_CODES):
                break
            time.sleep(0.6)
            last = self.fetch(target)
        return last

    def batch_fetch(
        self,
        targets: Iterable,
        *,
        delay: float = 0.5,
        progress_cb: Optional[Callable[[int, int, BangumiInfo], None]] = None,
    ) -> List[BangumiInfo]:
        results: List[BangumiInfo] = []
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

    def _build_skeleton(self, target) -> BangumiInfo:
        if isinstance(target, ParsedItem):
            raw = target.raw or target.value
            if target.kind == "bangumi_ss":
                return BangumiInfo(raw_input=raw, input_kind="bangumi_ss", season_id=int(target.value))
            if target.kind == "bangumi_ep":
                return BangumiInfo(raw_input=raw, input_kind="bangumi_ep", ep_id=int(target.value))
            return BangumiInfo(raw_input=raw, input_kind=target.kind, status="failed", error="非 bangumi 类型")
        s = str(target).strip()
        if not s:
            return BangumiInfo(raw_input=s, status="failed", error="空输入")
        # 兜底：纯数字当 ep_id
        if s.isdigit():
            return BangumiInfo(raw_input=s, input_kind="raw", ep_id=int(s))
        return BangumiInfo(raw_input=s, input_kind="raw", status="failed", error="无法识别输入")

    def _lookup_season_id_by_ep(self, ep_id: int) -> Optional[int]:
        """根据 ep_id 查 season_id。仅当 ep 形式时调用，多 1 次请求。"""
        try:
            r = self.sess.get(BANGUMI_VIEW_URL, params={"ep_id": ep_id}, timeout=self.timeout)
            data = r.json()
            if data.get("code") == 0 and data.get("result"):
                return data["result"].get("season_id")
        except Exception:
            pass
        return None

    def _hydrate(self, info: BangumiInfo, d: dict) -> None:
        info.status = "ok"
        info.title = d.get("title", "") or ""
        info.alias = d.get("alias", "") or ""
        info.type_name = d.get("type_name", "") or ""

        # 评分
        rating = d.get("rating") or {}
        if isinstance(rating, dict):
            info.rating_score = rating.get("score")
            info.rating_count = rating.get("count")

        # 元数据
        info.total_ep = d.get("total_ep") or d.get("total")
        info.status_text = d.get("status", "") or ""  # 已完结 / 连载中
        info.publish_date = d.get("publish", {}).get("pub_date_show", "") if isinstance(d.get("publish"), dict) else (d.get("publish_date", "") or "")

        # 统计
        info.view = d.get("stat", {}).get("view")
        info.favorite = d.get("stat", {}).get("favorites")
        info.coins = d.get("stat", {}).get("coins")
        info.danmaku = d.get("stat", {}).get("danmakus")
        info.reply = d.get("stat", {}).get("reply")
        info.share = d.get("stat", {}).get("share")
        info.like = d.get("stat", {}).get("likes")

        # 描述 / 封面
        info.desc = d.get("evaluate", "") or d.get("description", "") or ""
        info.cover = d.get("cover", "") or ""

        # 链接
        if info.season_id:
            info.url = f"https://www.bilibili.com/bangumi/play/ss{info.season_id}"
        elif info.ep_id:
            info.url = f"https://www.bilibili.com/bangumi/play/ep{info.ep_id}"

        info.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

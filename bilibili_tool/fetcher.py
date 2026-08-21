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
ARTICLE_VIEW_URL = "https://api.bilibili.com/x/article/view"  # 旧版 cv 端点
OPUS_DETAIL_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail"  # v2.8.1+ 新版 opus 端点
OPUS_HTML_FALLBACK = "https://www.bilibili.com/opus/"  # opus API 失败时降级到 web HTML
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
    """B 站专栏（read/cv 旧版 + opus 新版）数据获取器。

    **v2.8.1 重要修复**：opus 新版专栏（2024 B 站改版后的 URL）**不能**用 `/x/article/view` 查，
    必须走 `/x/polymer/web-dynamic/v1/opus/detail?id={opus_id}`。opus 端点返回嵌套结构：
      {code: 0, data: {item: {id_str, basic: {title, uid}, modules: [...]}}}

    旧版 cv 仍然走 `/x/article/view`，返回扁平结构。

    注意：抓正文需要登录 cookie，本版本只抓公开字段。
    """

    NO_RETRY_CODES = {-404, 404, 65001, 65002, -352}

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
        """target 可以是 ParsedItem (kind=article + is_opus 标志)，或 cv_id 字符串/数字。

        优先根据 target.is_opus 决定走哪个端点：
          - is_opus=True  → /x/polymer/web-dynamic/v1/opus/detail
          - is_opus=False → /x/article/view（默认）
        """
        info = self._build_skeleton(target)
        if info.status == "failed":
            return info
        # v2.8.1+：根据 is_opus 选端点
        if info.is_opus:
            url = OPUS_DETAIL_URL
        else:
            url = ARTICLE_VIEW_URL
        try:
            response = self.sess.get(
                url, params={"id": info.cv_id}, timeout=self.timeout
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
            if info.is_opus:
                # opus 端点：data = {item: {...}|null, fallback: {...}|null}
                # 正常情况：item 是有内容的 dict
                # 边界情况：item 是 None（被转发/已删），但 fallback 可能有指向
                item = data["data"].get("item") if isinstance(data["data"], dict) else None
                if item:
                    self._hydrate_opus(info, item)
                else:
                    # v2.8.1+：opus 失效时降级到 web HTML 拿 title
                    self._fallback_opus_html(info)
            else:
                # 旧版 cv 端点：data = {title, author: {mid, name}, stats: {...}, ...}
                self._hydrate(info, data["data"])
        else:
            info.status = "not_found" if code in self.NO_RETRY_CODES else "failed"
            info.error = explain_code(code)
        return info

    def _fallback_opus_html(self, info: ArticleInfo) -> None:
        """v2.8.1+ 降级策略：opus API 返回 item=null 时（被转发/已删），
        爬 web HTML 的 <title> 拿标题。

        标记 status="ok"（能拿到 title）+ error 字段写"原动态失效"提示。
        不抛异常；HTML 失败则回退到 failed 状态。
        """
        url = f"{OPUS_HTML_FALLBACK}{info.cv_id}"
        try:
            r = self.sess.get(url, timeout=self.timeout)
            text = r.text
        except Exception as e:
            info.status = "failed"
            info.error = f"opus API + HTML 降级都失败: API item=null, HTML 错误 {e}"
            return

        # 提取 <title>，去掉 " - 哔哩哔哩" 后缀
        import re as _re
        m = _re.search(r"<title[^>]*>(.*?)</title>", text, _re.DOTALL)
        if not m:
            info.status = "failed"
            info.error = "opus API item=null 且 HTML 无 <title>"
            return
        title = m.group(1).strip()
        # 去掉常见的 " - 哔哩哔哩" 后缀
        for suffix in (" - 哔哩哔哩", " - bilibili", " - B站"):
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        if not title or title == "哔哩哔哩":
            info.status = "failed"
            info.error = "opus API item=null 且 HTML <title> 无内容"
            return

        info.status = "ok"
        info.title = title
        info.error = "opus API item=null（原动态失效），仅从 HTML 拿到标题"
        # URL 仍然可用
        if info.cv_id and not info.url:
            info.url = f"https://www.bilibili.com/opus/{info.cv_id}"
        info.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                return ArticleInfo(
                    raw_input=raw, input_kind="article", cv_id=target.value,
                    is_opus=target.is_opus,  # v2.8.1+ 透传 is_opus
                )
            return ArticleInfo(raw_input=raw, input_kind=target.kind, status="failed", error="非 article 类型")
        s = str(target).strip()
        if not s:
            return ArticleInfo(raw_input=s, status="failed", error="空输入")
        # 字符串/数字：默认按旧版 cv 走（旧 API 兼容）
        return ArticleInfo(raw_input=s, input_kind="raw", cv_id=s, is_opus=False)

    def _hydrate(self, info: ArticleInfo, d: dict) -> None:
        """旧版 cv 端点的字段映射（/x/article/view 返回扁平结构）。"""
        info.status = "ok"
        info.title = d.get("title", "") or ""

        # 旧版 author 是 dict
        author = d.get("author") or {}
        if isinstance(author, dict):
            info.author_mid = author.get("mid")
            info.author_name = author.get("name", "") or ""

        # 统计
        stats = d.get("stats") or {}
        info.view = stats.get("view")
        info.like = stats.get("like")
        info.favorite = stats.get("favorite")
        info.coin = stats.get("coin")
        info.share = stats.get("share")
        info.reply = stats.get("reply")

        # 备用顶层字段
        for k in ("view", "like", "favorite", "coin", "share", "reply"):
            if getattr(info, k) is None and d.get(k) is not None:
                setattr(info, k, d.get(k))

        info.words = d.get("words")
        info.summary = d.get("summary", "") or ""
        info.banner = d.get("banner", "") or ""
        info.pic = d.get("pic", "") or ""

        # 时间
        if d.get("ctime"):
            info.ctime = datetime.fromtimestamp(d["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
        if d.get("pubtime"):
            info.pubtime = datetime.fromtimestamp(d["pubtime"]).strftime("%Y-%m-%d %H:%M:%S")
        elif d.get("publish_time"):
            info.pubtime = datetime.fromtimestamp(d["publish_time"]).strftime("%Y-%m-%d %H:%M:%S")

        # 链接（cv 形式）
        if info.cv_id:
            info.url = f"https://www.bilibili.com/read/cv{info.cv_id}"

        info.fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _hydrate_opus(self, info: ArticleInfo, item: dict) -> None:
        """v2.8.1+：opus 端点的字段映射（嵌套 basic + modules 结构）。"""
        info.status = "ok"
        # basic: 标题 + 作者 UID
        basic = item.get("basic") or {}
        info.title = basic.get("title", "") or ""

        # modules: 按 module_type 取数据
        modules = item.get("modules") or []
        title = ""
        author_name = ""
        author_mid = None
        author_face = ""
        pub_time_text = ""
        stat_counts = {}  # {like: n, coin: n, ...}
        for m in modules:
            mtype = m.get("module_type")
            if mtype == "MODULE_TYPE_TITLE":
                mt = m.get("module_title") or {}
                title = mt.get("text", "") or title
            elif mtype == "MODULE_TYPE_AUTHOR":
                ma = m.get("module_author") or {}
                author_name = ma.get("name", "") or ""
                try:
                    author_mid = int(ma.get("mid", 0)) or None
                except (TypeError, ValueError):
                    author_mid = None
                author_face = ma.get("face", "") or ""
                pub_time_text = ma.get("pub_time", "") or ""
            elif mtype == "MODULE_TYPE_STAT":
                ms = m.get("module_stat") or {}
                for k in ("like", "coin", "favorite", "comment", "forward"):
                    sub = ms.get(k) or {}
                    count = sub.get("count", 0) if isinstance(sub, dict) else 0
                    try:
                        stat_counts[k] = int(count)
                    except (TypeError, ValueError):
                        stat_counts[k] = 0

        # fallback：modules 缺数据时用 basic
        if not title:
            title = basic.get("title", "") or ""
        if not author_mid:
            try:
                author_mid = int(basic.get("uid", 0)) or None
            except (TypeError, ValueError):
                author_mid = None

        info.title = title
        info.author_name = author_name
        info.author_mid = author_mid
        info.author_face = author_face

        # 统计字段映射
        info.like = stat_counts.get("like")
        info.coin = stat_counts.get("coin")
        info.favorite = stat_counts.get("favorite")
        info.reply = stat_counts.get("comment")  # comment 实际是评论数
        info.forward = stat_counts.get("forward")
        # opus 端点没有 view / share 字段（默认 None，导出时留空）

        # pub_time_text 例 "2026年04月05日 10:49" —— 存到 pubtime 字段
        if pub_time_text:
            info.pubtime = pub_time_text

        # opus 端点没有 summary / words 字段（default 空字符串）
        info.summary = ""
        info.words = None

        # 链接（opus 形式）
        if info.cv_id:
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

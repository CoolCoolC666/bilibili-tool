"""Flask Web 应用：把 bilibili_tool 包成一个本地网页工具。

启动：python run_web.py  → http://127.0.0.1:5050
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from bilibili_tool import (
    AuthorDetailExporter,
    AuthorListExporter,
    AuthorVideoFetcher,
    BilibiliArticleFetcher,
    BilibiliBangumiFetcher,
    BilibiliVideoFetcher,
    Cache,
    expand_short_urls,
    export_all,
    export_all_multi,
    parse_text,
)
from bilibili_tool.cache import (
    _article_fingerprint,
    _article_keys,
    _bangumi_fingerprint,
    _bangumi_keys,
    parse_duration,
)
from bilibili_tool.models import ArticleInfo, BangumiInfo, VideoInfo


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_CACHE = os.path.join(ROOT, "data", "cache.json")
DEFAULT_CACHE_ARTICLE = os.path.join(ROOT, "data", "cache_article.json")
DEFAULT_CACHE_BANGUMI = os.path.join(ROOT, "data", "cache_bangumi.json")
DEFAULT_OUT = os.path.join(ROOT, "output")
DEFAULT_XLSX = os.path.join(ROOT, "output", "xlsx")  # v3.0.1+：XLSX 单独目录

app = Flask(
    __name__,
    template_folder=os.path.join(HERE, "templates"),
    static_folder=os.path.join(HERE, "static"),
)


# ---------------- 任务管理 ----------------

class Job:
    def __init__(self, job_id: str, targets: str, options: dict):
        self.id = job_id
        self.targets = targets
        self.options = options
        self.status = "pending"   # pending / running / done / error
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.finished_at = ""
        self.total = 0
        self.processed = 0
        self.ok_count = 0
        self.failed_count = 0
        self.from_cache = 0
        self.log: List[str] = []
        # v2.8.0：三类独立 results
        self.video_results: List[VideoInfo] = []
        self.article_results: List[ArticleInfo] = []
        self.bangumi_results: List[BangumiInfo] = []
        self.outputs: Dict[str, str] = {}  # format -> path
        self.error = ""
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    def push_log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.log.append(f"[{ts}] {line}")
            if len(self.log) > 500:
                self.log = self.log[-500:]
            self._cv.notify_all()

    def snapshot(self) -> dict:
        with self._lock:
            all_results = (
                [self._public_video(r) for r in self.video_results]
                + [self._public_article(r) for r in self.article_results]
                + [self._public_bangumi(r) for r in self.bangumi_results]
            )
            return {
                "id": self.id,
                "status": self.status,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "total": self.total,
                "processed": self.processed,
                "ok_count": self.ok_count,
                "failed_count": self.failed_count,
                "from_cache": self.from_cache,
                "log_tail": list(self.log[-30:]),
                "results": all_results,
                "outputs": self.outputs,
                "error": self.error,
            }

    @staticmethod
    def _public_video(v: VideoInfo) -> dict:
        return {
            "kind": "video",
            "raw_input": v.raw_input,
            "input_kind": v.input_kind,
            "status": v.status,
            "api_code": v.api_code,
            "error": v.error,
            "aid": v.aid,
            "bvid": v.bvid,
            "title": v.title,
            "up_name": v.up_name,
            "tname": v.tname,
            "view": v.view,
            "like": v.like,
            "coin": v.coin,
            "favorite": v.favorite,
            "share": v.share,
            "reply": v.reply,
            "danmaku": v.danmaku,
            "duration": v.duration,
            "pubdate": v.pubdate,
            "ctime": v.ctime,
            "desc": v.desc,
            "url": v.url,
            "fetched_at": v.fetched_at,
        }

    @staticmethod
    def _public_article(a: ArticleInfo) -> dict:
        return {
            "kind": "article",
            "raw_input": a.raw_input,
            "input_kind": a.input_kind,
            "status": a.status,
            "api_code": a.api_code,
            "error": a.error,
            "cv_id": a.cv_id,
            "is_opus": a.is_opus,
            "is_only_fans": a.is_only_fans,
            "title": a.title,
            "author_name": a.author_name,
            "author_mid": a.author_mid,
            "author_face": a.author_face,
            "view": a.view,
            "like": a.like,
            "coin": a.coin,
            "favorite": a.favorite,
            "share": a.share,
            "reply": a.reply,
            "forward": a.forward,
            "words": a.words,
            "ctime": a.ctime,
            "pubtime": a.pubtime,
            "summary": a.summary,
            "banner": a.banner,
            "pic": a.pic,
            "url": a.url,
            "fetched_at": a.fetched_at,
        }

    @staticmethod
    def _public_bangumi(b: BangumiInfo) -> dict:
        return {
            "kind": "bangumi",
            "raw_input": b.raw_input,
            "input_kind": b.input_kind,
            "status": b.status,
            "api_code": b.api_code,
            "error": b.error,
            "season_id": b.season_id,
            "ep_id": b.ep_id,
            "title": b.title,
            "alias": b.alias,
            "type_name": b.type_name,
            "rating_score": b.rating_score,
            "rating_count": b.rating_count,
            "total_ep": b.total_ep,
            "status_text": b.status_text,
            "publish_date": b.publish_date,
            "view": b.view,
            "favorite": b.favorite,
            "coins": b.coins,
            "like": b.like,
            "share": b.share,
            "reply": b.reply,
            "danmaku": b.danmaku,
            "desc": b.desc,
            "cover": b.cover,
            "url": b.url,
            "fetched_at": b.fetched_at,
        }


_JOBS: Dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _do_fetch_pass(
    job: Job,
    items: List,
    fetcher,
    cache,
    max_age_seconds: int,
    kind: str,  # "video" / "article" / "bangumi"
    skeleton_fn,
    progress_label: str,
    delay: float,
) -> List[Any]:
    """跑一个抓取 pass：通用骨架，处理 cache 命中 / 真实请求。"""
    results: List[Any] = []
    if not items:
        return results
    job.push_log(f"  {progress_label} 共 {len(items)} 个")
    for i, p in enumerate(items, 1):
        sk = skeleton_fn(p)
        if cache is not None:
            cached = cache.get_fresh(sk, max_age_seconds=max_age_seconds)
            if cached:
                results.append(cached)
                job.from_cache += 1
                job.processed += 1
                if cached.is_ok:
                    job.ok_count += 1
                else:
                    job.failed_count += 1
                job.push_log(
                    f"  [{i}/{len(items)}] ↪ cache {p.value} -> {cached.status}"
                )
                continue
        job.push_log(f"  [{i}/{len(items)}] → 请求 {p.value} ...")
        info = fetcher.fetch_with_retry(p)
        results.append(info)
        job.processed += 1
        if info.is_ok:
            job.ok_count += 1
            job.push_log(f"  [{i}/{len(items)}] ✓ {info.title[:28]}")
        else:
            job.failed_count += 1
            job.push_log(
                f"  [{i}/{len(items)}] ✗ {p.value} {info.status} code={info.api_code} {info.error}"
            )
        if cache is not None:
            cache.put(info)
        if i < len(items) and delay > 0:
            time.sleep(delay)
    return results


def _video_skeleton(p):
    return VideoInfo(
        input_kind=p.kind,
        bvid=p.value if p.kind == "bv" else "",
        aid=int(p.value) if p.kind == "av" else 0,
        raw_input=p.raw,
    )


def _article_skeleton(p):
    # v2.8.1+：透传 is_opus 标志，决定 fetcher 走哪个 API 端点
    return ArticleInfo(
        input_kind=p.kind, cv_id=p.value, raw_input=p.raw, is_opus=getattr(p, "is_opus", False),
    )


def _bangumi_skeleton(p):
    if p.kind == "bangumi_ss":
        return BangumiInfo(input_kind=p.kind, season_id=int(p.value), raw_input=p.raw)
    return BangumiInfo(input_kind=p.kind, ep_id=int(p.value), raw_input=p.raw)


def _run_job(job: Job) -> None:
    """后台线程：实际抓取逻辑。v2.8.0 支持视频/专栏/番剧三类。"""
    try:
        job.status = "running"
        job.push_log(f"任务启动：{job.targets[:80]}{'...' if len(job.targets) > 80 else ''}")

        parsed = parse_text(job.targets, allow_bare_numbers=job.options.get("allow_bare_numbers", False))
        if not parsed:
            job.status = "error"
            hint = ""
            if not job.options.get("allow_bare_numbers", False):
                hint = "（如果输入里全是数字，勾选「允许识别裸数字为 AV 号」再试）"
            job.error = f"未识别到任何 AV / BV / URL / 专栏 / 番剧。{hint}"
            job.push_log("❌ " + job.error)
            return

        # 短链展开
        parsed = expand_short_urls(parsed)
        if not parsed:
            job.status = "error"
            job.error = "短链解析后无有效 ID。"
            job.push_log("❌ " + job.error)
            return

        # 按 kind 分桶
        video_items = [p for p in parsed if p.kind in ("av", "bv")]
        article_items = [p for p in parsed if p.kind == "article"]
        bangumi_items = [p for p in parsed if p.kind in ("bangumi_ss", "bangumi_ep")]

        # 应用 fetch 开关
        if not job.options.get("fetch_articles", True):
            if article_items:
                job.push_log(f"  --no-fetch-articles：跳过 {len(article_items)} 个专栏")
            article_items = []
        if not job.options.get("fetch_bangumi", True):
            if bangumi_items:
                job.push_log(f"  --no-fetch-bangumi：跳过 {len(bangumi_items)} 个番剧")
            bangumi_items = []

        job.total = len(video_items) + len(article_items) + len(bangumi_items)
        if job.total == 0:
            job.status = "error"
            job.error = "过滤后没有需要抓取的项目。"
            job.push_log("❌ " + job.error)
            return
        job.push_log(
            f"解析到 {len(parsed)} 个 → 视频 {len(video_items)} / 专栏 {len(article_items)} / 番剧 {len(bangumi_items)}"
        )

        # 缓存策略
        no_cache = job.options.get("no_cache", False)
        if no_cache:
            max_age_seconds = 0
            max_age_desc = "0（不用缓存）"
        else:
            max_age_seconds = parse_duration(job.options.get("max_age", "1h"))
            if max_age_seconds is None:
                max_age_seconds = 3600
            max_age_desc = job.options.get("max_age", "1h")
        job.push_log(f"缓存策略: max-age = {max_age_desc}")

        # 三种 cache 各自独立
        video_cache = Cache(DEFAULT_CACHE) if not no_cache else None
        article_cache = Cache(
            DEFAULT_CACHE_ARTICLE,
            record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint,
        ) if not no_cache else None
        bangumi_cache = Cache(
            DEFAULT_CACHE_BANGUMI,
            record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint,
        ) if not no_cache else None

        delay = float(job.options.get("delay", 0.5))
        retry = int(job.options.get("retry", 1))
        timeout = float(job.options.get("timeout", 10.0))

        # --- 视频 ---
        if video_items:
            fetcher = BilibiliVideoFetcher(max_retries=retry, timeout=timeout)
            job.push_log(f"📹 开始抓取视频")
            job.video_results = _do_fetch_pass(
                job, video_items, fetcher, video_cache, max_age_seconds,
                kind="video", skeleton_fn=_video_skeleton,
                progress_label="视频", delay=delay,
            )
            if video_cache is not None:
                try:
                    video_cache.save()
                except OSError as e:
                    job.push_log(f"⚠ 视频缓存保存失败: {e}")

        # --- 专栏 ---
        if article_items:
            fetcher = BilibiliArticleFetcher(max_retries=retry, timeout=timeout)
            job.push_log(f"📝 开始抓取专栏")
            job.article_results = _do_fetch_pass(
                job, article_items, fetcher, article_cache, max_age_seconds,
                kind="article", skeleton_fn=_article_skeleton,
                progress_label="专栏", delay=delay,
            )
            if article_cache is not None:
                try:
                    article_cache.save()
                except OSError as e:
                    job.push_log(f"⚠ 专栏缓存保存失败: {e}")

        # --- 番剧 ---
        if bangumi_items:
            fetcher = BilibiliBangumiFetcher(max_retries=retry, timeout=timeout)
            job.push_log(f"🎬 开始抓取番剧")
            job.bangumi_results = _do_fetch_pass(
                job, bangumi_items, fetcher, bangumi_cache, max_age_seconds,
                kind="bangumi", skeleton_fn=_bangumi_skeleton,
                progress_label="番剧", delay=delay,
            )
            if bangumi_cache is not None:
                try:
                    bangumi_cache.save()
                except OSError as e:
                    job.push_log(f"⚠ 番剧缓存保存失败: {e}")

        job.push_log(f"💾 缓存已保存")

        # 导出
        try:
            base = f"web_{job.id[:8]}_{datetime.now().strftime('%H%M%S')}"
            has_multi = bool(job.article_results or job.bangumi_results)
            excl = job.options.get("exclude_invalid", False)
            dedupe = job.options.get("dedupe", True)
            if has_multi:
                saved = export_all_multi(
                    base=base, out_dir=DEFAULT_OUT,
                    videos=job.video_results, articles=job.article_results, bangumis=job.bangumi_results,
                    dedupe=dedupe, exclude_invalid=excl,
                )
            else:
                saved = export_all(
                    job.video_results, base=base, out_dir=DEFAULT_OUT,
                    dedupe=dedupe, exclude_invalid=excl,
                )
            for fmt, path in saved.items():
                job.outputs[fmt] = os.path.basename(path)
                job.push_log(f"📦 导出 {fmt}: {os.path.basename(path)}")

            # 统计
            all_results = job.video_results + job.article_results + job.bangumi_results
            n_raw = len(all_results)
            from bilibili_tool.exporter import (
                filter_valid as _filt,
                dedupe_videos as _dv, dedupe_articles as _da, dedupe_bangumis as _db,
            )
            if excl:
                v_after = len(_filt(job.video_results))
                a_after = len(_filt(job.article_results))
                b_after = len(_filt(job.bangumi_results))
                n_after = v_after + a_after + b_after
                if n_raw != n_after:
                    job.push_log(f"  ↪ 排除失效：{n_raw} 条 → {n_after} 条")
            else:
                v_after = len(job.video_results)
                a_after = len(job.article_results)
                b_after = len(job.bangumi_results)
                n_after = n_raw
            if dedupe:
                v_f = len(_dv(_filt(job.video_results) if excl else job.video_results))
                a_f = len(_da(_filt(job.article_results) if excl else job.article_results))
                b_f = len(_db(_filt(job.bangumi_results) if excl else job.bangumi_results))
                n_final = v_f + a_f + b_f
                if n_after != n_final:
                    job.push_log(f"  ↪ 去重：{n_after} 条 → {n_final} 条")
        except Exception as e:
            job.push_log(f"⚠ 导出失败: {e}")

        job.status = "done"
        job.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job.push_log(
            f"✅ 完成：{job.ok_count} 成功 / {job.failed_count} 失败 / {job.from_cache} 缓存命中"
        )
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        job.push_log(f"💥 异常: {e}")


# ---------------- 路由 ----------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------- v2.9.0+ 按 UP 主抓取 ----------------

@app.route("/author")
def author_page():
    """v2.9.0+：UP 主视频批量抓取（阶段 1 / 阶段 2）。"""
    return render_template("author.html")


def _parse_uids_from_input(text: str) -> list:
    """从用户输入里抠出所有 uid（支持：纯数字 / space 链接 / 手机端短链）。"""
    import re
    items = parse_text(text, allow_bare_numbers=True)
    uids = []
    for p in items:
        if p.kind == "up":
            try:
                uids.append(int(p.value))
            except ValueError:
                pass
    # 提取纯数字（如果没被 parse_text 当成 up 识别）
    for tok in text.split():
        if tok.isdigit() and int(tok) not in uids:
            uids.append(int(tok))
    return uids


@app.route("/api/author/detail", methods=["POST"])
def author_detail():
    """v3.0.4+ 阶段 2：异步抓详情（带实时进度）。

    之前：同步调用 → 客户端只能等"数十秒到几分钟"返回（看进度尴尬）
    现在：立即返回 job_id → 后台线程跑抓取 → 前端轮询 progress
    """
    data = request.get_json(force=True, silent=True) or {}
    filename = (data.get("filename") or "").strip()
    if not filename:
        return jsonify({"error": "filename 不能为空（阶段 1 导出的 CSV 文件名）"}), 400

    # 安全：限定在 output 目录
    safe = os.path.basename(filename)
    csv_path = os.path.join(DEFAULT_OUT, safe)
    if not os.path.exists(csv_path):
        return jsonify({"error": f"文件不存在：{safe}"}), 404

    try:
        max_count = data.get("max")
        if max_count is not None:
            max_count = int(max_count)
        # v3.0.9+：interval_ms 优先于 delay（统一翻页/单点间隔）
        # 后向兼容：旧 delay 参数仍可用，缺省 0.6s
        interval_ms = data.get("interval_ms")
        if interval_ms is not None:
            interval_ms = max(0, int(interval_ms))
            delay = interval_ms / 1000.0
        else:
            delay = float(data.get("delay", 0.6))
        timeout = float(data.get("timeout", 10.0))
        retry = int(data.get("retry", 2))

        # 创建任务 + 后台线程
        job_id = uuid.uuid4().hex[:8]
        job = {
            "id": job_id,
            "filename": safe,
            "status": "pending",   # pending / running / done / error
            "total": 0,
            "processed": 0,
            "ok_count": 0,
            "fail_count": 0,
            "current": "",          # 当前正在抓的视频标题
            "log": [],              # 实时日志
            "xlsx_path": "",        # 完成后的下载路径
            "error": "",
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),  # v3.0.9+ 回显
        }
        with _DETAIL_LOCK:
            _DETAIL_JOBS[job_id] = job
        t = threading.Thread(
            target=_run_detail_job,
            args=(job, csv_path, max_count, delay, timeout, retry),
            daemon=True,
        )
        t.start()
        return jsonify({
            "job_id": job_id,
            "filename": safe,
            "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# v3.0.4+ 阶段 2 异步任务管理
_DETAIL_JOBS: Dict[str, dict] = {}
_DETAIL_LOCK = threading.Lock()


def _run_detail_job(job, csv_path, max_count, delay, timeout, retry):
    """后台线程：跑 detail，实时更新 job 进度。"""
    try:
        job["status"] = "running"
        with _DETAIL_LOCK:
            job["log"].append(f"[{job['created_at']}] 启动：{job['filename']}")

        # 读 CSV
        from bilibili_tool.author_detail import read_author_csv, rows_to_parsed_items
        rows = read_author_csv(csv_path)
        if not rows:
            raise ValueError(f"CSV 文件为空或格式错误：{csv_path}")
        items = rows_to_parsed_items(rows)
        if max_count is not None:
            items = items[:max_count]
        job["total"] = len(items)
        with _DETAIL_LOCK:
            job["log"].append(f"  共 {len(items)} 条视频，开始抓取详情...")

        # 抓详情（每条更新进度）
        from bilibili_tool.fetcher import BilibiliVideoFetcher
        vfetcher = BilibiliVideoFetcher(max_retries=retry, timeout=timeout)
        results = []
        for i, item in enumerate(items, 1):
            info = vfetcher.fetch_with_retry(item)
            results.append(info)
            title = (info.title or info.raw_input or item.value or "")[:40]
            ok = info.is_ok
            job["processed"] = i
            job["current"] = title
            if ok:
                job["ok_count"] += 1
            else:
                job["fail_count"] += 1
            with _DETAIL_LOCK:
                job["log"].append(
                    f"  [{i:3d}/{len(items)}] {'OK' if ok else 'FAIL'} {title} {info.error or ''}"
                )
                # 日志上限 500
                if len(job["log"]) > 500:
                    job["log"] = job["log"][-500:]
            # 限速
            if i < len(items) and delay > 0:
                time.sleep(delay)

        # 写 XLSX
        up_uid = rows[0].get("up_uid", "unknown") or "unknown"
        from bilibili_tool.exporter import save_xlsx
        os.makedirs(DEFAULT_XLSX, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        xlsx_path = os.path.abspath(os.path.join(DEFAULT_XLSX, f"author_detail_{up_uid}_{ts}.xlsx"))
        save_xlsx(results, xlsx_path)

        # 完成
        rel = os.path.relpath(xlsx_path, DEFAULT_OUT).replace("\\", "/")
        job["xlsx_path"] = rel
        job["status"] = "done"
        with _DETAIL_LOCK:
            job["log"].append(
                f"  [完成] {job['ok_count']} 成功 / {job['fail_count']} 失败 → {rel}"
            )
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        with _DETAIL_LOCK:
            job["log"].append(f"  [异常] {e}")


# v3.0.7+ 批量抓详情（多 CSV）
@app.route("/api/author/detail/batch", methods=["POST"])
def author_detail_batch():
    """v3.0.7+ 阶段 2 批量：一次性抓多个 CSV（每个 CSV 一个 XLSX）。

    Body:
      filenames: ["author_53456_xxx.csv", "author_483307278_xxx.csv"]
      max: 单个 CSV 最多抓多少（None=全部）
      delay: 请求间隔
      timeout: 单视频超时
      retry: 重试次数
    """
    data = request.get_json(force=True, silent=True) or {}
    filenames = data.get("filenames", [])
    if not filenames:
        return jsonify({"error": "filenames 不能为空"}), 400
    if not isinstance(filenames, list):
        return jsonify({"error": "filenames 必须是列表"}), 400

    # 验证文件都存在
    missing = []
    safe_paths = []
    for fn in filenames:
        if not isinstance(fn, str):
            continue
        safe = os.path.basename(fn)
        full = os.path.join(DEFAULT_OUT, safe)
        if not os.path.isfile(full):
            missing.append(fn)
        else:
            safe_paths.append(safe)
    if missing:
        return jsonify({"error": f"文件不存在：{missing[:3]}{'...' if len(missing) > 3 else ''}"}), 404
    if not safe_paths:
        return jsonify({"error": "没有可用的文件"}), 400

    try:
        max_count = data.get("max")
        if max_count is not None:
            max_count = int(max_count)
        # v3.0.9+：interval_ms 优先于 delay（统一翻页/单点间隔）
        interval_ms = data.get("interval_ms")
        if interval_ms is not None:
            interval_ms = max(0, int(interval_ms))
            delay = interval_ms / 1000.0
        else:
            delay = float(data.get("delay", 0.6))
        timeout = float(data.get("timeout", 10.0))
        retry = int(data.get("retry", 2))

        # 创建任务（v3.0.7+：multi-CSV 模式）
        job_id = uuid.uuid4().hex[:8]
        job = {
            "id": job_id,
            "filenames": safe_paths,
            "status": "pending",
            "sub_total": len(safe_paths),     # CSV 总数
            "sub_done": 0,                    # 已完成 CSV 数
            "sub_current": "",               # 当前 CSV 文件名
            "total": 0,                       # 当前 CSV 内视频总数（动态）
            "processed": 0,                   # 当前 CSV 内已处理数
            "ok_count": 0,
            "fail_count": 0,
            "current": "",                    # 当前正在抓的视频
            "log": [],
            "xlsx_paths": [],                 # 所有生成的 XLSX 路径
            "errors": [],                     # 每个 CSV 的错误（如有）
            "error": "",
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),  # v3.0.9+ 回显
        }
        with _DETAIL_LOCK:
            _DETAIL_JOBS[job_id] = job
        t = threading.Thread(
            target=_run_detail_batch_job,
            args=(job, safe_paths, max_count, delay, timeout, retry),
            daemon=True,
        )
        t.start()
        return jsonify({
            "job_id": job_id,
            "total_files": len(safe_paths),
            "filenames": safe_paths,
            "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _run_detail_batch_job(job, csv_paths, max_count, delay, timeout, retry):
    """v3.0.7+：批量跑多个 CSV 的 detail。"""
    try:
        job["status"] = "running"
        with _DETAIL_LOCK:
            job["log"].append(f"[{job['created_at']}] 启动批量任务：{len(csv_paths)} 个 CSV")

        from bilibili_tool.fetcher import BilibiliVideoFetcher
        from bilibili_tool.author_detail import read_author_csv, rows_to_parsed_items
        from bilibili_tool.exporter import save_xlsx
        vfetcher = BilibiliVideoFetcher(max_retries=retry, timeout=timeout)

        total_ok = 0
        total_fail = 0

        for csv_idx, csv_path in enumerate(csv_paths, 1):
            job["sub_current"] = csv_path
            with _DETAIL_LOCK:
                job["log"].append(
                    f"\n[{csv_idx}/{len(csv_paths)}] 处理：{csv_path}"
                )
            full = os.path.join(DEFAULT_OUT, csv_path)

            try:
                rows = read_author_csv(full)
                if not rows:
                    raise ValueError(f"CSV 为空或格式错误")
                items = rows_to_parsed_items(rows)
                if max_count is not None:
                    items = items[:max_count]
                job["total"] = len(items)
                job["processed"] = 0

                results = []
                for i, item in enumerate(items, 1):
                    info = vfetcher.fetch_with_retry(item)
                    results.append(info)
                    title = (info.title or info.raw_input or item.value or "")[:40]
                    ok = info.is_ok
                    if ok:
                        total_ok += 1
                    else:
                        total_fail += 1
                    job["processed"] = i
                    job["current"] = title
                    with _DETAIL_LOCK:
                        job["log"].append(
                            f"  [{csv_idx}/{len(csv_paths)}] "
                            f"[{i:3d}/{len(items)}] "
                            f"{'OK' if ok else 'FAIL'} {title}"
                        )
                        if len(job["log"]) > 500:
                            job["log"] = job["log"][-500:]
                    if i < len(items) and delay > 0:
                        time.sleep(delay)

                # 写 XLSX
                up_uid = rows[0].get("up_uid", "unknown") or "unknown"
                os.makedirs(DEFAULT_XLSX, exist_ok=True)
                from datetime import datetime as _dt
                ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                xlsx_path = os.path.abspath(
                    os.path.join(DEFAULT_XLSX, f"author_detail_{up_uid}_{ts}.xlsx")
                )
                save_xlsx(results, xlsx_path)
                rel = os.path.relpath(xlsx_path, DEFAULT_OUT).replace("\\", "/")
                job["xlsx_paths"].append(rel)
                with _DETAIL_LOCK:
                    job["log"].append(f"  [{csv_idx}/{len(csv_paths)}] XLSX: {rel}")

            except Exception as e:
                job["errors"].append({"file": csv_path, "error": str(e)})
                with _DETAIL_LOCK:
                    job["log"].append(f"  [{csv_idx}/{len(csv_paths)}] FAIL: {e}")

            job["sub_done"] = csv_idx
            job["ok_count"] = total_ok
            job["fail_count"] = total_fail
            # 短暂停顿（不同 CSV 之间）
            if csv_idx < len(csv_paths) and delay > 0:
                time.sleep(delay)

        job["status"] = "done"
        with _DETAIL_LOCK:
            job["log"].append(
                f"\n[全部完成] {total_ok} 成功 / {total_fail} 失败 "
                f"({len(csv_paths)} 个 CSV, {len(job['xlsx_paths'])} 个 XLSX)"
            )
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        with _DETAIL_LOCK:
            job["log"].append(f"[异常] {e}")


# v3.0.7+：在文件管理器中打开 output/ 目录（Windows）
@app.route("/api/open-output-folder", methods=["POST"])
def open_output_folder():
    """v3.0.7+ 智能定位：按文件类型选目录。

    v3.0.8+ 智能逻辑：
      - select 含 'xlsx/' → 打开 output/xlsx/（高亮文件）
      - select 以 '.csv' 结尾 → 打开 output/（高亮文件）
      - select 以 '.xlsx' 结尾但路径不含 'xlsx/' → 打开 output/xlsx/（高亮）
      - 没 select → 打开 output/ 默认

    Body (可选):
      select: 文件路径（如 "xlsx/author_detail_xxx.xlsx"）
    """
    import subprocess
    import platform

    data = request.get_json(force=True, silent=True) or {}
    select = (data.get("select") or "").strip()

    if select:
        safe = (select.replace("\\", "/").lstrip("/")).replace("..", "")
        # 智能选目录
        if "/xlsx/" in select or select.startswith("xlsx/"):
            # XLSX 文件 → output/xlsx/
            target_dir = DEFAULT_XLSX
            full = os.path.join(target_dir, os.path.basename(select))
        elif select.endswith(".xlsx"):
            # 兜底：任何 .xlsx 都到 xlsx/
            target_dir = DEFAULT_XLSX
            full = os.path.join(target_dir, os.path.basename(select))
        else:
            # CSV 文件 → output/
            target_dir = DEFAULT_OUT
            full = os.path.join(target_dir, os.path.basename(select))

        if not os.path.isfile(full):
            return jsonify({"error": f"文件不存在：{select}"}), 404
        os.makedirs(target_dir, exist_ok=True)
        opened_dir = target_dir
        highlight = full
    else:
        opened_dir = DEFAULT_OUT
        highlight = None

    try:
        system = platform.system()
        if system == "Windows":
            if highlight:
                # explorer /select,"path" 高亮指定文件 + 打开父目录
                subprocess.Popen(["explorer", f"/select,{highlight}"])
            else:
                os.startfile(opened_dir)  # type: ignore[attr-defined]
        elif system == "Darwin":
            # macOS：用 `open -R` 高亮文件，否则 `open` 打开目录
            if highlight:
                subprocess.Popen(["open", "-R", highlight])
            else:
                subprocess.Popen(["open", opened_dir])
        else:  # Linux
            # Linux 没有原生高亮，只能打开目录
            subprocess.Popen(["xdg-open", opened_dir])
        return jsonify({
            "ok": True,
            "opened": opened_dir,
            "highlight": highlight,
            "platform": system,
        })
    except Exception as e:
        return jsonify({"error": f"打开失败：{e}"}), 500


@app.route("/api/author/detail/progress")
def detail_progress():
    """v3.0.4+：返回阶段 2 异步任务进度。v3.0.7+ 兼容单文件/批量。"""
    job_id = request.args.get("job_id", "").strip()
    if not job_id:
        return jsonify({"error": "job_id 必填"}), 400
    job = _DETAIL_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "no such job"}), 404
    with _DETAIL_LOCK:
        # v3.0.7+：兼容批量任务（filenames 列表）和单文件任务（filename）
        return jsonify({
            "id": job["id"],
            "filename": job.get("filename") or (job.get("filenames", [None])[0] if job.get("filenames") else None),
            "filenames": job.get("filenames"),       # v3.0.7+
            "is_batch": job.get("sub_total", 0) > 1,  # v3.0.7+
            "sub_total": job.get("sub_total", 0),
            "sub_done": job.get("sub_done", 0),
            "sub_current": job.get("sub_current", ""),
            "status": job["status"],
            "total": job["total"],
            "processed": job["processed"],
            "ok_count": job["ok_count"],
            "fail_count": job["fail_count"],
            "current": job["current"],
            "log_tail": list(job["log"][-30:]),
            "xlsx_path": job.get("xlsx_path", ""),
            "xlsx_paths": job.get("xlsx_paths", []),  # v3.0.7+
            "errors": job.get("errors", []),
            "error": job["error"],
            "interval_ms": job.get("interval_ms", 0),  # v3.0.9+：回显
        })


@app.route("/api/author/files")
def author_files():
    """v2.9.0+：列出 output/ 里所有阶段 1 导出的 author_*.csv 列表（供阶段 2 选择）。

    v3.0.1+：增加"分组"字段（按 mtime 算：今天/昨天/本周/更早），前端可折叠。
    """
    if not os.path.isdir(DEFAULT_OUT):
        return jsonify({"files": []})
    files = []
    now = time.time()
    one_day = 86400
    for name in sorted(os.listdir(DEFAULT_OUT), reverse=True):
        if name.startswith("author_") and name.endswith(".csv"):
            full = os.path.join(DEFAULT_OUT, name)
            mtime = os.path.getmtime(full)
            age = now - mtime
            if age < one_day:
                group = "今天"
            elif age < 2 * one_day:
                group = "昨天"
            elif age < 7 * one_day:
                group = "本周"
            else:
                group = "更早"
            files.append({
                "name": name,
                "size": os.path.getsize(full),
                "mtime": mtime,
                "group": group,
            })
    return jsonify({"files": files})


@app.route("/api/author/files/<path:filename>", methods=["DELETE"])
def author_file_delete(filename):
    """v3.0.1+：删除单个文件（限定在 output/ 目录，支持子目录如 xlsx/）。

    用途：清除测试残留 / 不需要的历史 CSV。
    """
    filename = filename.replace("\\", "/")
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "非法路径"}), 400
    # 用 safe_join 防穿越
    from werkzeug.security import safe_join
    full = safe_join(DEFAULT_OUT, filename)
    if full is None or not os.path.isfile(full):
        return jsonify({"error": f"文件不存在：{filename}"}), 404
    try:
        os.remove(full)
        return jsonify({"ok": True, "deleted": filename})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/author/files/delete-batch", methods=["POST"])
def author_files_delete_batch():
    """v3.0.2+：批量删除文件（路径输入 + 通配符）。

    Body:
      paths: ["author_53456_20260821_210424.csv", "xlsx/*.xlsx", "author_*.csv"]
      每行一个 / 也支持列表形式

    通配符语法（fnmatch）：
      *  匹配任意字符（不含 /）
      ?  匹配单个字符
      [seq] 匹配 seq 中任一字符

    返回：
      { "deleted": [..], "failed": [{"path": "..", "error": ".."}], "total": N }

    用途：一次性清理多个测试残留（比"一个个点删除"快）。
    """
    import fnmatch

    data = request.get_json(force=True, silent=True) or {}
    raw_paths = data.get("paths", [])
    if isinstance(raw_paths, str):
        # 支持多行字符串（每行一个）
        raw_paths = [line.strip() for line in raw_paths.splitlines() if line.strip()]
    elif not isinstance(raw_paths, list):
        return jsonify({"error": "paths 必须是字符串（多行）或列表"}), 400
    if not raw_paths:
        return jsonify({"error": "paths 不能为空"}), 400

    deleted: list = []
    failed: list = []

    from werkzeug.security import safe_join
    for raw in raw_paths:
        raw = raw.replace("\\", "/").strip()
        if not raw or ".." in raw or raw.startswith("/"):
            failed.append({"path": raw, "error": "非法路径"})
            continue
        # 如果是通配符（包含 * 或 ? 或 [）→ 用 fnmatch 匹配 output/ 下所有文件
        if any(c in raw for c in "*?["):
            # 取目录部分（不含 *）和文件名 pattern
            base_dir = os.path.dirname(raw)
            pattern = os.path.basename(raw)
            scan_dir = safe_join(DEFAULT_OUT, base_dir) if base_dir else DEFAULT_OUT
            if scan_dir is None or not os.path.isdir(scan_dir):
                failed.append({"path": raw, "error": "目录不存在"})
                continue
            matched_any = False
            for fname in sorted(os.listdir(scan_dir)):
                if fnmatch.fnmatch(fname, pattern):
                    full = os.path.join(scan_dir, fname)
                    if os.path.isfile(full):
                        rel = os.path.relpath(full, DEFAULT_OUT).replace("\\", "/")
                        try:
                            os.remove(full)
                            deleted.append(rel)
                            matched_any = True
                        except OSError as e:
                            failed.append({"path": rel, "error": str(e)})
            if not matched_any:
                failed.append({"path": raw, "error": "通配符未匹配任何文件"})
        else:
            # 单文件删除
            full = safe_join(DEFAULT_OUT, raw)
            if full is None or not os.path.isfile(full):
                failed.append({"path": raw, "error": "文件不存在"})
                continue
            try:
                os.remove(full)
                deleted.append(raw)
            except OSError as e:
                failed.append({"path": raw, "error": str(e)})

    return jsonify({
        "deleted": deleted,
        "failed": failed,
        "total": len(deleted) + len(failed),
    })


@app.route("/api/jobs", methods=["POST"])
def create_job():
    data = request.get_json(force=True, silent=True) or {}
    targets = (data.get("targets") or "").strip()
    if not targets:
        return jsonify({"error": "targets 不能为空"}), 400
    options = {
        "delay": data.get("delay", 0.5),
        "retry": data.get("retry", 1),
        "timeout": data.get("timeout", 10.0),
        "no_cache": bool(data.get("no_cache", False)),
        "allow_bare_numbers": bool(data.get("allow_bare_numbers", False)),
        "max_age": data.get("max_age", "1h"),
        "dedupe": bool(data.get("dedupe", True)),
        "exclude_invalid": bool(data.get("exclude_invalid", False)),
        "fetch_articles": bool(data.get("fetch_articles", True)),
        "fetch_bangumi": bool(data.get("fetch_bangumi", True)),
    }
    job_id = uuid.uuid4().hex[:12]
    job = Job(job_id, targets, options)
    with _JOBS_LOCK:
        _JOBS[job_id] = job
    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()
    return jsonify({"id": job_id})


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    job = _JOBS.get(job_id)
    if not job:
        return jsonify({"error": "no such job"}), 404
    return jsonify(job.snapshot())


@app.route("/api/jobs/<job_id>/stream")
def stream_job(job_id):
    """SSE 流：每 0.5s 推一次状态。"""
    job = _JOBS.get(job_id)
    if not job:
        return jsonify({"error": "no such job"}), 404

    def gen():
        last_idx = 0
        while True:
            with job._lock:
                # 有新 log 时优先推送 log
                new_logs = job.log[last_idx:]
                payload = {
                    "status": job.status,
                    "processed": job.processed,
                    "total": job.total,
                    "ok_count": job.ok_count,
                    "failed_count": job.failed_count,
                    "from_cache": job.from_cache,
                    "new_logs": list(new_logs),
                }
                last_idx = len(job.log)
                done = job.status in ("done", "error")
            yield f"data: {_sse_json(payload)}\n\n"
            if done:
                break
            time.sleep(0.5)

    return Response(gen(), mimetype="text/event-stream")


def _sse_json(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


@app.route("/api/outputs/<path:filename>")
def download_output(filename):
    """导出文件下载（限定在 output 目录，支持子目录如 xlsx/）。

    v3.0.1+：path 风格支持子路径（如 xlsx/author_detail_xxx.xlsx）。
    Flask send_from_directory 自身用 safe_join 防 `..` 穿越。
    """
    # 反斜杠转正斜杠（Windows 路径兼容）
    filename = filename.replace("\\", "/")
    # 防御性检查（send_from_directory 也有，这里双保险）
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "非法路径"}), 400
    return send_from_directory(DEFAULT_OUT, filename, as_attachment=True)


@app.route("/api/cache/stats")
def cache_stats():
    """v2.8.0：返回 3 类 cache 的总统计。"""
    total = {"total": 0, "ok": 0, "failed": 0}
    paths = []
    for label, path in [
        ("视频", DEFAULT_CACHE),
        ("专栏", DEFAULT_CACHE_ARTICLE),
        ("番剧", DEFAULT_CACHE_BANGUMI),
    ]:
        if os.path.exists(path):
            try:
                c = Cache(path)
                s = c.stats()
                total["total"] += s["total"]
                total["ok"] += s["ok"]
                total["failed"] += s["failed"]
                paths.append(path)
            except Exception:
                pass
    if not paths:
        return jsonify({"exists": False, "stats": {"total": 0, "ok": 0, "failed": 0}})
    return jsonify({"exists": True, "stats": total, "paths": paths})


@app.route("/api/cache", methods=["DELETE"])
def cache_clear():
    """v2.8.0：清空所有 3 类 cache。"""
    for p in (DEFAULT_CACHE, DEFAULT_CACHE_ARTICLE, DEFAULT_CACHE_BANGUMI):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError as e:
                return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


# ============================================================================
# v3.0+ UAPI 集成：provider 切换 + 降级链
# ============================================================================

# 可用 provider 元信息（前端展示用）
AVAILABLE_PROVIDERS = [
    {
        "id": "self-wbi",
        "name": "自主 WBI（v2.9.1+ 默认）",
        "description": "调用 B 站官方 /x/space/wbi/arc/search 端点，带 WBI 签名",
        "requires_key": False,
        "is_visitor_ok": True,
        "credit_cost": "免费（但受 B 站风控）",
        "rate_limit": "无明确限制（受 B 站风控）",
        "cache": "无服务端缓存（实时数据）",
        "data_limit": "B 站空间页最多 1000 条（理论），实际通常 200-500 条",
        "risk": "受 B 站风控直接打击。当前网络环境可能 -799 / 412。",
        "recommended_interval_ms": 300,  # v3.0.9+：默认翻页间隔（self-wbi 旧默认 0.3s）
    },
    {
        "id": "uapis.cn",
        "name": "uapis.cn 访客 / 登录",
        "description": "国产第三方聚合 API（uapis.cn / UApiPro）",
        "requires_key": False,  # 访客模式不需要 key
        "is_visitor_ok": True,
        "credit_cost": "4 积分/次（B 站 5 端点都同价）",
        "rate_limit": "访客 4 QPS / 登录 7 QPS / 资源包 10-30 QPS",
        "cache": "15 分钟（命中后按半价 0 积分）",
        # v3.0.8+：uapis 数据完整性是动态的（按 UP 主 / 时间窗口变）
        # - 活跃 UP 主（春山响 1751577265）：能拿 ~900/983 (91.5%)
        # - 老 UP 主（Warma 53456）：通常 ~140-160/262 (53-61%)
        # - 4 QPS 间隔够慢时上限 ≈ 1000；太快被限速
        # - 2019 年前数据视 UP 主而定（Warma 缺 2015-2018）
        "data_limit": (
            "动态限制：活跃 UP 主 ~90%+ 数据，老 UP 主 ~50-60%（Warma 140/262）。"
            "4 QPS 间隔能拿更多；太快会被限速。"
        ),
        "risk": (
            "数据过第三方服务器（UID 暴露）。"
            "访客按 IP 计算额度，切网络会重置。"
            "15 分钟缓存，最新视频可能滞后。"
            "数据量依赖 UP 主活跃度。"
        ),
        # v3.0.9+：根据档位推荐间隔（FAQ Q13）
        # - 访客 4 QPS → 250ms；登录 7 QPS → 142ms
        # - Q15 推荐 ≥ 1500ms/次（保守值，适合生产）
        "recommended_interval_ms": 250,
    },
    {
        "id": "self-legacy",
        "name": "旧端点（最末位降级）",
        "description": "B 站旧 /x/space/arc/search 端点（无 WBI 签名）",
        "requires_key": False,
        "is_visitor_ok": True,
        "credit_cost": "免费",
        "rate_limit": "无明确限制（B 站风控严）",
        "cache": "无服务端缓存",
        "data_limit": "B 站风控严，5 个 UP 主后必触发 -799",
        "risk": "B 站 2024 加了风控，5 个 UP 主后必触发 -799。仅作最末位降级。",
        "recommended_interval_ms": 250,
    },
]


def _build_provider(
    provider_id: str,
    api_key: str = None,
    interval_ms: int = 250,
    disable_cache: bool = False,  # v3.1.0+ Q12
):
    """根据 provider_id + api_key 构造 provider 实例。

    v3.0.9+：interval_ms 透传给 provider（控制翻页间隔，避开 429 / -799）
    v3.1.0+：disable_cache 透传给 provider（Q12 绕过服务端缓存）

    返回 (provider, error_message)：
      - provider: ArchiveProvider 实例 或 None
      - error_message: 错误描述 或 None
    """
    from bilibili_tool import (
        UapisCnProvider,
        SelfWbiProvider,
        SelfLegacyProvider,
        UapiAuthError,
    )
    try:
        if provider_id == "self-wbi":
            return SelfWbiProvider(interval_ms=interval_ms), None
        if provider_id == "self-legacy":
            return SelfLegacyProvider(interval_ms=interval_ms), None
        if provider_id == "uapis.cn":
            return UapisCnProvider(
                api_key=api_key or None, interval_ms=interval_ms,
                disable_cache=disable_cache,
            ), None
        return None, f"未知 provider: {provider_id!r}"
    except UapiAuthError as e:
        return None, f"密钥错误: {e}"
    except Exception as e:
        return None, f"provider 初始化失败: {e}"


def _build_chain(
    provider_id: str,
    api_key: str = None,
    interval_ms: int = 250,
    disable_cache: bool = False,  # v3.1.0+ Q12
):
    """根据 provider_id 构造降级链。

    - "self-wbi" → [self-wbi, uapis.cn(访客或登录), self-legacy]
    - "uapis.cn" → [uapis.cn(访客或登录), self-wbi, self-legacy]
    - "self-legacy" → [self-legacy, self-wbi, uapis.cn(访客或登录)]
    - "auto" → [self-wbi, uapis.cn(访客), self-legacy]（默认，智能降级）

    v3.0.9+：interval_ms 透传给所有 provider（控制翻页间隔）
    v3.1.0+：disable_cache 透传给所有 uapis.cn provider（Q12 绕过缓存）

    返回 (chain, error_message)
    """
    from bilibili_tool import (
        AuthorArchiveChain,
        UapisCnProvider,
        SelfWbiProvider,
        SelfLegacyProvider,
        UapiAuthError,
    )
    try:
        # 构造主 provider
        if provider_id == "self-wbi":
            primary = SelfWbiProvider(interval_ms=interval_ms)
        elif provider_id == "self-legacy":
            primary = SelfLegacyProvider(interval_ms=interval_ms)
        elif provider_id == "uapis.cn":
            primary = UapisCnProvider(
                api_key=api_key or None, interval_ms=interval_ms,
                disable_cache=disable_cache,
            )
        else:
            # "auto" 或其他 → 用 uapis 访客作主路径（受网络影响最小）
            primary = UapisCnProvider(
                api_key=api_key or None, interval_ms=interval_ms,
                disable_cache=disable_cache,
            )
        # 构造备选（按"最常用兜底"顺序）
        uapis_visitor = UapisCnProvider(interval_ms=interval_ms, disable_cache=disable_cache)
        return AuthorArchiveChain([
            primary, uapis_visitor, SelfLegacyProvider(interval_ms=interval_ms),
        ]), None
    except UapiAuthError as e:
        return None, f"密钥错误: {e}"
    except Exception as e:
        return None, f"chain 初始化失败: {e}"


@app.route("/api/author/providers")
def list_providers():
    """v3.0+：返回可用 provider 列表 + 元信息（前端展示用）。"""
    return jsonify({"providers": AVAILABLE_PROVIDERS})


@app.route("/api/author/list", methods=["POST"])
def author_list():
    """v3.0+ 阶段 1：拉取 UP 主视频列表 + 导出 CSV（支持 provider 切换 + 降级链）。"""
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("inputs") or "").strip()
    if not text:
        return jsonify({"error": "请至少输入 1 个 UP 主（UID / space 链接 / 短链）"}), 400

    uids = _parse_uids_from_input(text)
    if not uids:
        return jsonify({"error": "未识别到任何 UP 主 UID"}), 400

    # v3.0+ provider 切换
    provider_id = data.get("provider", "auto")
    api_key = (data.get("api_key") or "").strip() or None
    # v3.0.9+ 翻页间隔：默认 250ms（4 QPS，对应 uapis 访客档位）
    interval_ms = int(data.get("interval_ms", 250))
    if interval_ms < 0:
        interval_ms = 0
    # v3.1.0+ Q12：disable_cache 绕过 15 分钟服务端缓存
    disable_cache = bool(data.get("disable_cache", False))

    try:
        since_dt = None
        until_dt = None
        if data.get("since"):
            since_dt = datetime.strptime(data["since"], "%Y-%m-%d")
        if data.get("until"):
            until_dt = datetime.strptime(data["until"], "%Y-%m-%d")
        # v3.0.3+：unlimited=true 显式不限时间（避开默认 7 天）
        unlimited = bool(data.get("unlimited", False))
        days = data.get("days")
        if unlimited:
            days = None  # 显式不限
        elif days is not None and str(days) != "":
            days = int(days)
            if days == 0:
                days = None  # 0 = 不限
        elif since_dt is None:
            days = 7  # 默认（仅在用户没填时才用 7）
        max_count = data.get("max")
        if max_count is not None:
            max_count = int(max_count)
        timeout = float(data.get("timeout", 10.0))

        chain, err = _build_chain(
            provider_id, api_key,
            interval_ms=interval_ms, disable_cache=disable_cache,
        )
        if err:
            return jsonify({"error": err}), 400

        results = []
        from bilibili_tool import UapiError, AuthorListExporter
        for uid in uids:
            try:
                # v3.0+ 用 chain 替代直接用 AuthorVideoFetcher
                # v3.0.5+：unlimited=True 时 chain 内部把 days/since/until 全部设 None
                archives = chain.fetch_author_archives(
                    uid=uid, days=days, max_count=max_count,
                    since=since_dt, until=until_dt,
                    unlimited=unlimited,
                )
                # 用 AuthorListExporter 写 CSV（v3.0+ 新增 archives= 参数）
                exporter = AuthorListExporter(output_dir=DEFAULT_OUT)
                csv_path, count = exporter.export(uid=uid, archives=archives)
                # v3.0.5+：传递完整性元信息给前端
                result_item = {
                    "uid": uid, "count": count,
                    "path": os.path.basename(csv_path),
                    "source": archives[0].get("_source", "unknown") if archives else "empty",
                }
                if archives and "_completeness" in archives[0]:
                    result_item["completeness"] = archives[0]["_completeness"]
                    result_item["chain_provider"] = archives[0].get("_chain", "")
                    result_item["provider_total"] = archives[0].get("_provider_total")
                    result_item["actual_count"] = archives[0].get("_actual_count")
                results.append(result_item)
            except UapiError as e:
                results.append({"uid": uid, "error": f"[UAPI] {e}"})
            except Exception as e:
                results.append({"uid": uid, "error": str(e)})
        return jsonify({
            "uids": uids, "results": results,
            "provider": provider_id,
            "has_key": bool(api_key),
            "interval_ms": interval_ms,  # v3.0.9+：回显给前端
            "disable_cache": disable_cache,  # v3.1.0+：回显
        })
    except ValueError as e:
        return jsonify({"error": f"日期格式错误：{e}"}), 400


# ============================================================================
# v3.0.6+ UP 主主页信息批量抓取
# ============================================================================
# 设计：
#   - 输入：多个 UID / space 链接 / b23.tv 短链（复用现有 parser）
#   - 抓取：每个 UP 主的 userinfo（mid/name/face/sign/level/follower/archive_count...）
#   - 数据源：uapis.cn（v3.0.6 唯一支持 userinfo 的 provider；self-wbi 不支持）
#   - 导出：CSV（每行一个 UP 主）+ XLSX（单 sheet，列对齐 CSV）
#   - 进度：复用 _DETAIL_JOBS 异步模式（v3.0.4）

_PROFILE_JOBS: Dict[str, dict] = {}


# v3.1.0+ 实时额度查询（Q26）
@app.route("/api/author/usage", methods=["POST"])
def author_usage():
    """v3.1.0+：查询 uapis.cn 当前剩余积分 / QPS 状态。

    Body:
      api_key: 可选（uapis key，无则按访客查）
      disable_cache: bool（v3.1.0+ Q12）

    返回：
      {
        "ok": True,
        "usage": {...原始 uapis 响应...},
        "interval_ms": 0,
        "disable_cache": false,
      }
      或失败：
      {"ok": False, "error": "..."}

    端点：GET https://uapis.cn/api/v1/status/usage
    文档：https://uapis.cn/docs/api-reference/get-status-usage
    消耗：0 积分（免费端点，可频繁调用）
    """
    data = request.get_json(force=True, silent=True) or {}
    api_key = (data.get("api_key") or "").strip() or None
    disable_cache = bool(data.get("disable_cache", False))

    from bilibili_tool.uapi import UapisCnProvider, UapiError
    try:
        provider = UapisCnProvider(api_key=api_key, disable_cache=disable_cache)
        usage = provider.fetch_usage()
        return jsonify({
            "ok": True,
            "usage": usage,
            "mode": provider.mode,  # "visitor" / "logged_in"
            "disable_cache": disable_cache,
        })
    except UapiError as e:
        # 友好错误信息（含 docs 跳转链接如果服务端返回了）
        err_resp = {
            "ok": False,
            "error": str(e),
            "code": e.code,
            "status_code": e.status_code,
        }
        if e.docs:
            err_resp["docs"] = e.docs
        return jsonify(err_resp), 500
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"查询失败：{e}",
        }), 500


@app.route("/api/author/profile", methods=["POST"])
def author_profile():
    """v3.0.6+：批量抓取 UP 主主页信息（userinfo）。

    Body:
      inputs: "53456\\n483307278\\nhttps://space.bilibili.com/1751577265"
      api_key: 可选（uapis key）
    """
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("inputs") or "").strip()
    if not text:
        return jsonify({"error": "请输入至少 1 个 UP 主（UID / space 链接 / 短链）"}), 400

    uids = _parse_uids_from_input(text)
    if not uids:
        return jsonify({"error": "未识别到任何 UP 主 UID"}), 400

    api_key = (data.get("api_key") or "").strip() or None
    # v3.0.9+：interval_ms 优先于 delay（统一翻页/单点间隔）
    # 后向兼容：旧 delay 参数仍可用，缺省 0.3s
    interval_ms = data.get("interval_ms")
    if interval_ms is not None:
        interval_ms = max(0, int(interval_ms))
        delay = interval_ms / 1000.0
    else:
        delay = float(data.get("delay", 0.3))  # userinfo 比 archives 轻，间隔小

    # 创建任务
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "kind": "profile",
        "input": text,
        "uids": uids,
        "status": "pending",
        "total": len(uids),
        "processed": 0,
        "ok_count": 0,
        "fail_count": 0,
        "current": "",
        "log": [],
        "profiles": [],          # 抓到的 profile 列表
        "csv_path": "",
        "xlsx_path": "",
        "error": "",
        "created_at": datetime.now().strftime("%H:%M:%S"),
        "has_key": bool(api_key),
        "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),  # v3.0.9+ 回显
    }
    _PROFILE_JOBS[job_id] = job
    t = threading.Thread(
        target=_run_profile_job,
        args=(job, uids, api_key, delay),
        daemon=True,
    )
    t.start()
    return jsonify({
        "job_id": job_id,
        "total": len(uids),
        "uids": uids,
        "interval_ms": int(interval_ms) if interval_ms is not None else int(delay * 1000),
    })


def _run_profile_job(job, uids, api_key, delay):
    """v3.0.6+：后台抓取每个 UP 主的 userinfo。"""
    try:
        job["status"] = "running"
        with _PROFILE_LOCK:
            job["log"].append(f"[{job['created_at']}] 启动：{len(uids)} 个 UP 主")

        from bilibili_tool.uapi import UapisCnProvider
        provider = UapisCnProvider(api_key=api_key)

        for i, uid in enumerate(uids, 1):
            try:
                info = provider.fetch_user_info(uid)
                # 归一化字段
                profile = {
                    "uid": uid,
                    "name": info.get("name", ""),
                    "level": info.get("level", 0),
                    "sex": info.get("sex", ""),
                    "sign": info.get("sign", ""),
                    "follower": info.get("follower", 0),
                    "following": info.get("following", 0),
                    "archive_count": info.get("archive_count", 0),
                    "article_count": info.get("article_count", 0),
                    "vip_type": info.get("vip_type", 0),
                    "vip_status": info.get("vip_status", 0),
                    "birthday": info.get("birthday", ""),
                    "face": info.get("face", ""),
                    "source": "uapis.cn",
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                job["profiles"].append(profile)
                job["ok_count"] += 1
                job["current"] = profile["name"] or str(uid)
                with _PROFILE_LOCK:
                    job["log"].append(
                        f"  [{i:3d}/{len(uids)}] OK uid={uid} name={profile['name']!r} "
                        f"follower={profile['follower']} archives={profile['archive_count']}"
                    )
            except Exception as e:
                job["fail_count"] += 1
                job["current"] = f"uid={uid} (失败)"
                with _PROFILE_LOCK:
                    job["log"].append(f"  [{i:3d}/{len(uids)}] FAIL uid={uid}: {e}")
            job["processed"] = i
            with _PROFILE_LOCK:
                if len(job["log"]) > 500:
                    job["log"] = job["log"][-500:]
            if i < len(uids) and delay > 0:
                time.sleep(delay)

        # 写 CSV
        if job["profiles"]:
            import csv
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_name = f"profiles_{ts}.csv"
            csv_path = os.path.join(DEFAULT_OUT, csv_name)
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "uid", "name", "level", "sex", "sign",
                    "follower", "following", "archive_count", "article_count",
                    "vip_type", "vip_status", "birthday", "source", "fetched_at",
                ])
                for p in job["profiles"]:
                    writer.writerow([
                        p["uid"], p["name"], p["level"], p["sex"], p["sign"],
                        p["follower"], p["following"], p["archive_count"],
                        p["article_count"], p["vip_type"], p["vip_status"],
                        p["birthday"], p["source"], p["fetched_at"],
                    ])
            job["csv_path"] = os.path.basename(csv_path)
            with _PROFILE_LOCK:
                job["log"].append(f"  [CSV] {job['csv_path']} ({len(job['profiles'])} 行)")

            # 写 XLSX（单 sheet，列对齐 CSV）
            try:
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws.title = "UP 主主页"
                ws.append([
                    "UID", "昵称", "等级", "性别", "签名",
                    "粉丝数", "关注数", "投稿数", "专栏数",
                    "VIP类型", "VIP状态", "生日", "数据源", "抓取时间",
                ])
                for p in job["profiles"]:
                    ws.append([
                        p["uid"], p["name"], p["level"], p["sex"], p["sign"],
                        p["follower"], p["following"], p["archive_count"],
                        p["article_count"], p["vip_type"], p["vip_status"],
                        p["birthday"], p["source"], p["fetched_at"],
                    ])
                # 列宽
                widths = [10, 20, 6, 6, 40, 10, 10, 8, 8, 8, 8, 8, 12, 18]
                for i, w in enumerate(widths, 1):
                    ws.column_dimensions[chr(64 + i)].width = w
                os.makedirs(DEFAULT_XLSX, exist_ok=True)
                xlsx_name = f"profiles_{ts}.xlsx"
                xlsx_path = os.path.join(DEFAULT_XLSX, xlsx_name)
                wb.save(xlsx_path)
                rel = os.path.relpath(xlsx_path, DEFAULT_OUT).replace("\\", "/")
                job["xlsx_path"] = rel
                with _PROFILE_LOCK:
                    job["log"].append(f"  [XLSX] {rel}")
            except ImportError:
                # openpyxl 不存在（理论上 bilibili_tool 已装）
                with _PROFILE_LOCK:
                    job["log"].append("  [WARN] openpyxl 未装，跳过 XLSX")

        job["status"] = "done"
        with _PROFILE_LOCK:
            job["log"].append(
                f"  [完成] {job['ok_count']} 成功 / {job['fail_count']} 失败"
            )
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        with _PROFILE_LOCK:
            job["log"].append(f"  [异常] {e}")


_PROFILE_LOCK = threading.Lock()


@app.route("/api/author/profile/progress")
def profile_progress():
    """v3.0.6+：返回主页抓取进度。"""
    job_id = request.args.get("job_id", "").strip()
    if not job_id:
        return jsonify({"error": "job_id 必填"}), 400
    job = _PROFILE_JOBS.get(job_id)
    if not job:
        return jsonify({"error": "no such job"}), 404
    with _PROFILE_LOCK:
        return jsonify({
            "id": job["id"],
            "uids": job["uids"],
            "status": job["status"],
            "total": job["total"],
            "processed": job["processed"],
            "ok_count": job["ok_count"],
            "fail_count": job["fail_count"],
            "current": job["current"],
            "log_tail": list(job["log"][-30:]),
            "csv_path": job["csv_path"],
            "xlsx_path": job["xlsx_path"],
            "error": job["error"],
            "has_key": job["has_key"],
            "interval_ms": job.get("interval_ms", 0),  # v3.0.9+：回显
        })


@app.route("/api/author/profile/files")
def profile_files():
    """v3.0.6+：列出已导出的 profiles_*.csv 列表。"""
    if not os.path.isdir(DEFAULT_OUT):
        return jsonify({"files": []})
    files = []
    for name in sorted(os.listdir(DEFAULT_OUT), reverse=True):
        if name.startswith("profiles_") and name.endswith(".csv"):
            full = os.path.join(DEFAULT_OUT, name)
            files.append({
                "name": name,
                "size": os.path.getsize(full),
                "mtime": os.path.getmtime(full),
            })
    return jsonify({"files": files})

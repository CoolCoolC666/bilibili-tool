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
            "title": a.title,
            "author_name": a.author_name,
            "author_mid": a.author_mid,
            "view": a.view,
            "like": a.like,
            "coin": a.coin,
            "favorite": a.favorite,
            "share": a.share,
            "reply": a.reply,
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
    return ArticleInfo(input_kind=p.kind, cv_id=p.value, raw_input=p.raw)


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
    """导出文件下载（限定在 output 目录）。"""
    safe = os.path.basename(filename)
    return send_from_directory(DEFAULT_OUT, safe, as_attachment=True)


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


if __name__ == "__main__":
    print(f"🚀 Bilibili Tool Web  http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)

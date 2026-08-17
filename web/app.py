"""Flask Web 应用：把 bilibili_tool 包成一个本地网页工具。

启动：python run_web.py  → http://127.0.0.1:5050
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)

from bilibili_tool import (
    BilibiliVideoFetcher,
    Cache,
    expand_short_urls,
    export_all,
    parse_text,
)
from bilibili_tool.cache import parse_duration
from bilibili_tool.models import VideoInfo


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_CACHE = os.path.join(ROOT, "data", "cache.json")
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
        self.results: List[VideoInfo] = []
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
                "results": [self._public(r) for r in self.results],
                "outputs": self.outputs,
                "error": self.error,
            }

    @staticmethod
    def _public(v: VideoInfo) -> dict:
        return {
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


_JOBS: Dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _run_job(job: Job) -> None:
    """后台线程：实际抓取逻辑。"""
    try:
        job.status = "running"
        job.push_log(f"任务启动：{job.targets[:80]}{'...' if len(job.targets) > 80 else ''}")

        parsed = parse_text(job.targets, allow_bare_numbers=job.options.get("allow_bare_numbers", False))
        if not parsed:
            job.status = "error"
            hint = ""
            if not job.options.get("allow_bare_numbers", False):
                hint = "（如果输入里全是数字，勾选「允许识别裸数字为 AV 号」再试）"
            job.error = f"未识别到任何 AV / BV / URL。{hint}"
            job.push_log("❌ " + job.error)
            return

        # 短链展开
        parsed = expand_short_urls(parsed)
        if not parsed:
            job.status = "error"
            job.error = "短链解析后无有效 ID。"
            job.push_log("❌ " + job.error)
            return

        job.total = len(parsed)
        job.push_log(f"解析到 {job.total} 个目标")

        cache = Cache(DEFAULT_CACHE) if not job.options.get("no_cache") else None
        fetcher = BilibiliVideoFetcher(
            max_retries=int(job.options.get("retry", 1)),
            timeout=float(job.options.get("timeout", 10.0)),
        )
        delay = float(job.options.get("delay", 0.5))
        if job.options.get("no_cache"):
            max_age_seconds = 0
            max_age_desc = "0（不用缓存）"
        else:
            max_age_seconds = parse_duration(job.options.get("max_age", "1h"))
            if max_age_seconds is None:
                max_age_seconds = 3600
            max_age_desc = job.options.get("max_age", "1h")
        job.push_log(f"缓存策略: max-age = {max_age_desc}（静态字段永远，失败状态永远）")

        for i, p in enumerate(parsed, 1):
            sk = VideoInfo(
                input_kind=p.kind,
                bvid=p.value if p.kind == "bv" else "",
                aid=int(p.value) if p.kind == "av" else 0,
                raw_input=p.raw,
            )
            if cache is not None:
                cached = cache.get_fresh(sk, max_age_seconds=max_age_seconds)
                if cached:
                    job.results.append(cached)
                    job.from_cache += 1
                    job.processed += 1
                    if cached.is_ok:
                        job.ok_count += 1
                    else:
                        job.failed_count += 1
                    age_hint = ""
                    if cached.status == "ok" and cached.fetched_at:
                        try:
                            from datetime import datetime as _dt
                            fetched = _dt.strptime(cached.fetched_at, "%Y-%m-%d %H:%M:%S")
                            age_sec = (_dt.now() - fetched).total_seconds()
                            if age_sec < 60:
                                age_hint = f"（{int(age_sec)}秒前抓的）"
                            elif age_sec < 3600:
                                age_hint = f"（{int(age_sec/60)}分钟前抓的）"
                            else:
                                age_hint = f"（{int(age_sec/3600)}小时前抓的）"
                        except ValueError:
                            pass
                    job.push_log(
                        f"  [{i}/{job.total}] ↪ cache {p.value} -> {cached.status} {age_hint}"
                    )
                    continue

            job.push_log(f"  [{i}/{job.total}] → 请求 {p.value} ...")
            info = fetcher.fetch_with_retry(p)
            job.results.append(info)
            job.processed += 1
            if info.is_ok:
                job.ok_count += 1
                job.push_log(f"  [{i}/{job.total}] ✓ {info.title[:28]}")
            else:
                job.failed_count += 1
                job.push_log(
                    f"  [{i}/{job.total}] ✗ {p.value} {info.status} code={info.api_code} {info.error}"
                )
            if cache is not None:
                cache.put(info)
            if i < job.total and delay > 0:
                time.sleep(delay)

        if cache is not None:
            try:
                cache.save()
                job.push_log(f"💾 缓存已保存: {DEFAULT_CACHE}")
            except OSError as e:
                job.push_log(f"⚠ 缓存保存失败: {e}")

        # 导出
        try:
            base = f"web_{job.id[:8]}_{datetime.now().strftime('%H%M%S')}"
            saved = export_all(
                job.results,
                base=base,
                out_dir=DEFAULT_OUT,
                dedupe=job.options.get("dedupe", True),
                exclude_invalid=job.options.get("exclude_invalid", False),
            )
            for fmt, path in saved.items():
                job.outputs[fmt] = os.path.basename(path)
                job.push_log(f"📦 导出 {fmt}: {os.path.basename(path)}")
            n_raw = len(job.results)
            from bilibili_tool.exporter import dedupe_videos as _dedupe, filter_valid as _filt
            n_after_filter = len(_filt(job.results)) if job.options.get("exclude_invalid", False) else n_raw
            n_final = len(_dedupe(_filt(job.results) if job.options.get("exclude_invalid", False) else job.results))
            n_dedup_diff = n_after_filter - n_final
            if job.options.get("exclude_invalid", False) and n_raw != n_after_filter:
                job.push_log(f"  ↪ 排除失效：{n_raw} 条 → {n_after_filter} 条")
            if job.options.get("dedupe", True) and n_dedup_diff:
                job.push_log(f"  ↪ 去重：{n_after_filter} 条 → {n_final} 条")
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
    if not os.path.exists(DEFAULT_CACHE):
        return jsonify({"exists": False, "stats": {"total": 0, "ok": 0, "failed": 0}})
    c = Cache(DEFAULT_CACHE)
    return jsonify({"exists": True, "stats": c.stats(), "path": DEFAULT_CACHE})


@app.route("/api/cache", methods=["DELETE"])
def cache_clear():
    if os.path.exists(DEFAULT_CACHE):
        try:
            os.remove(DEFAULT_CACHE)
        except OSError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"🚀 Bilibili Tool Web  http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)

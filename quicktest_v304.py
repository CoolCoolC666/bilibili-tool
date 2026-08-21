"""v3.0.4 实时进度测试"""
import json
import time
import urllib.request


def req(method, path, body=None):
    url = f"http://127.0.0.1:5054{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# 启动抓取任务（用之前生成的 1751577265 CSV，90.6 KB，可能 ~100+ 条）
# 为了测试进度，用 max=5 减少等待时间
print("=== 1. 启动抓取任务（max=5）===")
code, body = req("POST", "/api/author/detail", {
    "filename": "author_1751577265_20260821_213245.csv",
    "max": 5, "delay": 0.5, "timeout": 8, "retry": 0,
})
print(f"status={code}")
data = json.loads(body)
print(f"  job_id: {data.get('job_id')}")
job_id = data.get("job_id")
print()

# 轮询进度
print("=== 2. 轮询进度（每 1 秒一次）===")
for i in range(15):
    time.sleep(1)
    code, body = req("GET", f"/api/author/detail/progress?job_id={job_id}")
    if code != 200:
        print(f"  轮询失败: {body}")
        break
    d = json.loads(body)
    pct = round(d['processed'] / d['total'] * 100) if d['total'] else 0
    print(f"  [{i+1:2d}s] status={d['status']}, {d['processed']}/{d['total']} ({pct}%), "
          f"OK={d['ok_count']}, FAIL={d['fail_count']}, current={d.get('current', '')[:30]!r}")
    if d['status'] in ('done', 'error'):
        print()
        print(f"  xlsx_path: {d.get('xlsx_path')}")
        print(f"  log_tail (last 3):")
        for line in d.get('log_tail', [])[-3:]:
            print(f"    {line}")
        if d['status'] == 'error':
            print(f"  error: {d.get('error')}")
        break

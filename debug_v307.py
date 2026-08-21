"""Debug: 直接跑后台线程看会抛什么"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from unittest.mock import patch


# Mock
def fake_export(self, csv_path, *, max_count=None, output_dir=None):
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%m%S")
    od = output_dir or self.output_dir
    os.makedirs(od, exist_ok=True)
    xlsx_path = os.path.abspath(os.path.join(od, f"author_detail_999_{ts}.xlsx"))
    with open(xlsx_path, "wb") as f:
        f.write(b"mock")
    time.sleep(0.3)
    return xlsx_path, 2, 0


patcher = patch("bilibili_tool.author_detail.AuthorDetailExporter.export", new=fake_export)
patcher.start()


os.chdir(r"E:\桌面\暑期可做\22-Bilibili Tool完善\Bilibili_tool\bilibili_tool_v2")

# 创建测试文件
test_files = ["author_test_v307_1.csv", "author_test_v307_2.csv", "author_test_v307_3.csv"]
for f in test_files:
    with open(os.path.join("output", f), "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("bvid,aid,title,duration,pubdate,tid,up_uid\n")
        fp.write("BV1xx1,1,test1,100,2026-01-01,0,999\n")
        fp.write("BV1xx2,2,test2,200,2026-01-01,0,999\n")

# 直接调 _run_detail_batch_job 看会抛什么
import subprocess

port = 5059
proc = subprocess.Popen(
    [sys.executable, "run_web.py", "--port", str(port)],
    cwd=".",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
for _ in range(30):
    time.sleep(0.5)
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
        break
    except Exception:
        continue


def req(method, path, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# 启动批量任务
code, body = req("POST", "/api/author/detail/batch", {
    "filenames": test_files, "max": 5, "delay": 0.1, "timeout": 5, "retry": 0,
})
data = json.loads(body)
job_id = data["job_id"]
print(f"job_id={job_id}")

# 等几秒
time.sleep(2)

# 轮询
code, body = req("GET", f"/api/author/detail/progress?job_id={job_id}")
print(f"status={code}")
print(f"body: {body[:500]}")

# 抓 Flask 输出
proc.terminate()
stdout, stderr = proc.communicate(timeout=5)
print("\n=== Flask stdout (last 2000 chars) ===")
print(stdout[-2000:])

# 清理
for f in test_files:
    try:
        os.remove(os.path.join("output", f))
    except OSError:
        pass
patcher.stop()

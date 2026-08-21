"""v3.0.1 端到端测试"""
import json
import urllib.request


def req(method, path, body=None):
    url = f"http://127.0.0.1:5051{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


print("=== 1. /api/author/files ===")
code, body = req("GET", "/api/author/files")
print(f"status={code}")
data = json.loads(body)
print(f"files: {len(data['files'])}")
for f in data["files"][:3]:
    print(f"  {f['name']} ({f['size']}B, {f['group']})")
print()

print("=== 2. /api/author/detail (max=1) ===")
code, body = req("POST", "/api/author/detail", {
    "filename": "author_53456_20260821_210424.csv",
    "max": 1, "timeout": 8, "retry": 0,
})
print(f"status={code}")
print(f"body: {body[:500]}")
print()

print("=== 3. 检查 xlsx 子目录 ===")
import os
xlsx_dir = "E:\\桌面\\暑期可做\\22-Bilibili Tool完善\\Bilibili_tool\\bilibili_tool_v2\\output\\xlsx"
if os.path.isdir(xlsx_dir):
    files = os.listdir(xlsx_dir)
    print(f"xlsx/ 目录: {len(files)} 个文件")
    for f in files:
        full = os.path.join(xlsx_dir, f)
        print(f"  {f} ({os.path.getsize(full)}B)")
else:
    print("xlsx/ 目录不存在（detail 未成功）")
print()

print("=== 4. 下载 xlsx ===")
# 从 detail 响应拿 path
try:
    d = json.loads(body)
    if "path" in d:
        xpath = d["path"]
        url = f"http://127.0.0.1:5051/api/outputs/{urllib.parse.quote(xpath, safe='/')}"
        print(f"GET {url}")
        with urllib.request.urlopen(url, timeout=10) as r:
            content = r.read()
            print(f"  status={r.status}, content-length={len(content)}")
except Exception as e:
    print(f"  FAIL: {e}")

"""v3.0.2 批量删除测试"""
import json
import urllib.request


def req(method, path, body=None):
    url = f"http://127.0.0.1:5052{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


print("=== 1. 列出文件 ===")
code, body = req("GET", "/api/author/files")
data = json.loads(body)
print(f"status={code}, files={len(data['files'])}")
for f in data["files"][:5]:
    print(f"  {f['name']} ({f['size']}B, {f['group']})")
print()

print("=== 2. 批量删除（通配符 author_483307278_*.csv）===")
code, body = req("POST", "/api/author/files/delete-batch", {
    "paths": ["author_483307278_*.csv"]
})
print(f"status={code}")
data = json.loads(body)
print(f"deleted: {data['deleted']}")
print(f"failed: {data['failed']}")
print(f"total: {data['total']}")
print()

print("=== 3. 批量删除（混合：单文件 + 通配符 + 不存在）===")
code, body = req("POST", "/api/author/files/delete-batch", {
    "paths": [
        "author_53456_20260821_210424.csv",  # 单文件
        "author_1751577265_*.csv",          # 通配符
        "nonexistent.csv",                  # 不存在
    ]
})
print(f"status={code}")
data = json.loads(body)
print(f"deleted ({len(data['deleted'])}): {data['deleted']}")
print(f"failed ({len(data['failed'])}): {data['failed']}")
print()

print("=== 4. 多行字符串（也支持）===")
code, body = req("POST", "/api/author/files/delete-batch", {
    "paths": "author_221648_*.csv\nauthor_399959326_*.csv"
})
data = json.loads(body)
print(f"status={code}, deleted: {len(data['deleted'])}, failed: {len(data['failed'])}")
print()

print("=== 5. 再列文件（应该清空很多）===")
code, body = req("GET", "/api/author/files")
data = json.loads(body)
print(f"剩余 files={len(data['files'])}")
for f in data["files"]:
    print(f"  {f['name']} ({f['size']}B)")

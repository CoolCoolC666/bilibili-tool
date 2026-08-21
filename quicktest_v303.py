"""v3.0.3 全选 / 日期快捷测试"""
import json
import urllib.request


def req(method, path, body=None):
    url = f"http://127.0.0.1:5053{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# 测试 1: 全部时间（unlimited=true）— Shuakami 应拿全 5 条
print("=== 1. unlimited=true（全部时间）===")
code, body = req("POST", "/api/author/list", {
    "inputs": "483307278",
    "provider": "uapis.cn",
    "unlimited": True,
    "max": 10,
})
print(f"status={code}")
data = json.loads(body)
if "results" in data:
    r = data["results"][0]
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")
print()

# 测试 2: 默认（不传 unlimited / days）— 应该用 days=7
print("=== 2. 默认（不传）→ 应该用 days=7 ===")
code, body = req("POST", "/api/author/list", {
    "inputs": "483307278",
    "provider": "uapis.cn",
    "max": 10,
})
print(f"status={code}")
data = json.loads(body)
if "results" in data:
    r = data["results"][0]
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")
print()

# 测试 3: days=30 显式
print("=== 3. days=30 显式 ===")
code, body = req("POST", "/api/author/list", {
    "inputs": "483307278",
    "provider": "uapis.cn",
    "days": 30,
    "max": 10,
})
data = json.loads(body)
if "results" in data:
    r = data["results"][0]
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")
print()

# 测试 4: days=0（也按不限处理）
print("=== 4. days=0（也按不限处理）===")
code, body = req("POST", "/api/author/list", {
    "inputs": "483307278",
    "provider": "uapis.cn",
    "days": 0,
    "max": 10,
})
data = json.loads(body)
if "results" in data:
    r = data["results"][0]
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")

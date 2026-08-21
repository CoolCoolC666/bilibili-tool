"""v3.0.5 完整性检查测试"""
import json
import urllib.request


def req(method, path, body=None):
    url = f"http://127.0.0.1:5055{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, method=method,
                              headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# 拉 Warma 全量
print("=== 1. 拉 Warma 53456（unlimited=true）===")
code, body = req("POST", "/api/author/list", {
    "inputs": "53456",
    "provider": "uapis.cn",
    "unlimited": True,
    "max": 200,
})
print(f"status={code}")
data = json.loads(body)
for r in data.get("results", []):
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")
    if "completeness" in r:
        print(f"    completeness={r['completeness']}, "
              f"provider_total={r.get('provider_total')}, "
              f"actual_count={r.get('actual_count')}, "
              f"chain_provider={r.get('chain_provider')}")
print()

# 对比 Shuakami（27 条左右，可能完整）
print("=== 2. 拉 Shuakami 483307278（unlimited=true，应该 5 条全）===")
code, body = req("POST", "/api/author/list", {
    "inputs": "483307278",
    "provider": "uapis.cn",
    "unlimited": True,
    "max": 200,
})
data = json.loads(body)
for r in data.get("results", []):
    print(f"  uid={r['uid']}, count={r['count']}, source={r.get('source')}")
    if "completeness" in r:
        print(f"    completeness={r['completeness']}, "
              f"provider_total={r.get('provider_total')}, "
              f"actual_count={r.get('actual_count')}")

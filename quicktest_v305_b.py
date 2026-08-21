"""v3.0.5 验证 Warma 修复后"""
import json
import urllib.request


def call(uid=53456, max_count=200):
    r = urllib.request.Request("http://127.0.0.1:5056/api/author/list", method="POST",
        data=json.dumps({"inputs": str(uid), "provider": "uapis.cn",
                         "unlimited": True, "max": max_count}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        return f"FAIL: {e}"


# 测试 Warma
print("=== Warma 53456 ===")
body = call(53456, 200)
d = json.loads(body)
for r in d.get("results", []):
    if "error" in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(f"  uid={r['uid']} count={r['count']}")
        print(f"    completeness={r.get('completeness')}")
        print(f"    provider_total={r.get('provider_total')}")
        print(f"    actual_count={r.get('actual_count')}")
        print(f"    chain={r.get('chain_provider')}")
        print(f"    path={r.get('path')}")
print()

# 测试 Shuakami（小数据，应该 OK）
print("=== Shuakami 483307278 ===")
body = call(483307278, 100)
d = json.loads(body)
for r in d.get("results", []):
    if "error" in r:
        print(f"  ERROR: {r['error']}")
    else:
        print(f"  uid={r['uid']} count={r['count']}")
        print(f"    completeness={r.get('completeness')}")
        print(f"    provider_total={r.get('provider_total')}")
        print(f"    actual_count={r.get('actual_count')}")

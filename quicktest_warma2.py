"""Warma 重测：加长间隔避免限速"""
import json
import urllib.request
import time


def req(url):
    r = urllib.request.Request(url, headers={"User-Agent": "bilibili_tool_v2/diag"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.read().decode("utf-8")


print("=" * 60)
print("Warma 53456 ps=20 翻页（间隔 0.3s = 略慢于 4 QPS）")
print("=" * 60)
total = []
for pn in range(1, 20):
    body = req(f"https://uapis.cn/api/v1/social/bilibili/archives?mid=53456&ps=20&pn={pn}")
    d = json.loads(body)
    vids = d.get("videos", [])
    if not vids:
        print(f"  pn={pn}: 空 (total={d.get('total')})")
        break
    total.extend(vids)
    print(f"  pn={pn}: total={d.get('total')}, got={len(vids)}")
    if pn * 20 >= (d.get("total") or 999999):
        print(f"  pn={pn}: total 已到达")
        break
    time.sleep(0.3)
print(f"  累计: {len(total)}")

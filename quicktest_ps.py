"""查 uapis ps=100 能不能突破 150 条限制"""
import json
import urllib.request
import datetime


def req(url):
    r = urllib.request.Request(url, headers={"User-Agent": "bilibili_tool_v2/diag"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.read().decode("utf-8")


# 测试 1: 春山响 1751577265 翻页（ps=50）
print("=" * 60)
print("春山响 1751577265 ps=50 翻页")
print("=" * 60)
total = []
for pn in range(1, 20):
    body = req(f"https://uapis.cn/api/v1/social/bilibili/archives?mid=1751577265&ps=50&pn={pn}")
    d = json.loads(body)
    vids = d.get("videos", [])
    if not vids:
        print(f"  pn={pn}: 空 (total={d.get('total')})")
        break
    total.extend(vids)
    print(f"  pn={pn}: total={d.get('total')}, got={len(vids)}")
print(f"  累计: {len(total)}")
print()

# 测试 2: 春山响 ps=100
print("=" * 60)
print("春山响 1751577265 ps=100 翻页")
print("=" * 60)
total = []
for pn in range(1, 20):
    body = req(f"https://uapis.cn/api/v1/social/bilibili/archives?mid=1751577265&ps=100&pn={pn}")
    d = json.loads(body)
    vids = d.get("videos", [])
    if not vids:
        print(f"  pn={pn}: 空 (total={d.get('total')})")
        break
    total.extend(vids)
    print(f"  pn={pn}: total={d.get('total')}, got={len(vids)}")
print(f"  累计: {len(total)}")

"""v3.0.5 改进版：分页逐页检查"""
import json
import time
import urllib.request
import datetime


def req(url):
    r = urllib.request.Request(url, headers={"User-Agent": "bilibili_tool_v2/diag"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8")


print("=" * 60)
print("Warma (53456) 全量抓取 + 分页诊断")
print("=" * 60)

# userinfo
code, body = req("https://uapis.cn/api/v1/social/bilibili/userinfo?uid=53456")
data = json.loads(body)
print(f"archive_count: {data.get('archive_count')}")
print()

# 拉 30 页（理论 30*50=1500，覆盖 262）
all_videos = []
prev_total = None
for pn in range(1, 31):
    code, body = req(f"https://uapis.cn/api/v1/social/bilibili/archives?mid=53456&ps=50&pn={pn}")
    d = json.loads(body)
    vids = d.get("videos", [])
    total = d.get("total")
    if vids:
        all_videos.extend(vids)
        earliest = min(v.get("publish_time", 0) for v in vids)
        latest = max(v.get("publish_time", 0) for v in vids)
        earliest_dt = datetime.datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
        latest_dt = datetime.datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
        print(f"  pn={pn:2d}: total={total:3d}, got={len(vids):2d}, "
              f"first={earliest_dt}, last={latest_dt}")
    else:
        print(f"  pn={pn:2d}: 空 (total={total})")
        break
    if total != prev_total:
        print(f"    [!!] total 变化: {prev_total} -> {total}")
    prev_total = total
    if len(vids) < 50:
        print(f"  pn={pn}: 不足 50 条（最后一页）")
        break
    time.sleep(0.3)

print()
print(f"实际拉取: {len(all_videos)} 条")
print(f"userinfo 报告: {data.get('archive_count')} 条")
print(f"差异: {data.get('archive_count') - len(all_videos)} 条缺失")
print()

# 时间范围
if all_videos:
    sorted_v = sorted(all_videos, key=lambda x: x.get("publish_time", 0))
    earliest = sorted_v[0]
    latest = sorted_v[-1]
    earliest_dt = datetime.datetime.fromtimestamp(earliest["publish_time"]).strftime("%Y-%m-%d")
    latest_dt = datetime.datetime.fromtimestamp(latest["publish_time"]).strftime("%Y-%m-%d")
    print(f"实际最早: {earliest.get('bvid')} {earliest.get('title', '')[:40]!r} @ {earliest_dt}")
    print(f"实际最新: {latest.get('bvid')} {latest.get('title', '')[:40]!r} @ {latest_dt}")
print()

# 检查目标 BV
print("用户提到的 BV 号：")
for bv in ["BV1gs411o7XM", "BV1gfGw6RE5p"]:
    found = next((v for v in all_videos if v.get("bvid") == bv), None)
    if found:
        pt = datetime.datetime.fromtimestamp(found["publish_time"]).strftime("%Y-%m-%d")
        print(f"  {bv}: 找到 {pt}")
    else:
        print(f"  {bv}: 未找到（不在 uapis 拉到的 {len(all_videos)} 条里）")

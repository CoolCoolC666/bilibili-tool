"""v3.0.5 数据缺失诊断 - Warma 53456"""
import json
import time
import urllib.request
import urllib.error


def req(url):
    r = urllib.request.Request(url, headers={"User-Agent": "bilibili_tool_v2/diag"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8")


print("=" * 60)
print("1. userinfo：查 Warma (53456) archive_count")
print("=" * 60)
code, body = req("https://uapis.cn/api/v1/social/bilibili/userinfo?uid=53456")
data = json.loads(body)
print(f"  name: {data.get('name')!r}")
print(f"  level: {data.get('level')}")
print(f"  follower: {data.get('follower')}")
print(f"  archive_count: {data.get('archive_count')}  ← 这是 B 站官方说 Warma 有多少投稿")
print(f"  article_count: {data.get('article_count')}")
print()

# 拉全量 archives（多页）
print("=" * 60)
print("2. archives 拉全量（pn=1..20, ps=50）")
print("=" * 60)
all_videos = []
for pn in range(1, 21):
    code, body = req("https://uapis.cn/api/v1/social/bilibili/archives?mid=53456&ps=50&pn=" + str(pn))
    d = json.loads(body)
    vids = d.get("videos", [])
    if not vids:
        print(f"  pn={pn}: 空，停止")
        break
    all_videos.extend(vids)
    print(f"  pn={pn}: total={d.get('total')}, got={len(vids)}")
    if len(vids) < 50:
        print(f"  pn={pn}: 不足 50 条（最后一页）")
        break
    time.sleep(0.3)

print()
print(f"  共拉取: {len(all_videos)} 条")
if all_videos:
    sorted_v = sorted(all_videos, key=lambda x: x.get("publish_time", 0))
    earliest = sorted_v[0]
    latest = sorted_v[-1]
    import datetime
    earliest_dt = datetime.datetime.fromtimestamp(earliest["publish_time"]).strftime("%Y-%m-%d %H:%M:%S")
    latest_dt = datetime.datetime.fromtimestamp(latest["publish_time"]).strftime("%Y-%m-%d %H:%M:%S")
    print(f"  最早一条: {earliest.get('bvid')} '{earliest.get('title', '')[:40]}' @ {earliest_dt}")
    print(f"  最新一条: {latest.get('bvid')} '{latest.get('title', '')[:40]}' @ {latest_dt}")
print()

# 用户提到的 BV 号是否在结果里
print("=" * 60)
print("3. 用户提到的 BV 号是否在 uapis 拉到的结果里？")
print("=" * 60)
target_bvs = ["BV1gs411o7XM", "BV1gfGw6RE5p"]
for bv in target_bvs:
    found = next((v for v in all_videos if v.get("bvid") == bv), None)
    if found:
        import datetime
        pt = datetime.datetime.fromtimestamp(found["publish_time"]).strftime("%Y-%m-%d")
        print(f"  {bv}: 找到 ✓  '{found.get('title', '')[:40]}' @ {pt}")
    else:
        print(f"  {bv}: 未找到 ✗")
print()

# 实际拿到的 vs 报告的 total
print("=" * 60)
print("4. uapis total vs 实际拉取数 vs B 站 userinfo.archive_count")
print("=" * 60)
print(f"  B 站 userinfo.archive_count: {data.get('archive_count')}")
print(f"  uapis total 字段:            {d.get('total')}")
print(f"  实际拉取数:                  {len(all_videos)}")

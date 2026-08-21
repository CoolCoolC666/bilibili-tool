"""v3.0.8 诊断 100 条限制"""
import os
import sys
import json
import urllib.request

os.environ.pop("UAPIS_CN_API_KEY", None)


def req(url, **kwargs):
    r = urllib.request.Request(url, headers={"User-Agent": "bilibili_tool_v2/diag"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8")


# 1. 测试 uapis /archives 翻页上限（用 Warma 53456，archive_count=262）
print("=" * 60)
print("uapis Warma 53456 翻页（ps 设为 50）")
print("=" * 60)
total_videos = []
for pn in range(1, 10):
    code, body = req(
        f"https://uapis.cn/api/v1/social/bilibili/archives?mid=53456&ps=50&pn={pn}"
    )
    d = json.loads(body)
    videos = d.get("videos", [])
    if not videos:
        print(f"  pn={pn}: 空")
        break
    total_videos.extend(videos)
    earliest = min(v.get("publish_time", 0) for v in videos)
    import datetime
    earliest_dt = datetime.datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
    print(f"  pn={pn}: total={d.get('total')}, got={len(videos)}, first={earliest_dt}")
    if len(videos) < 50:
        print(f"  pn={pn}: 不足 50 条（最后一页）")
        break

print()
print(f"实际共拉取: {len(total_videos)} 条")
if total_videos:
    sorted_v = sorted(total_videos, key=lambda x: x.get("publish_time", 0))
    earliest = sorted_v[0]
    latest = sorted_v[-1]
    earliest_dt = datetime.datetime.fromtimestamp(earliest["publish_time"]).strftime("%Y-%m-%d")
    latest_dt = datetime.datetime.fromtimestamp(latest["publish_time"]).strftime("%Y-%m-%d")
    print(f"最早: {earliest_dt} | 最新: {latest_dt}")

# 2. userinfo 看 Warma 真实 archive_count
print()
print("=" * 60)
print("uapis /userinfo 拿真实 archive_count")
print("=" * 60)
code, body = req("https://uapis.cn/api/v1/social/bilibili/userinfo?uid=53456")
d = json.loads(body)
print(f"  Warma archive_count: {d.get('archive_count')}")
print(f"  Warma follower: {d.get('follower')}")

"""v2.10.0+ 真实测试：Shuakami (UID 483307278) 投稿 + 排序"""
import os
import sys

os.environ.pop("UAPIS_CN_API_KEY", None)

from bilibili_tool.uapi import UapisCnProvider

p = UapisCnProvider()
print("--- Shuakami (UID 483307278) 最近 5 条投稿 ---")
arcs = p.fetch_author_archives(483307278, max_count=5)
print(f"拿到 {len(arcs)} 条:")
for i, a in enumerate(arcs, 1):
    title = a.get("title", "")[:40]
    print(f"  [{i}] {a.get('bvid')} {title} (pubdate={a.get('pubdate')}, play={a.get('play')})")

print()
print("--- Shuakami 最近 30 天 ---")
arcs30 = p.fetch_author_archives(483307278, days=30)
print(f"30 天内 {len(arcs30)} 条")

print()
print("--- Shuakami 按 views 排序 (直接调底层端点) ---")
r = p.sess.get(
    "https://uapis.cn/api/v1/social/bilibili/archives",
    params={"mid": "483307278", "ps": 5, "pn": 1, "orderby": "views"},
    timeout=10,
)
data = r.json()
for v in data.get("videos", []):
    print(f"  {v.get('bvid')} {v.get('title', '')[:40]} (play={v.get('play_count')})")
print()
print(f"X-Cache-Status: {r.headers.get('X-Cache-Status')}")
print(f"UAPI-Credits-Charged: {r.headers.get('UAPI-Credits-Charged')}")
print(f"UAPI-Debit-Status: {r.headers.get('UAPI-Debit-Status')}")
print(f"RateLimit: {r.headers.get('RateLimit')}")

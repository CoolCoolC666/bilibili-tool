"""查 春山响 CSV 时间范围"""
import csv

with open("output/author_1751577265_20260821_213245.csv", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
print(f"总条数: {len(rows)}")
sorted_rows = sorted(rows, key=lambda r: r["pubdate"])
earliest = sorted_rows[0]
latest = sorted_rows[-1]
print(f"最早: {earliest['pubdate']} - {earliest['title'][:50]}")
print(f"最晚: {latest['pubdate']} - {latest['title'][:50]}")
print(f"userinfo archive_count: 983")
print(f"实际拿到: {len(rows)}")

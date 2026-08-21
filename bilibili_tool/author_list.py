"""v2.9.0+ 阶段 1：UP 主视频链接列表导出（CSV）。

用途：
  - 从 UP 主空间拉取视频列表（BV + 标题 + 时长 + 发布时间 + 分区）
  - 导出为 CSV，供用户二次筛选后喂回阶段 2 抓详情

设计：
  - 复用 AuthorVideoFetcher.fetch_author_archives_raw()（返回原始 dict）
  - 输出到 output/author_<uid>_<时间戳>.csv
  - 字段：bvid, aid, title, duration, pubdate, tid, up_uid
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .author import AuthorVideoFetcher, TZ_BJ


class AuthorListExporter:
    """阶段 1：UP 主视频链接列表 → CSV。

    用法：
        fetcher = AuthorVideoFetcher()
        exporter = AuthorListExporter(fetcher)
        path, count = exporter.export(uid=473965081, days=7)
        # → output/author_473965081_20260821_173000.csv
    """

    def __init__(
        self,
        fetcher: Optional[AuthorVideoFetcher] = None,
        *,
        output_dir: str = "output",
    ):
        self.fetcher = fetcher or AuthorVideoFetcher()
        self.output_dir = output_dir

    def export(
        self,
        uid: int,
        *,
        archives: Optional[List[dict]] = None,
        days: Optional[int] = None,
        max_count: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        output_dir: Optional[str] = None,
    ) -> tuple:
        """拉取 UP 主视频列表，导出 CSV。

        v3.0+：可传 `archives`（已拉好的数据），跳过 fetcher 调用。
          - 用途：跟 AuthorArchiveChain 配合（chain 拉数据 + exporter 写文件）
          - 传 archives 时 days/since/until 仍可用于过滤（但通常 chain 已过滤）

        参数（archives=None 时生效）：
          days: 最近 N 天
          max_count: 最多 N 条
          since / until: 时间范围
          output_dir: 输出目录（默认 self.output_dir）

        返回：(csv_path, count)
          csv_path: 输出 CSV 的绝对路径
          count:    实际导出的视频条数
        """
        od = output_dir or self.output_dir
        os.makedirs(od, exist_ok=True)

        # 拉原始数据（v3.0+：支持直接传 archives）
        if archives is None:
            archives = self.fetcher.fetch_author_archives_raw(
                uid, days=days, max_count=max_count, since=since, until=until,
            )

        # 生成文件名
        ts = datetime.now(TZ_BJ).strftime("%Y%m%d_%H%M%S")
        filename = f"author_{uid}_{ts}.csv"
        path = os.path.join(od, filename)

        # 写 CSV（UTF-8 BOM，Excel 可读）
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["bvid", "aid", "title", "duration", "pubdate", "tid", "up_uid"])
            for arc in archives:
                bvid = arc.get("bvid") or ""
                aid = arc.get("aid") or ""
                title = arc.get("title") or ""
                duration = arc.get("duration") or 0
                pubdate = self._format_pubdate(arc.get("pubdate"))
                tid = arc.get("tid") or 0
                writer.writerow([bvid, aid, title, duration, pubdate, tid, uid])

        return os.path.abspath(path), len(archives)

    @staticmethod
    def _format_pubdate(ts) -> str:
        """Unix 时间戳 → YYYY-MM-DD HH:MM:SS。"""
        try:
            ts = int(ts)
            if ts <= 0:
                return ""
            return datetime.fromtimestamp(ts, tz=TZ_BJ).strftime("%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError, OSError):
            return ""
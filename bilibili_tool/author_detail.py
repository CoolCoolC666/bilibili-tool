"""v2.9.0+ 阶段 2：阶段 1 导出的 CSV → 抓取视频详情 → XLSX 导出。

设计：
  - 读取阶段 1 的 CSV（bvid, aid, title, duration, pubdate, tid, up_uid）
  - 用 BilibiliVideoFetcher.batch_fetch() 抓详情（自动复用 v2.8 缓存）
  - 复用 v2.8 的 save_xlsx() 导出 3 sheet（视频/统计/错误）

v3.0.1+ 输出路径：
  - 默认 `output/xlsx/` 子目录（与 CSV 分离，避免污染主目录）
  - 文件名：`author_detail_<uid>_<时间戳>.xlsx`
  - 向后兼容：传 `output_dir` 可指定其他位置
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import List, Optional, Tuple

from .author import TZ_BJ
from .fetcher import BilibiliVideoFetcher
from .exporter import save_xlsx
from .parser import ParsedItem


def read_author_csv(csv_path: str) -> List[dict]:
    """读阶段 1 导出的 CSV，返回 list of {bvid, aid, title, duration, pubdate, tid, up_uid}。

    不抛异常：行错误时跳过该行 + stderr 警告。
    """
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, 2):  # 2 = 表头是第 1 行
            bvid = (row.get("bvid") or "").strip()
            aid = (row.get("aid") or "").strip()
            if not bvid and not aid:
                # 空行直接跳过（不警告）
                continue
            rows.append({
                "bvid": bvid,
                "aid": aid,
                "title": (row.get("title") or "").strip(),
                "duration": (row.get("duration") or "").strip(),
                "pubdate": (row.get("pubdate") or "").strip(),
                "tid": (row.get("tid") or "").strip(),
                "up_uid": (row.get("up_uid") or "").strip(),
            })
    return rows


def rows_to_parsed_items(rows: List[dict]) -> List[ParsedItem]:
    """CSV rows → ParsedItem 列表（kind=bv/av）。

    优先 bvid，回退 aid。
    """
    items = []
    for r in rows:
        bvid = r.get("bvid") or ""
        aid = r.get("aid") or ""
        if bvid:
            items.append(ParsedItem(kind="bv", value=bvid, raw=bvid))
        elif aid:
            items.append(ParsedItem(kind="av", value=aid, raw=aid))
    return items


class AuthorDetailExporter:
    """阶段 2：阶段 1 CSV → 抓详情 → XLSX 导出。

    用法：
        fetcher = BilibiliVideoFetcher()
        exporter = AuthorDetailExporter(fetcher)
        path, ok_count, fail_count = exporter.export("output/author_473965081_xxx.csv")
    """

    def __init__(
        self,
        fetcher: Optional[BilibiliVideoFetcher] = None,
        *,
        output_dir: str = "output/xlsx",  # v3.0.1+：默认存到 xlsx/ 子目录（与 csv 分离）
        delay: float = 0.6,
    ):
        self.fetcher = fetcher or BilibiliVideoFetcher()
        self.output_dir = output_dir
        self.delay = delay

    def export(
        self,
        csv_path: str,
        *,
        output_dir: Optional[str] = None,
        max_count: Optional[int] = None,
    ) -> Tuple[str, int, int]:
        """从阶段 1 CSV 抓详情，导出 XLSX。

        参数：
          csv_path:   阶段 1 导出的 CSV 文件路径
          max_count:  最多抓多少条（None=全部，给调试/小批测试用）
          output_dir: 输出目录（默认 output/）

        返回：(xlsx_path, ok_count, fail_count)
        """
        rows = read_author_csv(csv_path)
        if not rows:
            raise ValueError(f"CSV 文件为空或格式错误：{csv_path}")

        if max_count is not None:
            rows = rows[:max_count]

        items = rows_to_parsed_items(rows)

        # 从 CSV 拿 up_uid（用于文件名）
        up_uid = rows[0].get("up_uid", "unknown")
        if not up_uid:
            up_uid = "unknown"

        # 抓详情（v2.8 batch_fetch 自动处理缓存/重试）
        # 注：print 用 ASCII 字符（不用 ✓/✗ emoji），避免 Windows GBK 终端编码炸
        print(f"[+] 抓取 {len(items)} 条视频详情...")
        video_infos = self.fetcher.batch_fetch(
            items, delay=self.delay,
            progress_cb=lambda i, total, info: print(
                f"  [{i:3d}/{total}] {'OK' if info.is_ok else 'FAIL'} "
                f"{(info.title or info.raw_input or '')[:28]}"
            ),
        )

        ok_count = sum(1 for v in video_infos if v.is_ok)
        fail_count = len(video_infos) - ok_count

        # 生成文件名
        ts = datetime.now(TZ_BJ).strftime("%Y%m%d_%H%M%S")
        od = output_dir or self.output_dir
        os.makedirs(od, exist_ok=True)
        xlsx_path = os.path.abspath(os.path.join(od, f"author_detail_{up_uid}_{ts}.xlsx"))

        save_xlsx(video_infos, xlsx_path)
        return xlsx_path, ok_count, fail_count
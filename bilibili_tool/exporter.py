"""导出器：xlsx / csv / json / txt 四种格式。

xlsx 走纯 openpyxl（不依赖 pandas），让脚本在精简 Python 环境也能跑。
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Iterable, List

from .models import VideoInfo


# xlsx 顺序列
XLSX_COLUMNS = [
    ("raw_input", "原始输入"),
    ("input_kind", "输入类型"),
    ("status", "状态"),
    ("api_code", "API 状态码"),
    ("error", "错误信息"),
    ("aid", "AV号"),
    ("bvid", "BV号"),
    ("title", "标题"),
    ("up_name", "UP主"),
    ("tname", "分区"),
    ("view", "播放量"),
    ("like", "点赞"),
    ("coin", "投币"),
    ("favorite", "收藏"),
    ("share", "分享"),
    ("reply", "评论"),
    ("danmaku", "弹幕"),
    ("duration", "时长(秒)"),
    ("pubdate", "发布时间"),
    ("ctime", "投稿时间"),
    ("desc", "简介"),
    ("url", "链接"),
    ("fetched_at", "抓取时间"),
]


def _row_for_xlsx(v: VideoInfo) -> dict:
    d = v.to_dict()
    return {label: d.get(key, "") for key, label in XLSX_COLUMNS}


def save_xlsx(videos: Iterable[VideoInfo], path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "视频数据"

    headers = [label for _, label in XLSX_COLUMNS]
    ws.append(headers)

    # 表头样式
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="3F6EE3")
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for v in videos:
        row = _row_for_xlsx(v)
        ws.append([row[label] for _, label in XLSX_COLUMNS])

    # 设置列宽（简单估算）
    for col_idx, (key, label) in enumerate(XLSX_COLUMNS, 1):
        max_len = len(str(label))
        for v in videos:
            val = _row_for_xlsx(v).get(label, "")
            s = "" if val is None else str(val)
            if len(s) > max_len:
                max_len = len(s)
        # 标题 / 简介 / 链接 列做宽一些
        if key in ("title", "desc", "url"):
            max_len = min(max_len, 50)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 50)

    # 冻结表头
    ws.freeze_panes = "A2"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb.save(path)
    return os.path.abspath(path)


def save_csv(videos: Iterable[VideoInfo], path: str) -> str:
    videos_list = list(videos)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[label for _, label in XLSX_COLUMNS],
        )
        writer.writeheader()
        for v in videos_list:
            row = _row_for_xlsx(v)
            writer.writerow(row)
    return os.path.abspath(path)


def save_json(videos: Iterable[VideoInfo], path: str) -> str:
    payload = [v.to_dict() for v in videos]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return os.path.abspath(path)


def save_txt(videos: Iterable[VideoInfo], path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    border = "═" * 60
    lines: List[str] = []
    lines.append("╔" + border + "╗")
    lines.append("║" + "🌟 B站视频信息提取清单 🌟".center(60) + "║")
    lines.append("╠" + border + "╣")
    lines.append(
        f"║ 🕒 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".ljust(62) + "║"
    )

    n_total = sum(1 for _ in videos)
    # 注意：videos 可能是 generator，这里其实在 save_txt 调用前就 list 化了
    lines.append(f"║ 📊 共 {n_total} 条记录".ljust(62) + "║")
    lines.append("╚" + border + "╝\n")

    for idx, v in enumerate(videos, 1):
        marker = "✓" if v.is_ok else "✗"
        title_disp = v.title or "(无标题)"
        lines.append(f"▶ [{idx:03d}] {marker} {title_disp}")
        lines.append(f"  👤 UP主: {v.up_name or '-'}")
        if v.tname:
            lines.append(f"  🏷️  分区: {v.tname}")
        if v.view is not None:
            lines.append(f"  👁  播放: {v.view:,} | 👍{v.like or 0:,} | 💬{v.reply or 0:,}")
        if v.pubdate:
            lines.append(f"  📅 发布时间: {v.pubdate}")
        if v.url:
            lines.append(f"  🔗 链接: {v.url}")
        if v.status != "ok":
            lines.append(f"  ⚠️  状态: {v.status} | code={v.api_code} | {v.error}")
        lines.append("  " + "-" * 56 + "\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return os.path.abspath(path)


def export_all(
    videos: List[VideoInfo],
    *,
    base: str,
    out_dir: str = "output",
) -> dict:
    """一键导出 xlsx + csv + json + txt，base 是输出文件名前缀。"""
    saved = {}
    saved["xlsx"] = save_xlsx(videos, os.path.join(out_dir, f"{base}.xlsx"))
    saved["csv"] = save_csv(videos, os.path.join(out_dir, f"{base}.csv"))
    saved["json"] = save_json(videos, os.path.join(out_dir, f"{base}.json"))
    saved["txt"] = save_txt(videos, os.path.join(out_dir, f"{base}.txt"))
    return saved

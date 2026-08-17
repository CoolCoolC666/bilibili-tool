"""命令行入口：保持原 bilibili_tool.py 的交互体验，扩展到 BV/URL。

典型用法：
    python cli.py "170001 BV1xxx https://www.bilibili.com/video/BV1yyy"
    python cli.py -f input.txt -o myrun
    python cli.py --no-cache "BV1xxx"
    python cli.py --reset-cache
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

from bilibili_tool import (
    BilibiliVideoFetcher,
    Cache,
    expand_short_urls,
    export_all,
    parse_text,
)
from bilibili_tool.cache import parse_duration


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE = os.path.join(HERE, "data", "cache.json")
DEFAULT_OUT = os.path.join(HERE, "output")


def _read_targets(args) -> str:
    if args.file:
        if not os.path.exists(args.file):
            print(f"[!] 输入文件不存在: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            return f.read()
    if args.text:
        return " ".join(args.text)
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("💡 提示: 粘贴 AV/BV/URL（空格、换行都行），Ctrl+D / 回车结束。")
    print("   例: BV1FpLU62EZW 170001 https://www.bilibili.com/video/BV1xxx\n")
    return input("👉 输入待抓取的 ID / 链接: ")


def _print_progress(i: int, total: int, info) -> None:
    marker = "✓" if info.is_ok else "✗"
    snippet = (info.title or info.raw_input or "")[:28]
    print(f"  [{i:3d}/{total}] {marker} {snippet:<28}  [{info.status}{'/' + str(info.api_code) if info.api_code is not None else ''}]")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="B 站视频信息抓取工具（支持 AV / BV / URL / 短链 + 缓存 + 断点续传）"
    )
    src = parser.add_argument_group("输入源（互斥）")
    src.add_argument("text", nargs="*", help="直接在命令行粘贴 ID / 链接")
    src.add_argument("-f", "--file", help="从文件读取，每行一段")
    src.add_argument(
        "--stdin",
        action="store_true",
        help="强制从标准输入读取（管道场景）",
    )

    out = parser.add_argument_group("输出")
    out.add_argument("-o", "--output", help="输出文件名前缀（默认：bilibili_<时间戳>）")
    out.add_argument("--out-dir", default=DEFAULT_OUT, help="输出目录")
    out.add_argument(
        "--format",
        choices=["xlsx", "csv", "json", "txt", "all"],
        default="all",
        help="导出格式",
    )
    out.add_argument(
        "--dedupe",
        dest="dedupe",
        action="store_true",
        default=True,
        help="导出时按 (BV, AV) 去重，同一视频只出现一行（默认开）",
    )
    out.add_argument(
        "--no-dedupe",
        dest="dedupe",
        action="store_false",
        help="不去重，保留所有记录（即使同一视频出现多次）",
    )
    out.add_argument(
        "--exclude-invalid",
        action="store_true",
        help=(
            "导出时排除无效视频（不统计）。"
            "只保留 status == 'ok' 的成功抓取记录，"
            "自动剔除 not_found / failed 等失效条目。"
            "默认关闭，保留原始全部导出行为。"
        ),
    )

    cache = parser.add_argument_group("缓存")
    cache.add_argument("--cache", default=DEFAULT_CACHE, help="缓存文件路径")
    cache.add_argument(
        "--no-cache",
        action="store_true",
        help="完全不用缓存（等价于 --max-age 0）",
    )
    cache.add_argument(
        "--max-age",
        type=str,
        default="1h",
        help=(
            "动态字段（播放/点赞/收藏/评论/弹幕）的最大缓存年龄。"
            "格式：'30m' / '1h' / '24h' / '7d'。"
            "'0' = 完全不用缓存，'never' = 永远信任缓存（不推荐）。"
            "默认 '1h'，与 Web 端「实时（1h 内）」一致。"
            "静态字段（标题/UP主/发布时间/时长）永远缓存，不受此选项影响。"
            "失败/失效状态也永远缓存。"
        ),
    )
    cache.add_argument("--reset-cache", action="store_true", help="清空缓存后开始")
    cache.add_argument("--save-cache", action="store_true", default=True, help="抓取后写回缓存（默认开）")

    net = parser.add_argument_group("网络")
    net.add_argument("--delay", type=float, default=0.6, help="每个请求间隔秒（默认 0.6）")
    net.add_argument("--retry", type=int, default=2, help="每个 ID 的最大重试次数（默认 2）")
    net.add_argument("--timeout", type=float, default=10.0, help="单次请求超时秒")

    parse = parser.add_argument_group("解析")
    parse.add_argument(
        "--allow-bare-numbers",
        action="store_true",
        help="允许把 6-13 位裸数字当 AV 号（默认关闭，避免把年份/统计数字误识别）。"
        "如确需识别 '170001' 这种裸号，加此开关；BV / av 前缀 / URL 永远会被识别。",
    )

    args = parser.parse_args(argv)

    # 1) 解析输入
    raw_text = _read_targets(args)
    parsed = parse_text(raw_text, allow_bare_numbers=args.allow_bare_numbers)
    if not parsed:
        hint = ""
        if not args.allow_bare_numbers:
            hint = "\n   💡 提示: 输入的全是数字？加上 --allow-bare-numbers 试试。"
        print(f"\n⚠️ 未识别到任何 AV / BV / URL。{hint}")
        return 1

    # 2) 展开短链
    parsed = expand_short_urls(parsed)
    if not parsed:
        print("\n⚠️ 短链展开后没有可用的 ID。")
        return 1

    # 3) 缓存
    if args.reset_cache and os.path.exists(args.cache):
        os.remove(args.cache)
        print(f"[i] 已清空缓存: {args.cache}")

    # 解析 max-age
    if args.no_cache:
        max_age_seconds = 0
        max_age_desc = "0（不用缓存）"
    else:
        max_age_seconds = parse_duration(args.max_age)
        if max_age_seconds is None:
            max_age_seconds = 3600  # 默认 1h（防御性，argparse default 也是 1h）
        max_age_desc = args.max_age

    cache_obj = Cache(args.cache) if max_age_seconds != 0 else None
    print(f"[i] 缓存策略: max-age = {max_age_desc}（静态字段永远，失败状态永远）")

    # 4) 构建 fetcher
    fetcher = BilibiliVideoFetcher(max_retries=args.retry, timeout=args.timeout)

    # 5) 跑
    started = time.time()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []
    from_cache_count = 0
    total = len(parsed)
    print(f"\n🎯 解析到 {total} 个待抓取项\n")

    for i, item in enumerate(parsed, 1):
        if cache_obj:
            sk = _skeleton_from_parsed(item)
            cached = cache_obj.get_fresh(sk, max_age_seconds=max_age_seconds)
            if cached:
                results.append(cached)
                from_cache_count += 1
                _print_progress(i, total, cached)
                age_str = ""
                if cached.status == "ok" and cached.fetched_at:
                    try:
                        from datetime import datetime as _dt
                        fetched = _dt.strptime(cached.fetched_at, "%Y-%m-%d %H:%M:%S")
                        age_sec = (_dt.now() - fetched).total_seconds()
                        if age_sec < 60:
                            age_str = f", {int(age_sec)}秒前抓的"
                        elif age_sec < 3600:
                            age_str = f", {int(age_sec/60)}分钟前抓的"
                        else:
                            age_str = f", {int(age_sec/3600)}小时前抓的"
                    except ValueError:
                        pass
                print(f"    ↪ cache hit{age_str}")
                continue

        # 用一个空 info 做 progress 标记
        from bilibili_tool.models import VideoInfo
        progress_info = VideoInfo(raw_input=item.raw or item.value, input_kind=item.kind)
        print(f"  [{i:3d}/{total}] ... 正在请求 {item.value}")
        info = fetcher.fetch_with_retry(item)
        results.append(info)
        if cache_obj and args.save_cache:
            cache_obj.put(info)
        _print_progress(i, total, info)
        if i < total and args.delay > 0:
            time.sleep(args.delay)

    if cache_obj and args.save_cache:
        try:
            cache_obj.save()
            print(f"\n[i] 缓存已保存: {args.cache}")
        except OSError as e:
            print(f"[!] 缓存保存失败: {e}")

    # 6) 导出
    elapsed = time.time() - started
    ok = sum(1 for v in results if v.is_ok)
    failed = total - ok
    base = args.output or f"bilibili_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📊 {ok} 成功 / {failed} 失败 / {from_cache_count} 缓存命中 / 耗时 {elapsed:.1f}s")

    saved = {}
    fmt = args.format
    excl = args.exclude_invalid
    if fmt == "all":
        saved = export_all(results, base=base, out_dir=args.out_dir, dedupe=args.dedupe, exclude_invalid=excl)
    elif fmt == "xlsx":
        from bilibili_tool.exporter import save_xlsx, dedupe_videos as _dedupe, filter_valid as _filt
        rows = _filt(results) if excl else results
        rows = _dedupe(rows) if args.dedupe else rows
        saved["xlsx"] = save_xlsx(rows, os.path.join(args.out_dir, f"{base}.xlsx"))
    elif fmt == "csv":
        from bilibili_tool.exporter import save_csv, dedupe_videos as _dedupe, filter_valid as _filt
        rows = _filt(results) if excl else results
        rows = _dedupe(rows) if args.dedupe else rows
        saved["csv"] = save_csv(rows, os.path.join(args.out_dir, f"{base}.csv"))
    elif fmt == "json":
        from bilibili_tool.exporter import save_json, dedupe_videos as _dedupe, filter_valid as _filt
        rows = _filt(results) if excl else results
        rows = _dedupe(rows) if args.dedupe else rows
        saved["json"] = save_json(rows, os.path.join(args.out_dir, f"{base}.json"))
    elif fmt == "txt":
        from bilibili_tool.exporter import save_txt, dedupe_videos as _dedupe, filter_valid as _filt
        rows = _filt(results) if excl else results
        rows = _dedupe(rows) if args.dedupe else rows
        saved["txt"] = save_txt(rows, os.path.join(args.out_dir, f"{base}.txt"))

    for k, v in saved.items():
        print(f"  ✓ {k}: {v}")
    return 0


def _skeleton_from_parsed(item):
    """给缓存查找用：构造一个最小 VideoInfo，只为比对 key。"""
    from bilibili_tool.models import VideoInfo
    if item.kind == "av":
        return VideoInfo(input_kind="av", aid=int(item.value), raw_input=item.raw)
    if item.kind == "bv":
        return VideoInfo(input_kind="bv", bvid=item.value, raw_input=item.raw)
    return VideoInfo(input_kind=item.kind, raw_input=item.raw)


if __name__ == "__main__":
    sys.exit(main())

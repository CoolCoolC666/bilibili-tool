"""命令行入口：保持原 bilibili_tool.py 的交互体验，扩展到 BV/URL/专栏/番剧。

典型用法：
    python cli.py "170001 BV1xxx https://www.bilibili.com/video/BV1yyy"
    python cli.py "https://www.bilibili.com/read/cv12345 https://www.bilibili.com/bangumi/play/ss67890"
    python cli.py "https://b23.tv/HXDxEfr"   # 短链自动展开 + 自动分类
    python cli.py -f input.txt -o myrun
    python cli.py --no-cache "BV1xxx"
    python cli.py --reset-cache
    python cli.py --no-fetch-articles --no-fetch-bangumi  "BV1xxx"  # 只要视频
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

from bilibili_tool import (
    BilibiliArticleFetcher,
    BilibiliBangumiFetcher,
    BilibiliVideoFetcher,
    Cache,
    expand_short_urls,
    export_all,
    export_all_multi,
    parse_text,
)
from bilibili_tool.cache import (
    _article_fingerprint,
    _article_keys,
    _bangumi_fingerprint,
    _bangumi_keys,
    parse_duration,
)
from bilibili_tool.models import ArticleInfo, BangumiInfo, VideoInfo


HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE = os.path.join(HERE, "data", "cache.json")
DEFAULT_CACHE_ARTICLE = os.path.join(HERE, "data", "cache_article.json")
DEFAULT_CACHE_BANGUMI = os.path.join(HERE, "data", "cache_bangumi.json")
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
    print("💡 提示: 粘贴 AV/BV/URL/短链/专栏/番剧（空格、换行都行），Ctrl+D / 回车结束。")
    print("   例: BV1FpLU62EZW 170001 https://www.bilibili.com/video/BV1xxx")
    print("   例: https://www.bilibili.com/read/cv12345 https://www.bilibili.com/bangumi/play/ss67890")
    print("   例: https://b23.tv/HXDxEfr   (短链自动展开 + 自动分类)\n")
    return input("👉 输入待抓取的 ID / 链接: ")


def _print_progress(i: int, total: int, info) -> None:
    marker = "✓" if info.is_ok else "✗"
    snippet = (info.title or info.raw_input or "")[:28]
    print(f"  [{i:3d}/{total}] {marker} {snippet:<28}  [{info.status}{'/' + str(info.api_code) if info.api_code is not None else ''}]")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="B 站信息抓取工具（支持视频 / 专栏 / 番剧 + 短链 + 缓存 + 断点续传）"
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
        help="导出格式（v2.7 旧版只导视频；视频+专栏+番剧混导请用 --format multi）",
    )
    out.add_argument(
        "--dedupe",
        dest="dedupe",
        action="store_true",
        default=True,
        help="导出时按 (BV, AV) / (cv) / (ss, ep) 去重（默认开）",
    )
    out.add_argument(
        "--no-dedupe",
        dest="dedupe",
        action="store_false",
        help="不去重，保留所有记录",
    )
    out.add_argument(
        "--exclude-invalid",
        action="store_true",
        help=(
            "导出时排除无效记录（不统计）。"
            "只保留 status == 'ok' 的成功抓取记录，"
            "自动剔除 not_found / failed 等失效条目。"
            "默认关闭，保留原始全部导出行为。"
        ),
    )

    content = parser.add_argument_group("抓取内容（v2.8.0 新增）")
    content.add_argument(
        "--fetch-articles",
        dest="fetch_articles",
        action="store_true",
        default=True,
        help="识别到专栏 URL/ID 时自动抓取（默认开）",
    )
    content.add_argument(
        "--no-fetch-articles",
        dest="fetch_articles",
        action="store_false",
        help="跳过专栏抓取（只处理视频和番剧）",
    )
    content.add_argument(
        "--fetch-bangumi",
        dest="fetch_bangumi",
        action="store_true",
        default=True,
        help="识别到番剧 URL/ID 时自动抓取（默认开）",
    )
    content.add_argument(
        "--no-fetch-bangumi",
        dest="fetch_bangumi",
        action="store_false",
        help="跳过番剧抓取（只处理视频和专栏）",
    )

    cache = parser.add_argument_group("缓存")
    cache.add_argument("--cache", default=DEFAULT_CACHE, help="视频缓存文件路径")
    cache.add_argument("--cache-article", default=DEFAULT_CACHE_ARTICLE, help="专栏缓存文件路径")
    cache.add_argument("--cache-bangumi", default=DEFAULT_CACHE_BANGUMI, help="番剧缓存文件路径")
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
            "动态字段的最大缓存年龄。格式：'30m' / '1h' / '24h' / '7d'。"
            "'0' = 完全不用缓存，'never' = 永远信任缓存（不推荐）。"
            "默认 '1h'。"
        ),
    )
    cache.add_argument("--reset-cache", action="store_true", help="清空全部缓存后开始")
    cache.add_argument("--save-cache", action="store_true", default=True, help="抓取后写回缓存（默认开）")

    net = parser.add_argument_group("网络")
    net.add_argument("--delay", type=float, default=0.6, help="每个请求间隔秒（默认 0.6）")
    net.add_argument("--retry", type=int, default=2, help="每个 ID 的最大重试次数（默认 2）")
    net.add_argument("--timeout", type=float, default=10.0, help="单次请求超时秒")

    parse = parser.add_argument_group("解析")
    parse.add_argument(
        "--allow-bare-numbers",
        action="store_true",
        help="允许把 6-16 位裸数字当 AV 号（默认关闭，避免把年份/统计数字误识别）。"
        "BV / av 前缀 / URL 永远会被识别。",
    )

    args = parser.parse_args(argv)

    # 1) 解析输入
    raw_text = _read_targets(args)
    parsed = parse_text(raw_text, allow_bare_numbers=args.allow_bare_numbers)
    if not parsed:
        hint = ""
        if not args.allow_bare_numbers:
            hint = "\n   💡 提示: 输入的全是数字？加上 --allow-bare-numbers 试试。"
        print(f"\n⚠️ 未识别到任何 AV / BV / URL / 专栏 / 番剧。{hint}")
        return 1

    # 2) 展开短链
    parsed = expand_short_urls(parsed)
    if not parsed:
        print("\n⚠️ 短链展开后没有可用的 ID。")
        return 1

    # 3) 按 kind 分桶
    video_items = [p for p in parsed if p.kind in ("av", "bv")]
    article_items = [p for p in parsed if p.kind == "article"]
    bangumi_items = [p for p in parsed if p.kind in ("bangumi_ss", "bangumi_ep")]

    # 应用 fetch 开关
    if not args.fetch_articles:
        skipped = len(article_items)
        article_items = []
        if skipped:
            print(f"[i] --no-fetch-articles：跳过 {skipped} 个专栏")
    if not args.fetch_bangumi:
        skipped = len(bangumi_items)
        bangumi_items = []
        if skipped:
            print(f"[i] --no-fetch-bangumi：跳过 {skipped} 个番剧")

    total = len(video_items) + len(article_items) + len(bangumi_items)
    if total == 0:
        print("\n⚠️ 过滤后没有需要抓取的项目。")
        return 1
    print(f"\n🎯 解析到 {len(parsed)} 个 → 视频 {len(video_items)} / 专栏 {len(article_items)} / 番剧 {len(bangumi_items)}")

    # 4) 缓存
    if args.reset_cache:
        for p in (args.cache, args.cache_article, args.cache_bangumi):
            if os.path.exists(p):
                os.remove(p)
        print(f"[i] 已清空全部缓存")

    if args.no_cache:
        max_age_seconds = 0
        max_age_desc = "0（不用缓存）"
    else:
        max_age_seconds = parse_duration(args.max_age)
        if max_age_seconds is None:
            max_age_seconds = 3600
        max_age_desc = args.max_age
    print(f"[i] 缓存策略: max-age = {max_age_desc}")

    video_cache = Cache(args.cache) if max_age_seconds != 0 else None
    article_cache = Cache(
        args.cache_article,
        record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint,
    ) if max_age_seconds != 0 else None
    bangumi_cache = Cache(
        args.cache_bangumi,
        record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint,
    ) if max_age_seconds != 0 else None

    # 5) 跑
    started = time.time()
    video_results: list = []
    article_results: list = []
    bangumi_results: list = []
    from_cache_count = 0

    # --- 视频 ---
    if video_items:
        fetcher = BilibiliVideoFetcher(max_retries=args.retry, timeout=args.timeout)
        print(f"\n📹 开始抓取 {len(video_items)} 个视频 ...")
        for i, item in enumerate(video_items, 1):
            sk = _video_skeleton_from_parsed(item)
            if video_cache:
                cached = video_cache.get_fresh(sk, max_age_seconds=max_age_seconds)
                if cached:
                    video_results.append(cached)
                    from_cache_count += 1
                    _print_progress(i, len(video_items), cached)
                    print(f"    ↪ cache hit")
                    continue
            print(f"  [{i:3d}/{len(video_items)}] ... 正在请求 {item.value}")
            info = fetcher.fetch_with_retry(item)
            video_results.append(info)
            if video_cache and args.save_cache:
                video_cache.put(info)
            _print_progress(i, len(video_items), info)
            if i < len(video_items) and args.delay > 0:
                time.sleep(args.delay)

    # --- 专栏 ---
    if article_items:
        fetcher = BilibiliArticleFetcher(max_retries=args.retry, timeout=args.timeout)
        print(f"\n📝 开始抓取 {len(article_items)} 个专栏 ...")
        for i, item in enumerate(article_items, 1):
            sk = _article_skeleton_from_parsed(item)
            if article_cache:
                cached = article_cache.get_fresh(sk, max_age_seconds=max_age_seconds)
                if cached:
                    article_results.append(cached)
                    from_cache_count += 1
                    _print_progress(i, len(article_items), cached)
                    print(f"    ↪ cache hit")
                    continue
            print(f"  [{i:3d}/{len(article_items)}] ... 正在请求 cv{item.value}")
            info = fetcher.fetch_with_retry(item)
            article_results.append(info)
            if article_cache and args.save_cache:
                article_cache.put(info)
            _print_progress(i, len(article_items), info)
            if i < len(article_items) and args.delay > 0:
                time.sleep(args.delay)

    # --- 番剧 ---
    if bangumi_items:
        fetcher = BilibiliBangumiFetcher(max_retries=args.retry, timeout=args.timeout)
        print(f"\n🎬 开始抓取 {len(bangumi_items)} 个番剧 ...")
        for i, item in enumerate(bangumi_items, 1):
            sk = _bangumi_skeleton_from_parsed(item)
            if bangumi_cache:
                cached = bangumi_cache.get_fresh(sk, max_age_seconds=max_age_seconds)
                if cached:
                    bangumi_results.append(cached)
                    from_cache_count += 1
                    _print_progress(i, len(bangumi_items), cached)
                    print(f"    ↪ cache hit")
                    continue
            label = f"ss{item.value}" if item.kind == "bangumi_ss" else f"ep{item.value}"
            print(f"  [{i:3d}/{len(bangumi_items)}] ... 正在请求 {label}")
            info = fetcher.fetch_with_retry(item)
            bangumi_results.append(info)
            if bangumi_cache and args.save_cache:
                bangumi_cache.put(info)
            _print_progress(i, len(bangumi_items), info)
            if i < len(bangumi_items) and args.delay > 0:
                time.sleep(args.delay)

    # 6) 保存缓存
    for c, label in [(video_cache, "视频"), (article_cache, "专栏"), (bangumi_cache, "番剧")]:
        if c and args.save_cache:
            try:
                c.save()
                print(f"\n[i] {label}缓存已保存: {c.path}")
            except OSError as e:
                print(f"[!] {label}缓存保存失败: {e}")

    # 7) 导出
    elapsed = time.time() - started
    all_results = video_results + article_results + bangumi_results
    ok = sum(1 for v in all_results if v.is_ok)
    failed = len(all_results) - ok
    base = args.output or f"bilibili_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📊 {ok} 成功 / {failed} 失败 / {from_cache_count} 缓存命中 / 耗时 {elapsed:.1f}s")

    saved = {}
    fmt = args.format
    excl = args.exclude_invalid
    # 是否走 multi 导出（v2.8.0）：
    # 只要识别到 article/bangumi，自动用 multi；否则用旧 API
    has_multi = bool(article_results or bangumi_results)
    if has_multi and fmt == "all":
        saved = export_all_multi(
            base=base, out_dir=args.out_dir,
            videos=video_results, articles=article_results, bangumis=bangumi_results,
            dedupe=args.dedupe, exclude_invalid=excl,
        )
    elif fmt == "all":
        # 旧版视频-only
        saved = export_all(video_results, base=base, out_dir=args.out_dir, dedupe=args.dedupe, exclude_invalid=excl)
    elif fmt == "xlsx":
        from bilibili_tool.exporter import save_xlsx, save_xlsx_multi, dedupe_videos as _dv, dedupe_articles as _da, dedupe_bangumis as _db, filter_valid as _filt
        if has_multi:
            vs = _filt(video_results) if excl else video_results
            asm = _filt(article_results) if excl else article_results
            bms = _filt(bangumi_results) if excl else bangumi_results
            vs = _dv(vs) if args.dedupe else vs
            asm = _da(asm) if args.dedupe else asm
            bms = _db(bms) if args.dedupe else bms
            saved["xlsx"] = save_xlsx_multi(vs, asm, bms, os.path.join(args.out_dir, f"{base}.xlsx"))
        else:
            rows = _filt(video_results) if excl else video_results
            rows = _dv(rows) if args.dedupe else rows
            saved["xlsx"] = save_xlsx(rows, os.path.join(args.out_dir, f"{base}.xlsx"))
    elif fmt == "csv":
        from bilibili_tool.exporter import save_csv, save_articles_csv, save_bangumis_csv, dedupe_videos as _dv, dedupe_articles as _da, dedupe_bangumis as _db, filter_valid as _filt
        if video_results:
            vs = _filt(video_results) if excl else video_results
            vs = _dv(vs) if args.dedupe else vs
            saved["csv_video"] = save_csv(vs, os.path.join(args.out_dir, f"{base}_video.csv"))
        if article_results:
            asm = _filt(article_results) if excl else article_results
            asm = _da(asm) if args.dedupe else asm
            saved["csv_article"] = save_articles_csv(asm, os.path.join(args.out_dir, f"{base}_article.csv"))
        if bangumi_results:
            bms = _filt(bangumi_results) if excl else bangumi_results
            bms = _db(bms) if args.dedupe else bms
            saved["csv_bangumi"] = save_bangumis_csv(bms, os.path.join(args.out_dir, f"{base}_bangumi.csv"))
    elif fmt == "json":
        from bilibili_tool.exporter import save_json, save_articles_json, save_bangumis_json, dedupe_videos as _dv, dedupe_articles as _da, dedupe_bangumis as _db, filter_valid as _filt
        if video_results:
            vs = _filt(video_results) if excl else video_results
            vs = _dv(vs) if args.dedupe else vs
            saved["json_video"] = save_json(vs, os.path.join(args.out_dir, f"{base}_video.json"))
        if article_results:
            asm = _filt(article_results) if excl else article_results
            asm = _da(asm) if args.dedupe else asm
            saved["json_article"] = save_articles_json(asm, os.path.join(args.out_dir, f"{base}_article.json"))
        if bangumi_results:
            bms = _filt(bangumi_results) if excl else bangumi_results
            bms = _db(bms) if args.dedupe else bms
            saved["json_bangumi"] = save_bangumis_json(bms, os.path.join(args.out_dir, f"{base}_bangumi.json"))
    elif fmt == "txt":
        from bilibili_tool.exporter import save_txt, save_articles_txt, save_bangumis_txt, dedupe_videos as _dv, dedupe_articles as _da, dedupe_bangumis as _db, filter_valid as _filt
        if video_results:
            vs = _filt(video_results) if excl else video_results
            vs = _dv(vs) if args.dedupe else vs
            saved["txt_video"] = save_txt(vs, os.path.join(args.out_dir, f"{base}_video.txt"))
        if article_results:
            asm = _filt(article_results) if excl else article_results
            asm = _da(asm) if args.dedupe else asm
            saved["txt_article"] = save_articles_txt(asm, os.path.join(args.out_dir, f"{base}_article.txt"))
        if bangumi_results:
            bms = _filt(bangumi_results) if excl else bangumi_results
            bms = _db(bms) if args.dedupe else bms
            saved["txt_bangumi"] = save_bangumis_txt(bms, os.path.join(args.out_dir, f"{base}_bangumi.txt"))

    for k, v in saved.items():
        print(f"  ✓ {k}: {v}")
    return 0


def _video_skeleton_from_parsed(item):
    from bilibili_tool.models import VideoInfo
    if item.kind == "av":
        return VideoInfo(input_kind="av", aid=int(item.value), raw_input=item.raw)
    if item.kind == "bv":
        return VideoInfo(input_kind="bv", bvid=item.value, raw_input=item.raw)
    return VideoInfo(input_kind=item.kind, raw_input=item.raw)


def _article_skeleton_from_parsed(item):
    from bilibili_tool.models import ArticleInfo
    return ArticleInfo(input_kind="article", cv_id=item.value, raw_input=item.raw)


def _bangumi_skeleton_from_parsed(item):
    from bilibili_tool.models import BangumiInfo
    if item.kind == "bangumi_ss":
        return BangumiInfo(input_kind="bangumi_ss", season_id=int(item.value), raw_input=item.raw)
    if item.kind == "bangumi_ep":
        return BangumiInfo(input_kind="bangumi_ep", ep_id=int(item.value), raw_input=item.raw)
    return BangumiInfo(input_kind=item.kind, raw_input=item.raw)


if __name__ == "__main__":
    sys.exit(main())

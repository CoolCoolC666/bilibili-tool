"""bilibili_tool: 多输入 + 缓存 + 断点续传 的 B 站信息抓取工具（视频 / 专栏 / 番剧）。"""
from .models import ArticleInfo, BangumiInfo, FetchSummary, VideoInfo
from .parser import parse_text, expand_short_urls, ParsedItem
from .fetcher import BilibiliArticleFetcher, BilibiliBangumiFetcher, BilibiliVideoFetcher
from .cache import Cache
from .exporter import (
    save_xlsx,
    save_csv,
    save_json,
    save_txt,
    save_xlsx_multi,
    save_articles_csv,
    save_articles_json,
    save_articles_txt,
    save_bangumis_csv,
    save_bangumis_json,
    save_bangumis_txt,
    export_all,
    export_all_multi,
    dedupe_videos,
    dedupe_articles,
    dedupe_bangumis,
    filter_valid,
)

__all__ = [
    # models
    "VideoInfo",
    "ArticleInfo",
    "BangumiInfo",
    "FetchSummary",
    # parser
    "parse_text",
    "expand_short_urls",
    "ParsedItem",
    # fetcher
    "BilibiliVideoFetcher",
    "BilibiliArticleFetcher",
    "BilibiliBangumiFetcher",
    # cache
    "Cache",
    # exporter
    "save_xlsx",
    "save_csv",
    "save_json",
    "save_txt",
    "save_xlsx_multi",
    "save_articles_csv",
    "save_articles_json",
    "save_articles_txt",
    "save_bangumis_csv",
    "save_bangumis_json",
    "save_bangumis_txt",
    "export_all",
    "export_all_multi",
    "dedupe_videos",
    "dedupe_articles",
    "dedupe_bangumis",
    "filter_valid",
]

__version__ = "2.8.0"

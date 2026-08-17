"""bilibili_tool: 多输入 + 缓存 + 断点续传的 B 站视频信息抓取工具。"""
from .models import VideoInfo, FetchSummary
from .parser import parse_text, expand_short_urls, ParsedItem
from .fetcher import BilibiliVideoFetcher
from .cache import Cache
from .exporter import (
    save_xlsx,
    save_csv,
    save_json,
    save_txt,
    export_all,
    dedupe_videos,
)

__all__ = [
    "VideoInfo",
    "FetchSummary",
    "parse_text",
    "expand_short_urls",
    "ParsedItem",
    "BilibiliVideoFetcher",
    "Cache",
    "save_xlsx",
    "save_csv",
    "save_json",
    "save_txt",
    "export_all",
    "dedupe_videos",
]

__version__ = "2.6.0"

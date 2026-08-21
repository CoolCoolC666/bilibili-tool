"""bilibili_tool: 多输入 + 缓存 + 断点续传 的 B 站信息抓取工具（视频 / 专栏 / 番剧 / UP 主）。"""
from .models import ArticleInfo, BangumiInfo, FetchSummary, VideoInfo
from .parser import parse_text, expand_short_urls, ParsedItem
from .fetcher import BilibiliArticleFetcher, BilibiliBangumiFetcher, BilibiliVideoFetcher
from .author import AuthorVideoFetcher
from .author_list import AuthorListExporter  # v2.9.0+ 阶段 1
from .author_detail import AuthorDetailExporter, read_author_csv, rows_to_parsed_items  # v2.9.0+ 阶段 2
from .wbi import WbiKeyCache, enc_wbi, get_mixin_key, get_wbi_keys, MIXIN_KEY_ENC_TAB  # v2.9.1+ WBI 签名
from .uapi import (  # v2.10.0+ UAPI 第三方集成（uapis.cn 等）
    ArchiveProvider,
    AuthorArchiveChain,
    SelfLegacyProvider,
    SelfWbiProvider,
    UapiAuthError,
    UapiError,
    UapiNotFoundError,
    UapiRateLimitError,
    UapiTimeoutError,
    UapisCnProvider,
)
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
    "AuthorVideoFetcher",  # v2.9.0+
    "AuthorListExporter",  # v2.9.0+ 阶段 1（UP 主视频列表 CSV 导出）
    "AuthorDetailExporter",  # v2.9.0+ 阶段 2（阶段 1 CSV → 抓详情 → XLSX 导出）
    "read_author_csv",
    "rows_to_parsed_items",
    "WbiKeyCache",  # v2.9.1+ WBI 签名 key 缓存（12h 自动刷新）
    "enc_wbi",  # v2.9.1+ WBI 签名函数
    "get_mixin_key",  # v2.9.1+ mixin_key 混排
    "get_wbi_keys",  # v2.9.1+ 从 nav 接口取 key
    "MIXIN_KEY_ENC_TAB",  # v2.9.1+ 64 位固定重排表
    # uapi v2.10.0+
    "ArchiveProvider",
    "AuthorArchiveChain",
    "SelfWbiProvider",
    "SelfLegacyProvider",
    "UapisCnProvider",
    "UapiError",
    "UapiRateLimitError",
    "UapiAuthError",
    "UapiNotFoundError",
    "UapiTimeoutError",
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

__version__ = "3.0.9-alpha"

"""输入解析：把任意形式的用户输入（AV / BV / URL / 短链）归一化为 (kind, payload)。

支持的输入示例：
- 纯数字  -> aid      (e.g. "170001")
- av12345  -> aid      (忽略大小写)
- BV1xxx   -> bvid     (标准 BV 开头 + 12 位 base58 字符)
- https://www.bilibili.com/video/BV1xxx -> bvid
- https://www.bilibili.com/video/av12345 -> aid
- https://b23.tv/xxxxxx (短链，需联网解) -> 通过 b23.tv 头跳转
- BV1xxx?p=2 -> bvid + 分 p（当前版本忽略分 p）
- BV1xxx/?spm_id_from=... -> bvid（忽略 query）

未识别片段会被跳过；重复值在去重时保留首次出现的顺序。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

import requests


# BV 号字符表（除 1 / i / l / o 外的 base58）
BV_ALPHABET = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
BV_LEN = 12
BV_PREFIX = "BV1"


@dataclass
class ParsedItem:
    kind: str          # "av" | "bv" | "short_url"
    value: str         # "170001" 或 "BV1xxx"
    raw: str = ""      # 用户原始片段

    def __repr__(self) -> str:
        return f"ParsedItem({self.kind}={self.value!r})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, ParsedItem):
            return NotImplemented
        return self.kind == other.kind and self.value == other.value and self.raw == other.raw

    def __hash__(self) -> int:
        return hash((self.kind, self.value, self.raw))


# 数字
RE_DIGITS = re.compile(r"\d+")
# av 前缀：1-20 位数字（B 站真实 aid 上限 ~10^10 也就是 10-11 位，
# 但有些抓取工具会用动态/评论/专栏 ID（18 位）当 av 传过来，
# parser 不做语义判断，让 B 站 API 决定是否有效）
RE_AV = re.compile(r"\bav(\d{1,20})\b", re.IGNORECASE)
# BV 前缀（BV1 + 10 位字符）
RE_BV = re.compile(r"\bBV1[1-9A-HJ-NP-Za-km-z]{9}\b", re.IGNORECASE)
# 完整 URL（bilibili.com/video/...）
RE_URL = re.compile(
    r"https?://(?:www\.)?bilibili\.com/video/(?:av(\d{1,20})|BV1[1-9A-HJ-NP-Za-km-z]{9})",
    re.IGNORECASE,
)
# b23.tv 短链
RE_SHORT = re.compile(r"https?://b23\.tv/[\w]+", re.IGNORECASE)


def _dedupe_keep_order(items: List[ParsedItem]) -> List[ParsedItem]:
    seen: set = set()
    out: List[ParsedItem] = []
    for it in items:
        key = (it.kind, it.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def parse_text(text: str, *, allow_bare_numbers: bool = False) -> List[ParsedItem]:
    """从一整段用户输入里抠出所有 AV/BV，URL 优先于裸号。

    优先级：URL > 短链 > 显式 av 标记 > 显式 BV 标记 > [可选] 纯数字。
    这样能避免把 URL 里的"av170001"当成独立的两个片段。

    返回的列表按"在原文中的出现顺序"排列，再去重。

    参数：
      allow_bare_numbers:
        False（默认）—— 裸数字**不**当 AV 号。年份/统计数字"2026""1949"会被忽略。
        True  —— 允许把 6~13 位的裸数字当 AV 号（更激进，但能识别"170001"这种输入）。
    """
    if not text:
        return []
    # 收集 (起始位置, ParsedItem)，最后按位置排序
    collected: List[Tuple[int, ParsedItem]] = []
    consumed_spans: List[Tuple[int, int]] = []

    def _mark(span: Tuple[int, int]) -> None:
        consumed_spans.append(span)

    def _overlaps(span: Tuple[int, int]) -> bool:
        s, e = span
        for cs, ce in consumed_spans:
            if not (e <= cs or s >= ce):
                return True
        return False

    # 1) 完整 URL
    for m in RE_URL.finditer(text):
        if _overlaps(m.span()):
            continue
        if m.group(1):  # av 数字
            collected.append((m.start(), ParsedItem("av", m.group(1), m.group(0))))
        else:
            collected.append((
                m.start(),
                ParsedItem("bv", m.group(0).split("/")[-1].split("?")[0], m.group(0)),
            ))
        _mark(m.span())

    # 2) 短链 b23.tv —— 单独拎出来，调用方决定要不要解（因为要联网）
    for m in RE_SHORT.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("short_url", m.group(0), m.group(0))))
        _mark(m.span())

    # 3) 显式 BV
    for m in RE_BV.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("bv", m.group(0), m.group(0))))
        _mark(m.span())

    # 4) 显式 av 标记
    for m in RE_AV.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("av", m.group(1), m.group(0))))
        _mark(m.span())

    # 5) 纯数字（剩余未消费片段）—— 默认不识别，避免把版权清单里的
    # 年份"2026""1949"和统计数字"100""10086"误当 AV 号查询；
    # 启用 allow_bare_numbers 后才识别 6-13 位的数字（B 站 av 号当前范围）。
    if allow_bare_numbers:
        for m in RE_DIGITS.finditer(text):
            if _overlaps(m.span()):
                continue
            n = m.group(0)
            # 6-13 位：B 站 av 号当前合理范围
            # 短于 6 位（< 100000）的数字大概率是误识别（年份/统计/页码）
            # 长于 13 位直接不是合法 av 号
            if 6 <= len(n) <= 13:
                collected.append((m.start(), ParsedItem("av", n, m.group(0))))
                _mark(m.span())

    collected.sort(key=lambda x: x[0])
    return _dedupe_keep_order([it for _, it in collected])


def expand_short_urls(
    items: List[ParsedItem],
    *,
    session: Optional[requests.Session] = None,
    timeout: float = 8.0,
    user_agent: str = "Mozilla/5.0",
) -> List[ParsedItem]:
    """把 short_url 类型的项解析成 BV/AV，HEAD 请求跟随 302 即可拿到 Location。

    无法解析的短链会被丢弃，不影响其他项。
    """
    if not items:
        return items
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", user_agent)
    out: List[ParsedItem] = []
    for it in items:
        if it.kind != "short_url":
            out.append(it)
            continue
        try:
            r = sess.head(it.value, allow_redirects=True, timeout=timeout)
            final = r.url or ""
        except Exception:
            final = ""
        # final 通常长这样：https://www.bilibili.com/video/BV1xxxxx/
        parsed = parse_text(final)
        if parsed:
            # 只取第一个匹配的 BV/AV
            out.append(parsed[0])
        # 解析失败就丢掉，不抛
    return _dedupe_keep_order(out)


def to_aid_string(parsed: ParsedItem) -> str:
    """返回适合传给 B 站 API 的 aid 字符串。仅供 fetcher 内部使用。"""
    if parsed.kind == "av":
        return parsed.value
    # bv 情况：fetcher 会自己用 bvid 参数
    return ""

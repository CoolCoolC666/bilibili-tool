"""输入解析：把任意形式的用户输入（AV / BV / URL / 短链 / 专栏 / 番剧）归一化为 (kind, payload)。

支持的输入示例：
- 纯数字  -> aid      (e.g. "170001")
- av12345  -> aid      (忽略大小写)
- BV1xxx   -> bvid     (标准 BV 开头 + 12 位 base58 字符)
- https://www.bilibili.com/video/BV1xxx -> bvid
- https://www.bilibili.com/video/av12345 -> aid
- https://www.bilibili.com/read/cv12345 -> article
- https://www.bilibili.com/bangumi/play/ss12345 -> bangumi_ss（整季）
- https://www.bilibili.com/bangumi/play/ep12345 -> bangumi_ep（单集）
- https://b23.tv/xxxxxx (短链，需联网解) -> 通过 b23.tv 头跳转后自动分类
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
    kind: str          # "av" | "bv" | "short_url" | "article" | "bangumi_ss" | "bangumi_ep"
    value: str         # "170001" / "BV1xxx" / "cv12345" / "ss12345" / "ep12345"
    raw: str = ""      # 用户原始片段
    from_scientific: bool = False  # 是否由科学记数法转换（精度可能丢失）
    is_opus: bool = False  # v2.8.1+：article 是否是 opus 新版（决定 API 端点）

    def __repr__(self) -> str:
        suffix = " (from scientific)" if self.from_scientific else ""
        if self.kind == "article" and self.is_opus:
            suffix += " (opus)"
        return f"ParsedItem({self.kind}={self.value!r}{suffix})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, ParsedItem):
            return NotImplemented
        return (
            self.kind == other.kind
            and self.value == other.value
            and self.raw == other.raw
            and self.from_scientific == other.from_scientific
            and self.is_opus == other.is_opus
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.value, self.raw, self.from_scientific, self.is_opus))


# 数字
RE_DIGITS = re.compile(r"\d+")
# av 前缀：1-20 位数字（B 站真实 aid 上限 ~10^10 也就是 10-11 位，
# 但有些抓取工具会用动态/评论/专栏 ID（18 位）当 av 传过来，
# parser 不做语义判断，让 B 站 API 决定是否有效）
RE_AV = re.compile(r"\bav(\d{1,20})\b", re.IGNORECASE)
# av 前缀 + 科学记数法：av1.13103E+14
# 不用 \b：避免"av1.13103E+14"被 RE_AV 截到"av1"后，RE_SCIENTIFIC 又匹配"13103E+14"
# 改用更严格的"前一个字符是 av"
RE_AV_SCI = re.compile(r"\bav(\d+(?:\.\d+)?[eE][+\-]?\d{1,3})\b", re.IGNORECASE)
# 裸科学记数法：1.13103E+14（来自 Excel 复制）
# 用 (?<![.\w]) lookbehind 排除"前一个字符是 . 或字母数字"的情况
# （避免匹配 "av1.13103E+14" 中的 "13103E+14" 片段）
RE_SCIENTIFIC = re.compile(r"(?<![.\w])(\d+(?:\.\d+)?[eE][+\-]?\d{1,3})\b")
# BV 前缀（BV1 + 10 位字符）
RE_BV = re.compile(r"\bBV1[1-9A-HJ-NP-Za-km-z]{9}\b", re.IGNORECASE)
# 完整 URL（bilibili.com/video/...）
# 子域名同时支持 www. / m. / 无 —— b23 短链有时会跳 m.bilibili.com
RE_URL = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?bilibili\.com/video/(?:av(\d{1,20})|BV1[1-9A-HJ-NP-Za-km-z]{9})",
    re.IGNORECASE,
)
# 专栏 URL（bilibili.com/read/cv{数字} —— 旧版，2024 前）
RE_ARTICLE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?bilibili\.com/read/cv(\d{1,20})",
    re.IGNORECASE,
)
# 专栏 URL（bilibili.com/opus/{数字} —— 新版，2024+）
RE_OPUS = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?bilibili\.com/opus/(\d{1,20})",
    re.IGNORECASE,
)
# 番剧整季 URL（bilibili.com/bangumi/play/ss{数字}）
RE_BANGUMI_SS = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?bilibili\.com/bangumi/play/ss(\d{1,10})",
    re.IGNORECASE,
)
# 番剧单集 URL（bilibili.com/bangumi/play/ep{数字}）
RE_BANGUMI_EP = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?bilibili\.com/bangumi/play/ep(\d{1,12})",
    re.IGNORECASE,
)
# b23.tv 短链
RE_SHORT = re.compile(r"https?://b23\.tv/[\w]+", re.IGNORECASE)


def _scientific_to_int(s: str) -> Optional[int]:
    """把 '1.13103E+14' / '1.13103e14' 转成 int。

    注意：**精度会丢失**——Excel 显示 1.13103E+14 时，实际存储是 113103000000000，
    跟 B 站真实 aid 113102813136198 差了 1.87 亿。
    但 parser 不做语义判断，让 B 站 API 自己决定是否有效。
    """
    try:
        n = int(round(float(s)))
    except (ValueError, OverflowError):
        return None
    if n < 0:
        return None
    return n


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

    # 1b) 专栏 URL（bilibili.com/read/cv{数字} —— 旧版 + bilibili.com/opus/{数字} —— 新版）
    for m in RE_ARTICLE.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("article", m.group(1), m.group(0), is_opus=False)))
        _mark(m.span())
    for m in RE_OPUS.finditer(text):
        if _overlaps(m.span()):
            continue
        # v2.8.1+：opus 必须走新端点，标记 is_opus=True
        collected.append((m.start(), ParsedItem("article", m.group(1), m.group(0), is_opus=True)))
        _mark(m.span())

    # 1c) 番剧整季 URL（bilibili.com/bangumi/play/ss{数字}）
    for m in RE_BANGUMI_SS.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("bangumi_ss", m.group(1), m.group(0))))
        _mark(m.span())

    # 1d) 番剧单集 URL（bilibili.com/bangumi/play/ep{数字}）
    for m in RE_BANGUMI_EP.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("bangumi_ep", m.group(1), m.group(0))))
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

    # 4) 显式 av + 科学记数法：av1.13103E+14（**先跑**，避免被 RE_AV 截成 av1）
    for m in RE_AV_SCI.finditer(text):
        if _overlaps(m.span()):
            continue
        n = _scientific_to_int(m.group(1))
        if n is not None and 1 <= len(str(n)) <= 20:
            collected.append((
                m.start(),
                ParsedItem("av", str(n), m.group(0), from_scientific=True),
            ))
            _mark(m.span())

    # 5) 显式 av 标记（普通数字）
    for m in RE_AV.finditer(text):
        if _overlaps(m.span()):
            continue
        collected.append((m.start(), ParsedItem("av", m.group(1), m.group(0))))
        _mark(m.span())

    # 6) 裸科学记数法：1.13103E+14（来自 Excel 复制粘贴）
    # 精度会丢失（Excel 显示是 113103000000000，真实 aid 可能是 113102813136198），
    # 但 parser 不做语义判断，让 B 站 API 自己决定是否有效。
    for m in RE_SCIENTIFIC.finditer(text):
        if _overlaps(m.span()):
            continue
        n = _scientific_to_int(m.group(1))
        if n is None:
            continue
        s = str(n)
        # 长度必须在 6-20 位之间（避免把 1.0E+2 = 100 这种短数字当 AV 号）
        if not (6 <= len(s) <= 20):
            continue
        collected.append((m.start(), ParsedItem("av", s, m.group(0), from_scientific=True)))
        _mark(m.span())

    # 7) 纯数字（剩余未消费片段）—— 默认不识别，避免把版权清单里的
    # 年份"2026""1949"和统计数字"100""10086"误当 AV 号查询；
    # 启用 allow_bare_numbers 后才识别 6-16 位的数字（覆盖现行 15 位 AV 号）。
    if allow_bare_numbers:
        for m in RE_DIGITS.finditer(text):
            if _overlaps(m.span()):
                continue
            n = m.group(0)
            # 6-16 位：
            # 短于 6 位（< 100000）的数字大概率是误识别（年份/统计/页码）
            # 长于 16 位（含 18 位动态/评论 ID）交给 RE_AV 那种显式 av 前缀的场景
            if 6 <= len(n) <= 16:
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
    """把 short_url 类型的项解析成 BV/AV/专栏/番剧，HEAD 请求跟随 302 即可拿到 Location。

    展开后按 302 目标 URL 路径自动分类：
      - /video/...   -> kind = "bv" / "av"
      - /read/cv...  -> kind = "article"
      - /bangumi/play/ss... -> kind = "bangumi_ss"
      - /bangumi/play/ep... -> kind = "bangumi_ep"

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
        # 优先尝试 article/bangumi 子集（避免被 RE_URL 误吞）
        # 顺序：opus > article (cv) > bangumi_ss > bangumi_ep > video
        classified: Optional[ParsedItem] = None
        m_article = RE_ARTICLE.search(final)
        m_opus = RE_OPUS.search(final)
        m_ss = RE_BANGUMI_SS.search(final)
        m_ep = RE_BANGUMI_EP.search(final)
        if m_opus:
            # v2.8.1+：opus 必须标记 is_opus，走新端点
            classified = ParsedItem("article", m_opus.group(1), it.value, is_opus=True)
        elif m_article:
            classified = ParsedItem("article", m_article.group(1), it.value, is_opus=False)
        elif m_ss:
            classified = ParsedItem("bangumi_ss", m_ss.group(1), it.value)
        elif m_ep:
            classified = ParsedItem("bangumi_ep", m_ep.group(1), it.value)
        else:
            # 退回 video 分类
            parsed = parse_text(final)
            if parsed:
                classified = parsed[0]
        if classified is not None:
            out.append(classified)
        # 解析失败就丢掉，不抛
    return _dedupe_keep_order(out)


def to_aid_string(parsed: ParsedItem) -> str:
    """返回适合传给 B 站 API 的 aid 字符串。仅供 fetcher 内部使用。"""
    if parsed.kind == "av":
        return parsed.value
    # bv 情况：fetcher 会自己用 bvid 参数
    return ""

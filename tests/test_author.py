"""v2.9.0+ AuthorVideoFetcher 单元测试。

注：真实 API 测试需要联网（且 B 站会限流），
本地测试只覆盖：
  - 时间归一化逻辑（_normalize_time_range）
  - pubdate 提取（_extract_pubdate）
  - ParsedItem 转换的形状
  - 输入校验
"""
import unittest
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import patch, MagicMock

from bilibili_tool.author import AuthorVideoFetcher, TZ_BJ
from bilibili_tool.parser import ParsedItem


def _now_ts() -> int:
    """现在的时间戳（秒），用于测试。"""
    return int(datetime.now(TZ_BJ).timestamp())


def _make_archive(
    bvid: str = "BV1abc",
    aid: int = 170001,
    days_ago: int = 0,
    pubdate: Optional[int] = None,
):
    """模拟 B 站 archive / vlist 字典。

    pubdate 优先用显式传入的（用于 unit test 边界值），
    否则按 days_ago 自动算"几天前"（用于时间过滤测试）。
    """
    if pubdate is None:
        pubdate = _now_ts() - days_ago * 86400
    return {
        "bvid": bvid,
        "aid": aid,
        "title": f"测试视频 {bvid}",
        "pubdate": pubdate,
        "author": "test",
    }


class TestNormalizeTimeRange(unittest.TestCase):
    """_normalize_time_range 把 days/since/until 归一化成 (start_ts, end_ts)。"""

    def setUp(self):
        self.fetcher = AuthorVideoFetcher()

    def test_all_none_returns_all_none(self):
        """全部 None → 不过滤"""
        start, end = self.fetcher._normalize_time_range(None, None, None)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_days_positive(self):
        """days=N（N>0）→ start_ts 是 N 天前 00:00:00，end=None"""
        now = datetime.now(TZ_BJ)
        start, end = self.fetcher._normalize_time_range(7, None, None)
        self.assertIsNone(end)
        self.assertIsNotNone(start)
        # 验证是约 7 天前
        start_dt = datetime.fromtimestamp(start, tz=TZ_BJ)
        delta = now - start_dt
        # 容忍 ±1 天的误差（因为 hours=0 截断）
        self.assertGreater(delta.days, 5)
        self.assertLess(delta.days, 8)

    def test_since_only(self):
        """只给 since → (start_ts, None)"""
        since = datetime(2026, 8, 1, 12, 30, 0)
        start, end = self.fetcher._normalize_time_range(None, since, None)
        self.assertIsNone(end)
        # 验证时间戳
        self.assertEqual(start, int(since.replace(tzinfo=TZ_BJ).timestamp()))

    def test_until_only(self):
        """只给 until → (None, end_ts)"""
        until = datetime(2026, 8, 21, 0, 0, 0)
        start, end = self.fetcher._normalize_time_range(None, None, until)
        self.assertIsNone(start)
        self.assertEqual(end, int(until.replace(tzinfo=TZ_BJ).timestamp()))

    def test_since_and_until(self):
        """since+until 都给 → 完整范围"""
        since = datetime(2026, 8, 1)
        until = datetime(2026, 8, 21)
        start, end = self.fetcher._normalize_time_range(None, since, until)
        self.assertEqual(start, int(since.replace(tzinfo=TZ_BJ).timestamp()))
        self.assertEqual(end, int(until.replace(tzinfo=TZ_BJ).timestamp()))

    def test_since_overrides_days(self):
        """显式 since 优先于 days"""
        since = datetime(2026, 1, 1)
        start, end = self.fetcher._normalize_time_range(7, since, None)
        # 应该是 2026-01-01 的时间戳，不是 7 天前
        self.assertEqual(start, int(since.replace(tzinfo=TZ_BJ).timestamp()))

    def test_days_zero_or_negative_ignored(self):
        """days=0 或负数 → 当 None 处理（不过滤）"""
        start, end = self.fetcher._normalize_time_range(0, None, None)
        self.assertIsNone(start)
        self.assertIsNone(end)


class TestExtractPubdate(unittest.TestCase):
    """_extract_pubdate 从 archive 字典提 pubdate。"""

    def setUp(self):
        self.fetcher = AuthorVideoFetcher()

    def test_new_endpoint_field(self):
        """新端点用 'pubdate' 字段"""
        arc = _make_archive("BV1xxx", pubdate=1700000000)
        self.assertEqual(self.fetcher._extract_pubdate(arc), 1700000000)

    def test_old_endpoint_field(self):
        """旧端点用 'created' 字段"""
        arc = {"bvid": "BV1xxx", "created": 1700000000}
        self.assertEqual(self.fetcher._extract_pubdate(arc), 1700000000)

    def test_missing_returns_zero(self):
        """没有 pubdate 字段 → 0（会被 start_ts 过滤掉）"""
        self.assertEqual(self.fetcher._extract_pubdate({"bvid": "BV1xxx"}), 0)
        self.assertEqual(self.fetcher._extract_pubdate({}), 0)

    def test_invalid_value_returns_zero(self):
        arc = {"pubdate": "not_a_number"}
        self.assertEqual(self.fetcher._extract_pubdate(arc), 0)


class TestFetchPageSeekArc(unittest.TestCase):
    """_fetch_page_seek_arc 新端点解析（mock 响应）。"""

    def setUp(self):
        self.fetcher = AuthorVideoFetcher()

    def test_success_response(self):
        """新端点成功响应：data.items[].archives[] 嵌套"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "archives": [
                            _make_archive("BV1aaa", 1001, days_ago=1),
                            _make_archive("BV1bbb", 1002, days_ago=2),
                        ]
                    }
                ]
            }
        }
        with patch.object(self.fetcher.sess, "get", return_value=mock_response):
            result = self.fetcher._fetch_page_seek_arc(123, pn=1, ps=50)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["bvid"], "BV1aaa")
        self.assertEqual(result[1]["bvid"], "BV1bbb")

    def test_non_zero_code_returns_none(self):
        """非 0 错误码 → 返回 None（降级到老端点）"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": -404, "message": "not found"}
        with patch.object(self.fetcher.sess, "get", return_value=mock_response):
            result = self.fetcher._fetch_page_seek_arc(123, pn=1, ps=50)
        self.assertIsNone(result)

    def test_empty_items(self):
        """items 为空 → 返回 []"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "data": {"items": []}}
        with patch.object(self.fetcher.sess, "get", return_value=mock_response):
            result = self.fetcher._fetch_page_seek_arc(123, pn=1, ps=50)
        self.assertEqual(result, [])


class TestFetchPageArcSearch(unittest.TestCase):
    """_fetch_page_arc_search 旧端点解析（mock 响应）。v2.9.1+ 已升级为 wbi 鉴权。"""

    def setUp(self):
        # v2.9.1+：注入预填的 mock wbi cache（不真发 nav 请求）
        from bilibili_tool.wbi import WbiKeyCache
        from datetime import datetime
        mock_cache = WbiKeyCache()
        mock_cache._img_key = "7cd084941338484aae1ad9425b84077b"
        mock_cache._sub_key = "4932caff0ff746eab6f01bf08b70ac45"
        mock_cache._fetched_at = datetime.now()
        self.fetcher = AuthorVideoFetcher(wbi_cache=mock_cache)

    def test_success_response(self):
        """v2.9.1+：wbi 端点响应 → data.list.vlist[]"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "data": {
                "list": {
                    "vlist": [
                        _make_archive("BV1ccc", 2001, days_ago=1),
                    ]
                }
            }
        }
        with patch.object(self.fetcher.sess, "get", return_value=mock_response):
            result = self.fetcher._fetch_page_arc_search(123, pn=1, ps=50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["bvid"], "BV1ccc")

    def test_412_fengce_returns_none(self):
        """412 风控 → 返回 None（用户需加 SESSDATA）"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": -352, "message": "fengce"}
        with patch.object(self.fetcher.sess, "get", return_value=mock_response):
            result = self.fetcher._fetch_page_arc_search(123, pn=1, ps=50)
        self.assertIsNone(result)


class TestFetchAuthorVideos(unittest.TestCase):
    """fetch_author_videos 集成：把 archives 转 ParsedItem + 时间过滤 + max_count。"""

    def setUp(self):
        self.fetcher = AuthorVideoFetcher()

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_basic_conversion(self, mock_seek, mock_old):
        """所有 archive 转 ParsedItem(kind=bv)"""
        # 只让 _fetch_page_seek_arc 返回数据；_fetch_page_arc_search 返回 None（避免被调）
        mock_seek.return_value = [
            _make_archive("BV1aaa", 1001, days_ago=1),
            _make_archive("BV1bbb", 1002, days_ago=2),
            _make_archive("BV1ccc", 1003, days_ago=3),
        ]
        mock_old.return_value = None
        result = self.fetcher.fetch_author_videos(123, days=30)
        self.assertEqual(len(result), 3)
        for item in result:
            self.assertIsInstance(item, ParsedItem)
            self.assertEqual(item.kind, "bv")
        self.assertEqual([p.value for p in result], ["BV1aaa", "BV1bbb", "BV1ccc"])

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_max_count_truncates(self, mock_seek, mock_old):
        """max_count=2 → 只返回 2 条"""
        mock_seek.return_value = [
            _make_archive("BV1aaa", 1001, days_ago=1),
            _make_archive("BV1bbb", 1002, days_ago=2),
            _make_archive("BV1ccc", 1003, days_ago=3),
        ]
        mock_old.return_value = None
        result = self.fetcher.fetch_author_videos(123, days=30, max_count=2)
        self.assertEqual(len(result), 2)
        self.assertEqual([p.value for p in result], ["BV1aaa", "BV1bbb"])

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_fallback_to_arc_search(self, mock_seek, mock_old):
        """新端点返回 None → 降级到旧端点"""
        mock_seek.return_value = None
        mock_old.return_value = [_make_archive("BV1fall", 3001, days_ago=1)]
        result = self.fetcher.fetch_author_videos(123, days=30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, "BV1fall")
        # 验证：旧端点被调用了
        mock_old.assert_called()

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_both_endpoints_fail_returns_empty(self, mock_seek, mock_old):
        """两个端点都失败 → 返回 []（不抛异常）"""
        mock_seek.return_value = None
        mock_old.return_value = None
        result = self.fetcher.fetch_author_videos(123, days=30)
        self.assertEqual(result, [])

    def test_invalid_uid_raises(self):
        """uid 不是正整数 → ValueError"""
        with self.assertRaises(ValueError):
            self.fetcher.fetch_author_videos(0)
        with self.assertRaises(ValueError):
            self.fetcher.fetch_author_videos(-1)
        with self.assertRaises(ValueError):
            self.fetcher.fetch_author_videos("123")  # type: ignore

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_no_results(self, mock_seek, mock_old):
        """UP 主没投稿 → 返回 []"""
        mock_seek.return_value = []
        mock_old.return_value = None
        result = self.fetcher.fetch_author_videos(123, days=30)
        self.assertEqual(result, [])

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_falls_back_to_aid_when_no_bvid(self, mock_seek, mock_old):
        """archive 缺 bvid 但有 aid → 转 ParsedItem(kind=av)"""
        now_ts = _now_ts()
        mock_seek.return_value = [
            {"bvid": "", "aid": 12345, "pubdate": now_ts - 86400},
            _make_archive("BV1normal", 9999, days_ago=1),
        ]
        mock_old.return_value = None
        result = self.fetcher.fetch_author_videos(123, days=30)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].kind, "av")
        self.assertEqual(result[0].value, "12345")
        self.assertEqual(result[1].kind, "bv")
        self.assertEqual(result[1].value, "BV1normal")

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_time_filter_stops_early_on_descending(self, mock_seek, mock_old):
        """按时间倒序：一旦早于 start_ts 就停止（不浪费后续请求）"""
        now_ts = _now_ts()
        mock_seek.return_value = [
            _make_archive("BV1new", 1, pubdate=now_ts - 86400),      # 1 天前
            _make_archive("BV1mid", 2, pubdate=now_ts - 86400 * 2),  # 2 天前
            _make_archive("BV1old", 3, pubdate=now_ts - 86400 * 3),  # 3 天前
        ]
        mock_old.return_value = None
        # start_ts 在 2 天前和 3 天前之间，应该只拿前 2 条
        start_dt = datetime.fromtimestamp(now_ts - 86400 * 2.5, tz=TZ_BJ)
        result = self.fetcher.fetch_author_videos(123, since=start_dt)
        self.assertEqual(len(result), 2)
        self.assertEqual([p.value for p in result], ["BV1new", "BV1mid"])


if __name__ == "__main__":
    unittest.main()

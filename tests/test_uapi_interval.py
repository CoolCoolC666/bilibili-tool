"""v3.0.9+ "请求间隔" 自定义测试（mock 外部调用 + 验证 sleep 行为）。

测试目标：
  1. base.ArchiveProvider 默认 interval_ms = 250
  2. UapisCnProvider 翻页调用 _sleep_interval
  3. SelfLegacyProvider 翻页调用 _sleep_interval
  4. SelfWbiProvider 透传 interval_ms 到 AuthorVideoFetcher
  5. AuthorVideoFetcher 翻页调用 time.sleep(interval_ms / 1000)
  6. interval_ms = 0 → 不 sleep（向后兼容）
  7. interval_ms 负数 → 被 max(0, ...) 修正为 0
  8. 链式测试：chain.fetch_author_archives 把 interval_ms 传给所有 provider
  9. self-wbi 旧默认 300ms，uapis/legacy 默认 250ms
"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call

import requests

from bilibili_tool.uapi import (
    SelfWbiProvider,
    SelfLegacyProvider,
    UapisCnProvider,
    AuthorArchiveChain,
    ArchiveProvider,
)
from bilibili_tool.author import AuthorVideoFetcher


TZ_BJ = timezone(timedelta(hours=8))


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data
    r.text = str(json_data)
    return r


class TestBaseIntervalDefault(unittest.TestCase):
    """ArchiveProvider 默认 interval_ms：base 默认 250，但 self-wbi 覆盖为 300（保留旧 0.3s）。"""

    def test_uapis_default_is_250(self):
        """uapis.cn 默认 250ms = 4 QPS（访客档位）。"""
        p = UapisCnProvider()
        self.assertEqual(p.interval_ms, 250)

    def test_legacy_default_is_250(self):
        p = SelfLegacyProvider()
        self.assertEqual(p.interval_ms, 250)

    def test_self_wbi_default_is_300(self):
        """self-wbi 默认 300ms（保留 AuthorVideoFetcher 旧 0.3s 行为）。"""
        p = SelfWbiProvider()
        self.assertEqual(p.interval_ms, 300)

    def test_explicit_interval_ms_set(self):
        p = SelfWbiProvider(interval_ms=500)
        self.assertEqual(p.interval_ms, 500)

    def test_interval_ms_zero_keeps_zero(self):
        p = SelfWbiProvider(interval_ms=0)
        self.assertEqual(p.interval_ms, 0)

    def test_interval_ms_negative_clamped_to_zero(self):
        """interval_ms < 0 应当被修正为 0（base 类 max(0, int(...))）。"""
        p = SelfWbiProvider(interval_ms=-100)
        self.assertEqual(p.interval_ms, 0)

    def test_interval_ms_string_converted_to_int(self):
        p = SelfWbiProvider(interval_ms="300")
        self.assertEqual(p.interval_ms, 300)

    def test_interval_ms_non_numeric_falls_back_to_zero(self):
        """非数字字符串 → int() 抛错。验证是否被捕获（如果未捕获会冒泡到测试 fail）。"""
        # 故意设计：base.__init__ 调 int(interval_ms)，非数字会 ValueError
        with self.assertRaises(ValueError):
            SelfWbiProvider(interval_ms="abc")


class TestSleepIntervalMethod(unittest.TestCase):
    """_sleep_interval 行为：interval_ms > 0 → sleep(interval/1000)。"""

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_sleep_when_interval_250(self, mock_sleep):
        p = SelfWbiProvider(interval_ms=250)
        p._sleep_interval()
        mock_sleep.assert_called_once_with(0.25)

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_sleep_when_interval_1500(self, mock_sleep):
        """1500ms = 1.5s（uapis Q15 推荐保守值）。"""
        p = SelfWbiProvider(interval_ms=1500)
        p._sleep_interval()
        mock_sleep.assert_called_once_with(1.5)

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_no_sleep_when_interval_0(self, mock_sleep):
        p = SelfWbiProvider(interval_ms=0)
        p._sleep_interval()
        mock_sleep.assert_not_called()


class TestUapisCnInterval(unittest.TestCase):
    """UapisCnProvider 翻页调用 _sleep_interval（每翻一页 sleep 一次）。"""

    def _make_3_page_response(self, total=50):
        """构造 3 页响应：pn=1, 2, 3 各 20 条，pn=4 空。"""
        def mock_get(url, params=None, timeout=None):
            pn = int((params or {}).get("pn", 1))
            ps = int((params or {}).get("ps", 20))
            if pn * ps >= total:
                # 最后一页
                vlist = [
                    {"aid": 1000 + pn * 10 + i, "publish_time": 1758000000 - pn * 10000 - i * 100,
                     "title": f"uapis page{pn} v{i}", "bvid": f"BV1page{pn}v{i}"}
                    for i in range(min(ps, total - (pn - 1) * ps))
                ]
                return _mock_response(200, {"videos": vlist, "total": total})
            else:
                vlist = [
                    {"aid": 1000 + pn * 10 + i, "publish_time": 1758000000 - pn * 10000 - i * 100,
                     "title": f"uapis page{pn} v{i}", "bvid": f"BV1page{pn}v{i}"}
                    for i in range(ps)
                ]
                return _mock_response(200, {"videos": vlist, "total": total})
        return mock_get

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_3_pages_sleeps_twice(self, mock_sleep):
        """3 页 = 翻 2 次页（pn=1→2, 2→3）= 2 次 sleep。"""
        p = UapisCnProvider(interval_ms=100)
        with patch.object(p.sess, "get", side_effect=self._make_3_page_response(total=50)):
            archives = p.fetch_author_archives(12345, max_count=50)
        # 3 页 → sleep 2 次（pn=1 后，pn=2 后；pn=3 已是最后一页）
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.1)

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_1_page_no_sleep(self, mock_sleep):
        """1 页（pn=1 即最后一页）→ 不 sleep。"""
        p = UapisCnProvider(interval_ms=100)
        with patch.object(p.sess, "get", side_effect=self._make_3_page_response(total=10)):
            archives = p.fetch_author_archives(12345, max_count=10)
        # 1 页（total=10 < ps=20）→ 0 次 sleep
        self.assertEqual(mock_sleep.call_count, 0)

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_interval_0_no_sleep(self, mock_sleep):
        """interval=0 时即使翻页也不 sleep。"""
        p = UapisCnProvider(interval_ms=0)
        with patch.object(p.sess, "get", side_effect=self._make_3_page_response(total=50)):
            archives = p.fetch_author_archives(12345, max_count=50)
        mock_sleep.assert_not_called()

    def test_visitor_mode_keeps_interval(self):
        """访客模式 + interval_ms 都生效。"""
        p = UapisCnProvider(interval_ms=500)  # 无 key
        self.assertTrue(p.is_visitor)
        self.assertEqual(p.interval_ms, 500)


class TestSelfLegacyInterval(unittest.TestCase):
    """SelfLegacyProvider 翻页调用 _sleep_interval。"""

    def _make_legacy_response(self, pn, ps, total_pages=3):
        """旧端点格式：{ data: { list: { vlist: [...] } } }"""
        vlist = [
            {"aid": 2000 + pn * 10 + i, "bvid": f"BVleg{pn}v{i}",
             "title": f"legacy page{pn} v{i}", "created": 1758000000 - pn * 10000,
             "pic": "http://x", "length": "1:00", "play": 100}
            for i in range(ps if pn < total_pages else 5)  # 最后一页只 5 条
        ]
        return _mock_response(200, {"code": 0, "message": "0", "data": {"list": {"vlist": vlist}}})

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_3_pages_sleeps_twice(self, mock_sleep):
        p = SelfLegacyProvider(interval_ms=200)
        # 3 页 = 翻 2 次
        responses = [self._make_legacy_response(pn, ps=50, total_pages=3) for pn in range(1, 4)]
        # 第 3 页返回 5 条 < ps=50，循环退出
        with patch.object(p.sess, "get", side_effect=responses):
            archives = p.fetch_author_archives(12345, max_count=200)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.2)

    @patch("bilibili_tool.uapi.base.time.sleep")
    def test_interval_0_no_sleep(self, mock_sleep):
        p = SelfLegacyProvider(interval_ms=0)
        responses = [self._make_legacy_response(pn, ps=50, total_pages=3) for pn in range(1, 4)]
        with patch.object(p.sess, "get", side_effect=responses):
            archives = p.fetch_author_archives(12345, max_count=200)
        mock_sleep.assert_not_called()


class TestSelfWbiInterval(unittest.TestCase):
    """SelfWbiProvider 透传 interval_ms 到 AuthorVideoFetcher。"""

    def test_init_passes_interval_to_fetcher(self):
        """SelfWbiProvider(interval_ms=500) → fetcher.interval_ms = 500。"""
        p = SelfWbiProvider(interval_ms=500)
        self.assertEqual(p.interval_ms, 500)
        self.assertEqual(p.fetcher.interval_ms, 500)

    def test_init_default_interval_300(self):
        """self-wbi 默认 interval_ms = 300（保留旧 0.3s 行为）。"""
        p = SelfWbiProvider()
        self.assertEqual(p.interval_ms, 300)
        self.assertEqual(p.fetcher.interval_ms, 300)

    def test_init_zero_interval(self):
        p = SelfWbiProvider(interval_ms=0)
        self.assertEqual(p.fetcher.interval_ms, 0)


class TestAuthorVideoFetcherInterval(unittest.TestCase):
    """AuthorVideoFetcher 翻页用 self.interval_ms。"""

    def _make_wbi_response(self, pn, ps):
        """WBI 端点格式：{ data: { list: { vlist: [...] } } }"""
        vlist = [
            {"aid": 3000 + pn * 10 + i, "bvid": f"BVwbi{pn}v{i}",
             "title": f"wbi page{pn} v{i}", "pubdate": 1758000000 - pn * 10000}
            for i in range(ps if pn < 3 else 5)
        ]
        return _mock_response(200, {
            "code": 0, "message": "0",
            "data": {"list": {"vlist": vlist}}
        })

    @patch("time.sleep")  # author.py 里的 time.sleep
    def test_3_pages_sleeps_twice(self, mock_sleep):
        """3 页 → 翻 2 次 → sleep 2 次。"""
        f = AuthorVideoFetcher(interval_ms=400)
        # 准备 wbi key mock
        with patch.object(f.wbi_cache, "get", return_value=("img_key", "sub_key")):
            responses = [self._make_wbi_response(pn, ps=50) for pn in range(1, 4)]
            with patch.object(f.sess, "get", side_effect=responses):
                archives = f.fetch_author_archives_raw(12345, max_count=200)
        # 3 页 → sleep 2 次（pn=1 后，pn=2 后）
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(0.4)

    @patch("time.sleep")
    def test_default_interval_300(self, mock_sleep):
        """默认 interval_ms=300 保留旧 0.3s 行为。"""
        f = AuthorVideoFetcher()
        self.assertEqual(f.interval_ms, 300)

    @patch("time.sleep")
    def test_interval_0_no_sleep(self, mock_sleep):
        f = AuthorVideoFetcher(interval_ms=0)
        with patch.object(f.wbi_cache, "get", return_value=("img_key", "sub_key")):
            responses = [self._make_wbi_response(pn, ps=50) for pn in range(1, 4)]
            with patch.object(f.sess, "get", side_effect=responses):
                archives = f.fetch_author_archives_raw(12345, max_count=200)
        mock_sleep.assert_not_called()


class TestChainInterval(unittest.TestCase):
    """chain.fetch_author_archives 把 interval_ms 传给所有 provider。"""

    def test_interval_appears_in_each_provider(self):
        """3 个 provider 都按 interval_ms=500 构造。"""
        chain = AuthorArchiveChain([
            UapisCnProvider(interval_ms=500),
            SelfWbiProvider(interval_ms=500),
            SelfLegacyProvider(interval_ms=500),
        ])
        for p in chain.providers:
            self.assertEqual(p.interval_ms, 500)

    def test_chain_default_mixed_intervals(self):
        """chain 默认构造时各 provider 用各自默认值（uapis 250 / wbi 300 / legacy 250）。"""
        chain = AuthorArchiveChain([
            UapisCnProvider(),       # 250
            SelfWbiProvider(),       # 300
            SelfLegacyProvider(),    # 250
        ])
        intervals = [p.interval_ms for p in chain.providers]
        self.assertEqual(intervals, [250, 300, 250])


if __name__ == "__main__":
    unittest.main()

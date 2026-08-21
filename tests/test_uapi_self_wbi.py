"""self-wbi / self-legacy provider 测试。"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import requests

from bilibili_tool.uapi import (
    SelfWbiProvider,
    SelfLegacyProvider,
    UapiError,
    UapiRateLimitError,
)


TZ_BJ = timezone(timedelta(hours=8))


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data
    r.text = str(json_data)
    return r


class TestSelfWbiProvider(unittest.TestCase):
    """SelfWbiProvider 适配 AuthorVideoFetcher。"""

    def test_init_no_key_needed(self):
        """self-wbi 不需要 key。"""
        p = SelfWbiProvider()
        self.assertEqual(p.name, "self-wbi")
        self.assertFalse(p.requires_key)
        self.assertIsNone(p.api_key)

    def test_init_ignores_api_key(self):
        """传 key 也忽略（self-wbi 不用 key）。"""
        p = SelfWbiProvider(api_key="ignored")
        self.assertIsNone(p.api_key)

    def test_fetch_success(self):
        """mock 内部 fetcher 成功。"""
        fake_archives = [
            {"aid": 100, "bvid": "BV1wbi1", "title": "wbi video 1", "pubdate": 1758000000},
            {"aid": 101, "bvid": "BV1wbi2", "title": "wbi video 2", "pubdate": 1757900000},
        ]
        p = SelfWbiProvider()
        p.fetcher = MagicMock()
        p.fetcher.fetch_author_archives_raw.return_value = fake_archives

        results = p.fetch_author_archives(uid=123, max_count=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["bvid"], "BV1wbi1")
        p.fetcher.fetch_author_archives_raw.assert_called_once_with(
            uid=123, days=None, max_count=5, since=None, until=None,
        )

    def test_fetch_with_keyword_filters_client_side(self):
        """wbi 端点不原生支持 keyword，客户端过滤。"""
        fake_archives = [
            {"aid": 100, "bvid": "BV1a", "title": "Python tutorial", "pubdate": 1758000000},
            {"aid": 101, "bvid": "BV1b", "title": "Java tutorial", "pubdate": 1757900000},
        ]
        p = SelfWbiProvider()
        p.fetcher = MagicMock()
        p.fetcher.fetch_author_archives_raw.return_value = fake_archives

        results = p.fetch_author_archives(uid=123, keyword="python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bvid"], "BV1a")

    def test_fetch_keyword_case_insensitive(self):
        """keyword 过滤大小写不敏感。"""
        fake_archives = [
            {"aid": 100, "bvid": "BV1a", "title": "Python Tutorial", "pubdate": 1758000000},
        ]
        p = SelfWbiProvider()
        p.fetcher = MagicMock()
        p.fetcher.fetch_author_archives_raw.return_value = fake_archives

        results = p.fetch_author_archives(uid=123, keyword="PYTHON")
        self.assertEqual(len(results), 1)

    def test_fetch_timeout_raises_uapi_error(self):
        """requests.Timeout → UapiError。"""
        p = SelfWbiProvider()
        p.fetcher = MagicMock()
        p.fetcher.fetch_author_archives_raw.side_effect = requests.Timeout("timeout")

        with self.assertRaises(UapiError) as ctx:
            p.fetch_author_archives(uid=123)
        self.assertIn("超时", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, UapiRateLimitError)

    def test_fetch_network_error_raises_uapi_error(self):
        """requests.ConnectionError → UapiError。"""
        p = SelfWbiProvider()
        p.fetcher = MagicMock()
        p.fetcher.fetch_author_archives_raw.side_effect = requests.ConnectionError("reset")

        with self.assertRaises(UapiError):
            p.fetch_author_archives(uid=123)


class TestSelfLegacyProvider(unittest.TestCase):
    """SelfLegacyProvider 调旧端点 /x/space/arc/search。"""

    def test_init_no_key_needed(self):
        p = SelfLegacyProvider()
        self.assertEqual(p.name, "self-legacy")
        self.assertFalse(p.requires_key)

    def test_fetch_success(self):
        mock_data = {
            "code": 0,
            "data": {
                "list": {
                    "vlist": [
                        {
                            "aid": 100, "bvid": "BV1legacy1", "title": "legacy 1",
                            "pic": "...", "length": "00:01:00", "created": 1758000000,
                            "play": 500,
                        },
                        {
                            "aid": 101, "bvid": "BV1legacy2", "title": "legacy 2",
                            "pic": "...", "length": "00:02:00", "created": 1757900000,
                            "play": 300,
                        },
                    ]
                }
            }
        }
        p = SelfLegacyProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(200, mock_data)):
            results = p.fetch_author_archives(uid=123)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["bvid"], "BV1legacy1")
        self.assertEqual(results[0]["_source"], "self-legacy")
        self.assertEqual(results[0]["pubdate"], 1758000000)

    def test_fetch_minus_799_raises_rate_limit(self):
        """B 站 -799 → UapiRateLimitError（触发降级）。"""
        mock_data = {"code": -799, "message": "请求过于频繁，请稍后再试"}
        p = SelfLegacyProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(200, mock_data)):
            with self.assertRaises(UapiRateLimitError):
                p.fetch_author_archives(uid=123)

    def test_fetch_minus_403_raises_uapi_error(self):
        """B 站 -403 → UapiError（不触发降级）。"""
        mock_data = {"code": -403, "message": "非法访问"}
        p = SelfLegacyProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(200, mock_data)):
            with self.assertRaises(UapiError):
                p.fetch_author_archives(uid=123)

    def test_fetch_pagination_stops_at_max(self):
        mock_data = {
            "code": 0,
            "data": {
                "list": {
                    "vlist": [
                        {
                            "aid": 100 + i, "bvid": f"BV1p_{i}", "title": f"v{i}",
                            "pic": "...", "length": "00:01", "created": 1758000000 - i * 100,
                            "play": 10,
                        }
                        for i in range(10)
                    ]
                }
            }
        }
        p = SelfLegacyProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(200, mock_data)):
            results = p.fetch_author_archives(uid=123, max_count=3)
        self.assertEqual(len(results), 3)

    def test_fetch_keyword_filter(self):
        mock_data = {
            "code": 0,
            "data": {
                "list": {
                    "vlist": [
                        {"aid": 1, "bvid": "BV1a", "title": "Python", "pic": "", "length": "", "created": 1758000000, "play": 0},
                        {"aid": 2, "bvid": "BV1b", "title": "Java", "pic": "", "length": "", "created": 1757900000, "play": 0},
                    ]
                }
            }
        }
        p = SelfLegacyProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(200, mock_data)):
            results = p.fetch_author_archives(uid=123, keyword="py")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bvid"], "BV1a")

    def test_invalid_uid(self):
        p = SelfLegacyProvider()
        with self.assertRaises(ValueError):
            p.fetch_author_archives(uid=-1)


if __name__ == "__main__":
    unittest.main()

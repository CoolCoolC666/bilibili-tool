"""uapis.cn provider 测试（mock 外部调用，零真实网络请求）。"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import requests

from bilibili_tool.uapi import (
    UapisCnProvider,
    UapiError,
    UapiRateLimitError,
    UapiAuthError,
    UapiNotFoundError,
    UapiTimeoutError,
)


TZ_BJ = timezone(timedelta(hours=8))


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data
    r.text = str(json_data)
    return r


class TestUapisCnInit(unittest.TestCase):
    """密钥校验 + 访客模式。"""

    def test_init_with_valid_key(self):
        """uapi- 前缀 + 非空 → 正常初始化（登录用户模式）。"""
        p = UapisCnProvider(api_key="uapi-test-12345678")
        self.assertEqual(p.name, "uapis.cn")
        self.assertEqual(p.api_key, "uapi-test-12345678")
        self.assertFalse(p.is_visitor)
        self.assertEqual(p.mode, "logged_in")

    def test_init_visitor_mode_no_key(self):
        """v2.10.0+ 访客模式：不传 key + 环境变量无 → 正常初始化（不抛错）。"""
        import os
        old = os.environ.pop("UAPIS_CN_API_KEY", None)
        try:
            p = UapisCnProvider()
            self.assertIsNone(p.api_key)
            self.assertTrue(p.is_visitor)
            self.assertEqual(p.mode, "visitor")
            # 访客模式不携带 Authorization 头
            self.assertNotIn("Authorization", p.sess.headers)
        finally:
            if old is not None:
                os.environ["UAPIS_CN_API_KEY"] = old

    def test_init_with_key_adds_authorization_header(self):
        """有 key 时设置 Authorization: Bearer uapi-xxx。"""
        p = UapisCnProvider(api_key="uapi-test-12345678")
        self.assertEqual(p.sess.headers["Authorization"], "Bearer uapi-test-12345678")

    def test_visitor_session_has_no_authorization(self):
        """访客模式 session 不携带 Authorization 头。"""
        import os
        old = os.environ.pop("UAPIS_CN_API_KEY", None)
        try:
            p = UapisCnProvider()
            self.assertNotIn("Authorization", p.sess.headers)
            self.assertNotIn("authorization", p.sess.headers)
        finally:
            if old is not None:
                os.environ["UAPIS_CN_API_KEY"] = old

    def test_init_invalid_key_prefix_raises(self):
        """没 uapi- 前缀的 key 应抛 UapiAuthError（即使 requires_key=False）。"""
        with self.assertRaises(UapiAuthError) as ctx:
            UapisCnProvider(api_key="invalid-key")
        self.assertIn("uapi-", str(ctx.exception))

    def test_init_key_from_env(self):
        """没传 key + 环境变量有 → 正常初始化。"""
        import os
        os.environ["UAPIS_CN_API_KEY"] = "uapi-from-env"
        try:
            p = UapisCnProvider()
            self.assertEqual(p.api_key, "uapi-from-env")
            self.assertFalse(p.is_visitor)
        finally:
            os.environ.pop("UAPIS_CN_API_KEY")

    def test_init_explicit_key_overrides_env(self):
        """显式传入的 key 优先于环境变量。"""
        import os
        os.environ["UAPIS_CN_API_KEY"] = "uapi-from-env"
        try:
            p = UapisCnProvider(api_key="uapi-explicit")
            self.assertEqual(p.api_key, "uapi-explicit")
        finally:
            os.environ.pop("UAPIS_CN_API_KEY")


class TestUapisCnArchives(unittest.TestCase):
    """端点 1：UP 主投稿列表。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_archives_success_single_page(self):
        """单页 1 条，正常返回。"""
        mock_data = {
            "total": 1,
            "page": 1,
            "size": 20,
            "videos": [
                {
                    "aid": 115212162177124,
                    "bvid": "BV1JSpkzbEm6",
                    "title": "THE FINALS - 2025-09-16 12-41-39",
                    "cover": "http://i0.hdslb.com/bfs/archive/xxx.jpg",
                    "duration": 468,
                    "play_count": 210,
                    "publish_time": 1757999542,
                    "create_time": 1757999542,
                    "state": 0,
                    "is_ugc_pay": 0,
                    "is_interactive": False,
                }
            ],
        }
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)):
            results = self.provider.fetch_author_archives(483307278, max_count=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bvid"], "BV1JSpkzbEm6")
        self.assertEqual(results[0]["aid"], 115212162177124)
        self.assertEqual(results[0]["pubdate"], 1757999542)
        self.assertEqual(results[0]["play"], 210)
        self.assertEqual(results[0]["_source"], "uapis.cn")

    def test_archives_pagination(self):
        """两页 25 条（pn=1 拿 20 条，pn=2 拿 5 条），按时间倒序。"""
        # pn=1: 20 条
        page1 = {"total": 25, "page": 1, "size": 20, "videos": [
            {
                "aid": 100 + i, "bvid": f"BV1page1_{i:02d}", "title": f"page1 video {i}",
                "cover": "", "duration": 100, "play_count": 10,
                "publish_time": 1758000000 - i * 1000,  # 倒序
                "create_time": 1758000000, "state": 0, "is_ugc_pay": 0, "is_interactive": False,
            }
            for i in range(20)
        ]}
        # pn=2: 5 条
        page2 = {"total": 25, "page": 2, "size": 20, "videos": [
            {
                "aid": 200 + i, "bvid": f"BV1page2_{i:02d}", "title": f"page2 video {i}",
                "cover": "", "duration": 100, "play_count": 10,
                "publish_time": 1757980000 - i * 1000,
                "create_time": 1757980000, "state": 0, "is_ugc_pay": 0, "is_interactive": False,
            }
            for i in range(5)
        ]}
        responses = [_mock_response(200, page1), _mock_response(200, page2)]
        with patch.object(self.provider.sess, "get", side_effect=responses):
            results = self.provider.fetch_author_archives(483307278)
        self.assertEqual(len(results), 25)

    def test_archives_pagination_stops_at_max(self):
        """max_count=5 时只拿 5 条。"""
        page1 = {"total": 100, "page": 1, "size": 20, "videos": [
            {
                "aid": 100 + i, "bvid": f"BV1p1_{i:02d}", "title": f"v{i}",
                "cover": "", "duration": 100, "play_count": 10,
                "publish_time": 1758000000 - i * 1000,
                "create_time": 1758000000, "state": 0, "is_ugc_pay": 0, "is_interactive": False,
            }
            for i in range(20)
        ]}
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, page1)):
            results = self.provider.fetch_author_archives(483307278, max_count=5)
        self.assertEqual(len(results), 5)

    def test_archives_time_filter_since(self):
        """since 过滤：按 publish_time 倒序，遇到早于 since 的就停。"""
        page1 = {"total": 3, "page": 1, "size": 20, "videos": [
            {
                "aid": 101, "bvid": "BV1new", "title": "new",
                "cover": "", "duration": 100, "play_count": 10,
                "publish_time": 1758000000,
                "create_time": 1758000000, "state": 0, "is_ugc_pay": 0, "is_interactive": False,
            },
            {
                "aid": 102, "bvid": "BV1old", "title": "old",
                "cover": "", "duration": 100, "play_count": 10,
                "publish_time": 1757000000,  # 早于 since
                "create_time": 1757000000, "state": 0, "is_ugc_pay": 0, "is_interactive": False,
            },
        ]}
        since = datetime.fromtimestamp(1757500000, tz=TZ_BJ)
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, page1)):
            results = self.provider.fetch_author_archives(483307278, since=since)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["bvid"], "BV1new")

    def test_archives_invalid_uid(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_author_archives(-1)
        with self.assertRaises(ValueError):
            self.provider.fetch_author_archives(0)
        with self.assertRaises(ValueError):
            self.provider.fetch_author_archives("abc")  # type: ignore


class TestUapisCnErrors(unittest.TestCase):
    """错误码 → 异常类型映射。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_400_invalid_argument(self):
        """400 → UapiError（参数错误）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(400, {"code": "INVALID_ARGUMENT", "message": "Missing 'mid' parameter."}),
        ):
            with self.assertRaises(UapiError) as ctx:
                self.provider.fetch_author_archives(1)
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertNotIsInstance(ctx.exception, UapiRateLimitError)

    def test_401_auth_error(self):
        """401 → UapiAuthError（**不**触发降级）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(401, {"code": "UNAUTHORIZED", "message": "鉴权失败"}),
        ):
            with self.assertRaises(UapiAuthError):
                self.provider.fetch_author_archives(1)

    def test_404_not_found(self):
        """404 → UapiNotFoundError（**不**触发降级）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(404, {"code": "NOT_FOUND", "message": "User not found."}),
        ):
            with self.assertRaises(UapiNotFoundError):
                self.provider.fetch_author_archives(99999999)

    def test_429_rate_limit(self):
        """429 → UapiRateLimitError（**触发降级**）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(429, {"code": "RATE_LIMITED", "message": "请求过于频繁"}),
        ):
            with self.assertRaises(UapiRateLimitError) as ctx:
                self.provider.fetch_author_archives(1)
            self.assertEqual(ctx.exception.status_code, 429)

    def test_500_server_error(self):
        """500 → UapiError（服务器内部错误）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(500, {"code": "INTERNAL_SERVER_ERROR", "message": "Server error."}),
        ):
            with self.assertRaises(UapiError) as ctx:
                self.provider.fetch_author_archives(1)
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertNotIsInstance(ctx.exception, UapiRateLimitError)

    def test_502_upstream_error(self):
        """502 → UapiError（uapis 上游 B 站挂）。"""
        with patch.object(
            self.provider.sess, "get",
            return_value=_mock_response(502, {"code": "UPSTREAM_ERROR", "message": "Unable to fetch the data."}),
        ):
            with self.assertRaises(UapiError):
                self.provider.fetch_author_archives(1)

    def test_timeout_raises_timeout_error(self):
        """requests.Timeout → UapiTimeoutError。"""
        with patch.object(
            self.provider.sess, "get",
            side_effect=requests.Timeout("read timed out"),
        ):
            with self.assertRaises(UapiTimeoutError):
                self.provider.fetch_author_archives(1)

    def test_network_error_raises_uapi_error(self):
        """其他 requests 异常 → UapiError。"""
        with patch.object(
            self.provider.sess, "get",
            side_effect=requests.ConnectionError("connection reset"),
        ):
            with self.assertRaises(UapiError) as ctx:
                self.provider.fetch_author_archives(1)
            self.assertIn("网络错误", str(ctx.exception))


class TestUapisCnUserInfo(unittest.TestCase):
    """端点 2：UP 主信息。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_userinfo_success(self):
        mock_data = {
            "mid": 483307278, "name": "bishi", "sex": "保密",
            "face": "http://i0.hdslb.com/bfs/face/xxx.jpg",
            "sign": "哔哩哔哩 - ( ゜- ゜)つロ 乾杯~",
            "level": 6, "birthday": "10-24", "vip_type": 2, "vip_status": 1,
            "following": 148, "follower": 123456, "archive_count": 321, "article_count": 12,
        }
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)):
            result = self.provider.fetch_user_info(483307278)
        self.assertEqual(result["name"], "bishi")
        self.assertEqual(result["level"], 6)


class TestUapisCnVideoInfo(unittest.TestCase):
    """端点 3：单视频详情。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_videoinfo_by_aid(self):
        mock_data = {
            "bvid": "BV17x411w79F", "aid": 75836761, "videos": 1, "tid": 31,
            "tname": "Vocaloid·UTAU", "title": "测试", "duration": 213,
            "owner": {"mid": 2, "name": "bishi", "face": "..."},
            "stat": {"view": 14227982, "like": 989718},
        }
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)) as mock_get:
            result = self.provider.fetch_video_info(aid=75836761)
        self.assertEqual(result["bvid"], "BV17x411w79F")
        # 验证请求参数
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["aid"], "75836761")
        self.assertNotIn("bvid", called_params)

    def test_videoinfo_by_bvid(self):
        mock_data = {"bvid": "BV17x411w79F", "aid": 75836761, "title": "测试"}
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)) as mock_get:
            result = self.provider.fetch_video_info(bvid="BV17x411w79F")
        self.assertEqual(result["aid"], 75836761)
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["bvid"], "BV17x411w79F")
        self.assertNotIn("aid", called_params)

    def test_videoinfo_requires_aid_or_bvid(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_video_info()


class TestUapisCnReplies(unittest.TestCase):
    """端点 4：视频评论。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_replies_success(self):
        mock_data = {
            "page": {"num": 1, "size": 20, "count": 100, "acount": 200},
            "hots": None,
            "replies": [
                {
                    "rpid": 4189337397, "oid": 1706416465, "mid": 12345678,
                    "root": 0, "parent": 0, "count": 5, "ctime": 1579532400,
                    "like": 1314,
                    "member": {"uname": "大神", "sex": "男", "avatar": "..."},
                    "content": {"message": "十年B站无人问"},
                }
            ],
        }
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)) as mock_get:
            result = self.provider.fetch_video_replies(1706416465, sort="hot")
        self.assertEqual(len(result["replies"]), 1)
        self.assertEqual(result["replies"][0]["rpid"], 4189337397)
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["oid"], "1706416465")
        self.assertEqual(called_params["sort"], "hot")

    def test_replies_ps_must_be_1_to_20(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_video_replies(1, ps=0)
        with self.assertRaises(ValueError):
            self.provider.fetch_video_replies(1, ps=21)


class TestUapisCnLiveRoom(unittest.TestCase):
    """端点 5：直播间。"""

    def setUp(self):
        self.provider = UapisCnProvider(api_key="uapi-test-12345678")

    def test_liveroom_by_mid(self):
        mock_data = {
            "uid": 672328094, "room_id": 22637261, "short_id": 22625027,
            "live_status": 1, "title": "【B限】杂谈",
            "online": 3662242, "parent_area_name": "虚拟主播",
        }
        with patch.object(self.provider.sess, "get", return_value=_mock_response(200, mock_data)) as mock_get:
            result = self.provider.fetch_live_room(mid=672328094)
        self.assertEqual(result["room_id"], 22637261)
        self.assertEqual(result["live_status"], 1)
        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["mid"], "672328094")

    def test_liveroom_requires_mid_or_room_id(self):
        with self.assertRaises(ValueError):
            self.provider.fetch_live_room()


if __name__ == "__main__":
    unittest.main()

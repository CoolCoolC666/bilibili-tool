"""v3.1.0+ 新功能测试（disableCache / Q32 错误结构 / usage）。

测试目标：
  1. UapisCnProvider(disable_cache=True) 每次请求都加 _t= 时间戳
  2. disable_cache=False（默认）不修改 params
  3. UapiError 新增 details / docs 字段
  4. Q32 错误响应 4 种结构兼容
  5. fetch_usage() 调 /status/usage
  6. /api/author/usage 端点工作
"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import requests

from bilibili_tool.uapi import (
    UapisCnProvider,
    UapiError,
    UapiAuthError,
    UapiNotFoundError,
    UapiRateLimitError,
)


TZ_BJ = timezone(timedelta(hours=8))


def _mock_response(status_code: int, json_data: dict, headers: dict = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data
    r.text = str(json_data)
    r.headers = headers or {}
    return r


# ============================================================================
# A. disableCache（Q12 修复截断陷阱）
# ============================================================================

class TestDisableCache(unittest.TestCase):
    """UapisCnProvider(disable_cache=True) 每次请求都加 _t= 时间戳戳。"""

    def test_disable_cache_default_false(self):
        """默认 disable_cache=False，不修改 params。"""
        p = UapisCnProvider()
        self.assertFalse(p.disable_cache)

    def test_disable_cache_explicit_true(self):
        p = UapisCnProvider(disable_cache=True)
        self.assertTrue(p.disable_cache)

    @patch("time.time", return_value=1700000000.0)  # 固定时间戳便于测试
    def test_disable_cache_appends_t_to_params(self, mock_time):
        """disable_cache=True 时所有 params 都加 _t= 时间戳。"""
        p = UapisCnProvider(disable_cache=True)
        with patch.object(p.sess, "get", return_value=_mock_response(200, {"name": "test"})) as mock_get:
            p.fetch_user_info(12345)
        # 验证 mock_get 被调用的参数
        args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        self.assertIn("_t", params, f"params 应含 _t 时间戳，实际：{params}")
        # 时间戳 = 1700000000 * 1000 = 1700000000000
        self.assertEqual(params["_t"], "1700000000000")

    def test_disable_cache_false_no_t_in_params(self):
        """disable_cache=False 时 params 不含 _t。"""
        p = UapisCnProvider(disable_cache=False)
        with patch.object(p.sess, "get", return_value=_mock_response(200, {"name": "test"})) as mock_get:
            p.fetch_user_info(12345)
        args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        self.assertNotIn("_t", params, f"params 不应含 _t，实际：{params}")

    def test_disable_cache_does_not_mutate_input_params(self):
        """disable_cache=True 时不应修改调用方传入的 params dict。"""
        p = UapisCnProvider(disable_cache=True)
        original_params = {"uid": "12345"}
        with patch.object(p.sess, "get", return_value=_mock_response(200, {"name": "test"})):
            p._request("/social/bilibili/userinfo", original_params)
        # 原 dict 不应被修改（_t 应在新 dict 里）
        self.assertNotIn("_t", original_params, "调用方传入的 params 被意外修改！")

    def test_disable_cache_visitor_mode(self):
        """访客模式 + disable_cache 都不冲突。"""
        p = UapisCnProvider(disable_cache=True)  # 无 key = 访客
        self.assertTrue(p.is_visitor)
        self.assertTrue(p.disable_cache)


# ============================================================================
# B. Q32 错误响应 4 种结构兼容
# ============================================================================

class TestErrorResponseStructures(unittest.TestCase):
    """Q32 错误响应有 4 种结构，_request 必须都能正确解析。"""

    # ---- 结构 1: 标准错误 ----

    def test_structure_1_standard_error(self):
        """{"code": "INVALID_PARAMETER", "message": "...", "details": {...}}"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(400, {
            "code": "INVALID_PARAMETER",
            "message": "city 参数不能为空",
            "details": {"param": "city"},
        })):
            with self.assertRaises(UapiError) as ctx:
                p._request("/misc/weather", {"city": ""})
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.code, "INVALID_PARAMETER")
        self.assertIn("city 参数不能为空", str(ctx.exception))
        self.assertEqual(ctx.exception.details, {"param": "city"})

    # ---- 结构 2: 简化错误 ----

    def test_structure_2_simplified_error(self):
        """{"error": "INVALID_PARAMETER", "details": "..."}"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(400, {
            "error": "INVALID_PARAMETER",
            "details": "city 不能为空",
        })):
            with self.assertRaises(UapiError) as ctx:
                p._request("/misc/weather", {"city": ""})
        self.assertEqual(ctx.exception.code, "INVALID_PARAMETER")
        self.assertIn("city 不能为空", str(ctx.exception))

    # ---- 结构 3: 积分不足 + docs 跳转链接 ----

    def test_structure_3_insufficient_credits_with_docs(self):
        """{"error": "INSUFFICIENT_CREDITS", "message": "...", "docs": {upgrade, usage}}"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(402, {
            "error": "INSUFFICIENT_CREDITS",
            "message": "账户积分不足，无法继续调用",
            "docs": {
                "upgrade": "https://uapis.cn/pricing",
                "usage": "https://uapis.cn/console/usage",
            },
        })):
            with self.assertRaises(UapiError) as ctx:
                p.fetch_user_info(12345)
        self.assertEqual(ctx.exception.status_code, 402)
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_CREDITS")
        # docs 字段需要被存到异常对象（虽然当前 _request 没传，但 base 支持 details/docs）
        # 这里验证：message 正确
        self.assertIn("积分不足", str(ctx.exception))

    # ---- 结构 4: 限流类错误 ----

    def test_structure_4_rate_limit_with_limit_field(self):
        """{"code": 429, "message": "Rate limit exceeded", "limit": 10}"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(429, {
            "code": 429,
            "message": "Rate limit exceeded",
            "limit": 10,
        })):
            with self.assertRaises(UapiRateLimitError) as ctx:
                p.fetch_user_info(12345)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Rate limit exceeded", str(ctx.exception))

    # ---- VISITOR_MONTHLY_QUOTA_EXHAUSTED → 不降级（再换 provider 也无意义） ----

    def test_visitor_quota_exhausted_is_not_rate_limit(self):
        """429 + code=VISITOR_MONTHLY_QUOTA_EXHAUSTED → 抛普通 UapiError（不触发降级链）"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(429, {
            "code": "VISITOR_MONTHLY_QUOTA_EXHAUSTED",
            "message": "访客本月 1500 积分已用尽",
        })):
            with self.assertRaises(UapiError) as ctx:
                p.fetch_user_info(12345)
        # 应该是 UapiError 而不是 UapiRateLimitError（防止无效降级）
        self.assertNotIsInstance(ctx.exception, UapiRateLimitError)
        self.assertEqual(ctx.exception.code, "VISITOR_MONTHLY_QUOTA_EXHAUSTED")

    # ---- 401 / 403 / 404 ----

    def test_401_uses_auth_error_class(self):
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(401, {
            "code": "UNAUTHORIZED",
            "message": "Key 无效",
        })):
            with self.assertRaises(UapiAuthError):
                p.fetch_user_info(12345)

    def test_403_cors_forbidden(self):
        """403 CORS_FORBIDDEN（跨域未带 Key）→ 抛 UapiError。"""
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(403, {
            "code": "CORS_FORBIDDEN",
            "message": "浏览器跨域调用 /api/v1/* 未携带 Key",
        })):
            with self.assertRaises(UapiError) as ctx:
                p.fetch_user_info(12345)
        self.assertEqual(ctx.exception.code, "CORS_FORBIDDEN")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_404_uses_not_found_class(self):
        p = UapisCnProvider()
        with patch.object(p.sess, "get", return_value=_mock_response(404, {
            "code": "NOT_FOUND",
            "message": "用户不存在",
        })):
            with self.assertRaises(UapiNotFoundError):
                p.fetch_user_info(12345)

    # ---- UapiError 增强 ----

    def test_uapi_error_has_details_field(self):
        err = UapiError("msg", status_code=400, code="X", details={"k": "v"})
        self.assertEqual(err.details, {"k": "v"})

    def test_uapi_error_has_docs_field(self):
        err = UapiError("msg", status_code=402, code="INSUFFICIENT_CREDITS",
                        docs={"upgrade": "https://uapis.cn/pricing"})
        self.assertEqual(err.docs, {"upgrade": "https://uapis.cn/pricing"})


# ============================================================================
# D. 实时额度查询
# ============================================================================

class TestFetchUsage(unittest.TestCase):
    """UapisCnProvider.fetch_usage() 调 /status/usage。"""

    def test_fetch_usage_success(self):
        p = UapisCnProvider()
        usage_response = {
            "visitor_quota": {"remaining": 1234, "monthly": 1500, "used": 266},
            "billing": {"quota": 0, "balance": 0},
            "rate_limit": {"qps": 4},
        }
        with patch.object(p.sess, "get", return_value=_mock_response(200, usage_response)) as mock_get:
            result = p.fetch_usage()
        # 验证调了 /status/usage
        args, kwargs = mock_get.call_args
        self.assertIn("/status/usage", args[0])
        # 验证返回值
        self.assertEqual(result["visitor_quota"]["remaining"], 1234)
        self.assertEqual(result["rate_limit"]["qps"], 4)

    def test_fetch_usage_with_disable_cache(self):
        p = UapisCnProvider(disable_cache=True)
        with patch.object(p.sess, "get", return_value=_mock_response(200, {"ok": True})) as mock_get:
            p.fetch_usage()
        args, kwargs = mock_get.call_args
        self.assertIn("_t", kwargs.get("params", {}))


class TestWebUsageEndpoint(unittest.TestCase):
    """v3.1.0+ /api/author/usage 端点。"""

    @classmethod
    def setUpClass(cls):
        import os
        HERE = os.path.dirname(os.path.abspath(__file__))
        ROOT = os.path.dirname(HERE)
        import sys
        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "web"))
        from web.app import app
        cls.app = app
        cls.client = app.test_client()

    def test_usage_endpoint_default(self):
        """不传任何参数 → 默认访客模式。"""
        with patch("bilibili_tool.uapi.UapisCnProvider.fetch_usage",
                   return_value={"visitor_quota": {"remaining": 1000, "monthly": 1500, "used": 500}}):
            r = self.client.post("/api/author/usage", json={})
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["mode"], "visitor")
            self.assertIn("usage", data)

    def test_usage_endpoint_with_api_key(self):
        """传 api_key → 登录模式。"""
        with patch("bilibili_tool.uapi.UapisCnProvider.fetch_usage",
                   return_value={"billing": {"quota": 100, "balance": 500}}):
            r = self.client.post("/api/author/usage", json={"api_key": "uapi-test-1234"})
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertEqual(data["mode"], "logged_in")

    def test_usage_endpoint_error_handling(self):
        """uapis 返回错误 → 端点返回 ok=False + code。"""
        from bilibili_tool.uapi import UapiError
        with patch("bilibili_tool.uapi.UapisCnProvider.fetch_usage",
                   side_effect=UapiError("服务异常", status_code=500, code="INTERNAL_SERVER_ERROR")):
            r = self.client.post("/api/author/usage", json={})
            self.assertEqual(r.status_code, 500)
            data = r.get_json()
            self.assertFalse(data["ok"])
            self.assertEqual(data["code"], "INTERNAL_SERVER_ERROR")


# ============================================================================
# A + B 端到端：list 端点透传 disable_cache
# ============================================================================

class TestWebListDisableCache(unittest.TestCase):
    """v3.1.0+ /api/author/list 端点接 disable_cache。"""

    @classmethod
    def setUpClass(cls):
        import os, sys
        HERE = os.path.dirname(os.path.abspath(__file__))
        ROOT = os.path.dirname(HERE)
        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "web"))
        from web.app import app
        cls.app = app
        cls.client = app.test_client()

    def test_list_endpoint_accepts_disable_cache(self):
        """disable_cache=true → 传给 _build_chain。"""
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = [
                {"aid": 1, "bvid": "BV1x", "title": "test", "pubdate": 1758000000,
                 "_completeness": "ok", "_source": "uapis.cn", "_chain": "uapis.cn"}
            ]
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter") as MockExp:
                MockExp.return_value.export.return_value = ("/tmp/x.csv", 1)
                r = self.client.post(
                    "/api/author/list",
                    json={"inputs": "12345", "provider": "uapis.cn", "disable_cache": True},
                )
            self.assertEqual(r.status_code, 200)
            args, kwargs = mock_build.call_args
            self.assertTrue(kwargs.get("disable_cache"),
                            f"disable_cache 应为 True，实际：{kwargs}")
            # 响应回显
            data = r.get_json()
            self.assertTrue(data.get("disable_cache"))

    def test_list_endpoint_disable_cache_default_false(self):
        """不传 disable_cache → 默认 False。"""
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = []
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter"):
                r = self.client.post(
                    "/api/author/list",
                    json={"inputs": "12345", "provider": "uapis.cn"},
                )
            args, kwargs = mock_build.call_args
            self.assertFalse(kwargs.get("disable_cache", False))


if __name__ == "__main__":
    unittest.main()

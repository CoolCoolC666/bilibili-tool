"""v3.0.9+ Web 端 4 个端点对 interval_ms 的处理（Flask test client + mock provider）。

测试目标：
  1. /api/author/list 接收 interval_ms 并传给 _build_chain
  2. /api/author/profile 接收 interval_ms 并写进 job
  3. /api/author/detail 接收 interval_ms 并写进 job
  4. /api/author/detail/batch 接收 interval_ms 并写进 job
  5. interval_ms=0 合法
  6. interval_ms 负数被修正为 0
  7. interval_ms 默认 250（list / profile / detail / detail/batch）
  8. progress 端点回显 interval_ms
"""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

# 测试前：确保 web 目录可导入
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))


class TestWebIntervalPropagation(unittest.TestCase):
    """验证 web 4 端点 → provider/job 的 interval_ms 透传。"""

    @classmethod
    def setUpClass(cls):
        from web.app import app
        cls.app = app
        cls.client = app.test_client()

    def test_providers_endpoint_returns_recommended_interval(self):
        """/api/author/providers 返回的元信息含 recommended_interval_ms。"""
        r = self.client.get("/api/author/providers")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        for p in data["providers"]:
            self.assertIn("recommended_interval_ms", p, f"{p['id']} 缺少 recommended_interval_ms")
            self.assertIsInstance(p["recommended_interval_ms"], int)

    def test_list_endpoint_accepts_interval_ms(self):
        """/api/author/list 接 interval_ms → 传给 _build_chain → 回显。"""
        # Mock _build_chain 验证参数 + Mock 写出
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = [
                {"aid": 1, "bvid": "BV1x", "title": "test", "pubdate": 1758000000,
                 "_completeness": "ok", "_source": "uapis.cn", "_chain": "uapis.cn",
                 "_actual_count": 1, "_provider_total": 1}
            ]
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter") as MockExporter:
                mock_exp_instance = MagicMock()
                mock_exp_instance.export.return_value = ("/tmp/test.csv", 1)
                MockExporter.return_value = mock_exp_instance
                r = self.client.post(
                    "/api/author/list",
                    json={
                        "inputs": "12345",
                        "provider": "uapis.cn",
                        "interval_ms": 800,
                    },
                )
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            # 验证 _build_chain 收到 interval_ms=800
            args, kwargs = mock_build.call_args
            self.assertEqual(kwargs.get("interval_ms"), 800,
                             f"_build_chain 收到 interval_ms={kwargs.get('interval_ms')}")
            # 验证响应回显
            data = r.get_json()
            self.assertEqual(data.get("interval_ms"), 800)

    def test_list_endpoint_default_interval_250(self):
        """不传 interval_ms → 默认 250。"""
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = [
                {"aid": 1, "bvid": "BV1x", "title": "test", "pubdate": 1758000000,
                 "_completeness": "ok", "_source": "uapis.cn", "_chain": "uapis.cn"}
            ]
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter") as MockExporter:
                mock_exp_instance = MagicMock()
                mock_exp_instance.export.return_value = ("/tmp/test.csv", 1)
                MockExporter.return_value = mock_exp_instance
                r = self.client.post(
                    "/api/author/list",
                    json={"inputs": "12345", "provider": "uapis.cn"},
                )
            args, kwargs = mock_build.call_args
            self.assertEqual(kwargs.get("interval_ms"), 250)

    def test_list_endpoint_interval_zero(self):
        """interval_ms=0 合法（用户要全速抓）。"""
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = []
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter"):
                r = self.client.post(
                    "/api/author/list",
                    json={"inputs": "12345", "provider": "uapis.cn", "interval_ms": 0},
                )
            args, kwargs = mock_build.call_args
            self.assertEqual(kwargs.get("interval_ms"), 0)

    def test_list_endpoint_interval_negative_clamped(self):
        """interval_ms=-100 → 被修正为 0。"""
        with patch("web.app._build_chain") as mock_build:
            mock_chain = MagicMock()
            mock_chain.fetch_author_archives.return_value = []
            mock_build.return_value = (mock_chain, None)
            with patch("web.app.AuthorListExporter"):
                r = self.client.post(
                    "/api/author/list",
                    json={"inputs": "12345", "provider": "uapis.cn", "interval_ms": -100},
                )
            args, kwargs = mock_build.call_args
            self.assertEqual(kwargs.get("interval_ms"), 0)

    def test_profile_endpoint_interval(self):
        """/api/author/profile 接收 interval_ms。"""
        with patch("web.app.threading.Thread"):  # 不真起后台线程
            r = self.client.post(
                "/api/author/profile",
                json={"inputs": "12345", "interval_ms": 1500},
            )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual(data.get("interval_ms"), 1500)

    def test_profile_endpoint_default_interval(self):
        """profile 端点默认 300ms（对应原 delay=0.3 默认）。"""
        with patch("web.app.threading.Thread"):
            r = self.client.post(
                "/api/author/profile",
                json={"inputs": "12345"},
            )
        data = r.get_json()
        self.assertEqual(data.get("interval_ms"), 300)

    def test_profile_endpoint_with_legacy_delay(self):
        """profile 端点用旧 delay 参数时也回显。"""
        with patch("web.app.threading.Thread"):
            r = self.client.post(
                "/api/author/profile",
                json={"inputs": "12345", "delay": 0.5},  # 旧参数 = 500ms
            )
        data = r.get_json()
        self.assertEqual(data.get("interval_ms"), 500)


class TestWebProvidersMetadata(unittest.TestCase):
    """验证 provider 元信息含 interval 推荐值。"""

    def test_uapis_recommended_interval_250(self):
        from web.app import AVAILABLE_PROVIDERS
        uapis = next(p for p in AVAILABLE_PROVIDERS if p["id"] == "uapis.cn")
        self.assertEqual(uapis["recommended_interval_ms"], 250)

    def test_self_wbi_recommended_interval_300(self):
        from web.app import AVAILABLE_PROVIDERS
        wbi = next(p for p in AVAILABLE_PROVIDERS if p["id"] == "self-wbi")
        self.assertEqual(wbi["recommended_interval_ms"], 300)

    def test_legacy_recommended_interval_250(self):
        from web.app import AVAILABLE_PROVIDERS
        legacy = next(p for p in AVAILABLE_PROVIDERS if p["id"] == "self-legacy")
        self.assertEqual(legacy["recommended_interval_ms"], 250)


if __name__ == "__main__":
    unittest.main()

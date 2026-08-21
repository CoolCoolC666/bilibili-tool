"""降级链 AuthorArchiveChain 测试。"""
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from bilibili_tool.uapi import (
    ArchiveProvider,
    UapiError,
    UapiRateLimitError,
    UapiAuthError,
    UapiNotFoundError,
    AuthorArchiveChain,
    SelfWbiProvider,
    UapisCnProvider,
)


def _make_mock_provider(name: str, *, return_value=None, side_effect=None) -> ArchiveProvider:
    """快速生成一个 mock provider。

    参数：
      return_value: 正常返回值（如 [{"bvid": "..."}]）
      side_effect: 异常 / 函数（用于模拟错误）
    """
    p = MagicMock(spec=ArchiveProvider)
    p.name = name
    p.description = f"mock {name}"
    p.requires_key = False
    if side_effect is not None:
        p.fetch_author_archives.side_effect = side_effect
    if return_value is not None:
        p.fetch_author_archives.return_value = return_value
    return p


class TestChainFallback(unittest.TestCase):
    """降级链：限流触发降级，其他错误直接抛。"""

    def test_chain_falls_back_on_rate_limit(self):
        """p1 限流 → 降级到 p2 成功。"""
        p1 = _make_mock_provider("p1", side_effect=UapiRateLimitError("p1 limited"))
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1xx"}])
        chain = AuthorArchiveChain([p1, p2])

        result = chain.fetch_author_archives(uid=123)
        # v3.0.5+：chain 给第一个 archive 加完整性元信息
        self.assertEqual(result[0]["bvid"], "BV1xx")
        self.assertIn("_completeness", result[0])
        self.assertIn("_chain", result[0])
        p1.fetch_author_archives.assert_called_once()
        p2.fetch_author_archives.assert_called_once()

    def test_chain_falls_back_through_multiple(self):
        """p1 限流 → p2 限流 → p3 成功。"""
        p1 = _make_mock_provider("p1", side_effect=UapiRateLimitError("p1"))
        p2 = _make_mock_provider("p2", side_effect=UapiRateLimitError("p2"))
        p3 = _make_mock_provider("p3", return_value=[{"bvid": "BV1fromP3"}])
        chain = AuthorArchiveChain([p1, p2, p3])

        result = chain.fetch_author_archives(uid=123)
        self.assertEqual(result[0]["bvid"], "BV1fromP3")
        self.assertEqual(result[0]["_chain"], "p3")
        p3.fetch_author_archives.assert_called_once()

    def test_chain_raises_when_all_rate_limited(self):
        """所有 provider 都限流 → 抛最后一个限流错误。"""
        e1 = UapiRateLimitError("p1 limited")
        e2 = UapiRateLimitError("p2 limited")
        p1 = _make_mock_provider("p1", side_effect=e1)
        p2 = _make_mock_provider("p2", side_effect=e2)
        chain = AuthorArchiveChain([p1, p2])

        with self.assertRaises(UapiRateLimitError) as ctx:
            chain.fetch_author_archives(uid=123)
        self.assertIn("都限流", str(ctx.exception))
        self.assertIn("p1", str(ctx.exception))
        self.assertIn("p2", str(ctx.exception))

    def test_chain_first_provider_succeeds_no_fallback(self):
        """p1 成功 → 不调 p2。"""
        p1 = _make_mock_provider("p1", return_value=[{"bvid": "BV1fromP1"}])
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1fromP2"}])
        chain = AuthorArchiveChain([p1, p2])

        result = chain.fetch_author_archives(uid=123)
        self.assertEqual(result[0]["bvid"], "BV1fromP1")
        self.assertEqual(result[0]["_chain"], "p1")
        p1.fetch_author_archives.assert_called_once()
        p2.fetch_author_archives.assert_not_called()


class TestChainNonRateLimit(unittest.TestCase):
    """降级链：非限流错误（鉴权/不存在/网络）直接抛，不降级。"""

    def test_auth_error_raises_immediately(self):
        """p1 鉴权失败 → 直接抛，不调 p2。"""
        p1 = _make_mock_provider("p1", side_effect=UapiAuthError("invalid key"))
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1xx"}])
        chain = AuthorArchiveChain([p1, p2])

        with self.assertRaises(UapiAuthError):
            chain.fetch_author_archives(uid=123)
        p2.fetch_author_archives.assert_not_called()

    def test_not_found_raises_immediately(self):
        """p1 资源不存在 → 直接抛。"""
        p1 = _make_mock_provider("p1", side_effect=UapiNotFoundError("user not found"))
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1xx"}])
        chain = AuthorArchiveChain([p1, p2])

        with self.assertRaises(UapiNotFoundError):
            chain.fetch_author_archives(uid=99999999)
        p2.fetch_author_archives.assert_not_called()

    def test_generic_uapi_error_raises_immediately(self):
        """p1 网络错误 → 直接抛。"""
        p1 = _make_mock_provider("p1", side_effect=UapiError("network error"))
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1xx"}])
        chain = AuthorArchiveChain([p1, p2])

        with self.assertRaises(UapiError):
            chain.fetch_author_archives(uid=123)
        p2.fetch_author_archives.assert_not_called()


class TestChainInit(unittest.TestCase):
    """降级链：构造校验。"""

    def test_empty_providers_raises(self):
        with self.assertRaises(ValueError):
            AuthorArchiveChain([])

    def test_single_provider(self):
        """1 个 provider 也能工作。"""
        p1 = _make_mock_provider("p1", return_value=[{"bvid": "BV1solo"}])
        chain = AuthorArchiveChain([p1])
        result = chain.fetch_author_archives(uid=1)
        self.assertEqual(result[0]["bvid"], "BV1solo")
        # v3.0.5+：chain 给第一个 archive 加完整性元信息
        self.assertIn("_completeness", result[0])

    def test_repr_shows_chain(self):
        p1 = MagicMock(spec=ArchiveProvider)
        p1.name = "self-wbi"
        p2 = MagicMock(spec=ArchiveProvider)
        p2.name = "uapis.cn"
        chain = AuthorArchiveChain([p1, p2])
        self.assertIn("self-wbi", repr(chain))
        self.assertIn("uapis.cn", repr(chain))
        self.assertIn("→", repr(chain))


class TestChainCompleteness(unittest.TestCase):
    """v3.0.5+：chain 评估数据完整性。"""

    def test_completeness_ok_when_ratio_high(self):
        """实际数 / reported >= 0.9 → ok。"""
        p1 = _make_mock_provider("p1", return_value=[{"bvid": "BV1"}] * 90)
        p1.last_reported_total = 100
        chain = AuthorArchiveChain([p1])
        result = chain.fetch_author_archives(uid=1)
        self.assertEqual(result[0]["_completeness"], "ok")
        self.assertEqual(result[0]["_chain"], "p1")
        self.assertEqual(result[0]["_provider_total"], 100)
        self.assertEqual(result[0]["_actual_count"], 90)

    def test_completeness_partial_when_ratio_low(self):
        """实际数 / reported < 0.5 → partial。"""
        p1 = _make_mock_provider("p1", return_value=[{"bvid": "BV1"}] * 10)
        p1.last_reported_total = 100
        chain = AuthorArchiveChain([p1])
        result = chain.fetch_author_archives(uid=1)
        self.assertEqual(result[0]["_completeness"], "partial")
        # 实际显示给用户
        self.assertEqual(result[0]["_provider_total"], 100)
        self.assertEqual(result[0]["_actual_count"], 10)

    def test_completeness_unknown_when_no_reported_total(self):
        """没 reported_total → unknown。"""
        p1 = _make_mock_provider("p1", return_value=[{"bvid": "BV1"}] * 10)
        # 不设 last_reported_total
        chain = AuthorArchiveChain([p1])
        result = chain.fetch_author_archives(uid=1)
        self.assertEqual(result[0]["_completeness"], "unknown")
        self.assertIsNone(result[0]["_provider_total"])

    def test_completeness_partial_real_case_warma(self):
        """模拟 Warma 真实场景：uapis report_total=262, 实际 71 → partial。"""
        p1 = _make_mock_provider("uapis.cn", return_value=[{"bvid": f"BV1{i}"} for i in range(71)])
        p1.last_reported_total = 262
        chain = AuthorArchiveChain([p1])
        result = chain.fetch_author_archives(uid=53456)
        # 27% ratio < 50% → partial
        self.assertEqual(result[0]["_completeness"], "partial")
        self.assertEqual(result[0]["_chain"], "uapis.cn")
        self.assertEqual(result[0]["_actual_count"], 71)
        self.assertEqual(result[0]["_provider_total"], 262)


class TestChainArguments(unittest.TestCase):
    """降级链：参数透传。"""

    def test_kwargs_propagated_to_providers(self):
        """所有 kwargs 透传到每个 provider。"""
        p1 = _make_mock_provider("p1", side_effect=UapiRateLimitError("limited"))
        p2 = _make_mock_provider("p2", return_value=[{"bvid": "BV1xx"}])
        chain = AuthorArchiveChain([p1, p2])

        since = datetime(2026, 1, 1)
        until = datetime(2026, 8, 21)
        chain.fetch_author_archives(
            uid=123, days=30, max_count=20, since=since, until=until, keyword="test",
        )

        # 两个 provider 都应该收到相同参数
        for p in (p1, p2):
            p.fetch_author_archives.assert_called_once_with(
                uid=123, days=30, max_count=20, since=since, until=until, keyword="test",
            )


class TestRealProviderIntegration(unittest.TestCase):
    """真实 provider 接入降级链的集成测试。"""

    def test_real_self_wbi_in_chain(self):
        """真实 SelfWbiProvider 接入（不需要 key）。"""
        # 用 mock 替换其内部 fetcher
        chain = AuthorArchiveChain([SelfWbiProvider()])
        # SelfWbiProvider 内部调用 AuthorVideoFetcher，会真去拉网络
        # 这里跳过实际调用，只验证 chain 能正常构造
        self.assertEqual(chain.providers[0].name, "self-wbi")

    def test_real_uapis_cn_visitor_mode_ok(self):
        """v2.10.0+ 真实 UapisCnProvider 接入：访客模式不需要 key。"""
        import os
        old = os.environ.pop("UAPIS_CN_API_KEY", None)
        try:
            p = UapisCnProvider()  # 访客模式
            self.assertTrue(p.is_visitor)
            chain = AuthorArchiveChain([p])
            self.assertEqual(chain.providers[0].name, "uapis.cn")
        finally:
            if old is not None:
                os.environ["UAPIS_CN_API_KEY"] = old

    def test_real_uapis_cn_logged_in_mode(self):
        """真实 UapisCnProvider 接入：登录用户模式需要 key。"""
        p = UapisCnProvider(api_key="uapi-test-12345678")
        self.assertFalse(p.is_visitor)
        chain = AuthorArchiveChain([p])
        self.assertEqual(chain.providers[0].name, "uapis.cn")


if __name__ == "__main__":
    unittest.main()

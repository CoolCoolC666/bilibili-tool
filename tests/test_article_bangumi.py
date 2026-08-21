"""v2.8.0 专栏 / 番剧集成测试：Cache 通用化 + dedupe。

注：ArticleFetcher / BangumiFetcher 的真实 API 测试需要联网，
只在本地用 mock 测试基本结构（已在 test_parser.py 测过 URL 解析）。
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from bilibili_tool.cache import (
    Cache,
    _article_fingerprint,
    _article_keys,
    _bangumi_fingerprint,
    _bangumi_keys,
)
from bilibili_tool.models import ArticleInfo, BangumiInfo, VideoInfo, explain_code


def make_article(*, cv_id="cv123", status="ok", view=1000, fetched_at=None,
                 is_opus=False, title=None, **kw) -> ArticleInfo:
    if fetched_at is None:
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if title is None:
        title = f"article-{cv_id}"
    return ArticleInfo(
        input_kind="article", cv_id=cv_id, title=title,
        author_name=f"author-{cv_id}", status=status, view=view,
        fetched_at=fetched_at, is_opus=is_opus, **kw,
    )


def make_bangumi(*, season_id=67890, ep_id=None, status="ok", rating_score=9.0, fetched_at=None, **kw) -> BangumiInfo:
    if fetched_at is None:
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return BangumiInfo(
        input_kind="bangumi_ss" if season_id else "bangumi_ep",
        season_id=season_id, ep_id=ep_id, title=f"bangumi-{season_id or ep_id}",
        status=status, rating_score=rating_score,
        fetched_at=fetched_at, **kw,
    )


class TestArticleCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_article_key_func(self):
        a = make_article(cv_id="cv123")
        keys = _article_keys(a)
        self.assertEqual(keys, ["cv:cv123"])

    def test_article_fingerprint(self):
        d = {"cv_id": "cv123", "raw_input": "x"}
        fp = _article_fingerprint(d)
        self.assertEqual(fp, ("cv123", "x"))

    def test_put_and_get_article(self):
        c = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        a = make_article(cv_id="cv123", view=500)
        c.put(a)
        # 索引写入了
        self.assertIn("cv:cv123", c._data)
        # 能取回
        got = c.get(make_article(cv_id="cv123"))
        self.assertIsNotNone(got)
        self.assertEqual(got.cv_id, "cv123")
        self.assertEqual(got.view, 500)

    def test_article_freshness(self):
        c = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        old = make_article(cv_id="cv1", view=100, fetched_at=(datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"))
        c.put(old)
        # max-age 1h 过期
        self.assertIsNone(c.get_fresh(make_article(cv_id="cv1"), max_age_seconds=3600))
        # max-age 3h 仍然新鲜
        self.assertIsNotNone(c.get_fresh(make_article(cv_id="cv1"), max_age_seconds=3 * 3600))

    def test_article_failed_always_fresh(self):
        c = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        very_old_failed = make_article(
            cv_id="cv1", status="not_found", api_code=404,
            fetched_at=(datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(very_old_failed)
        # max-age=0 也算新鲜（失败状态永远新鲜）
        self.assertIsNotNone(c.get_fresh(make_article(cv_id="cv1"), max_age_seconds=0))

    def test_article_unique_count(self):
        c = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        c.put(make_article(cv_id="cv1"))
        c.put(make_article(cv_id="cv2"))
        c.put(make_article(cv_id="cv3"))
        self.assertEqual(c.unique_count(), 3)
        self.assertEqual(c.stats()["ok"], 3)

    def test_article_persistence(self):
        c1 = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        c1.put(make_article(cv_id="cv1", view=123))
        c1.save()
        c2 = Cache(self.path, record_class=ArticleInfo, key_func=_article_keys, fingerprint=_article_fingerprint)
        got = c2.get(make_article(cv_id="cv1"))
        self.assertIsNotNone(got)
        self.assertEqual(got.view, 123)


class TestBangumiCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_bangumi_key_func_ss(self):
        b = make_bangumi(season_id=67890)
        keys = _bangumi_keys(b)
        self.assertEqual(keys, ["ss:67890"])

    def test_bangumi_key_func_ep(self):
        b = make_bangumi(season_id=None, ep_id=1438464)
        keys = _bangumi_keys(b)
        self.assertEqual(keys, ["ep:1438464"])

    def test_bangumi_key_func_both(self):
        b = make_bangumi(season_id=67890, ep_id=1438464)
        keys = _bangumi_keys(b)
        # 双索引：ss + ep 都有
        self.assertIn("ss:67890", keys)
        self.assertIn("ep:1438464", keys)

    def test_bangumi_fingerprint(self):
        d = {"season_id": 67890, "ep_id": 1438464, "raw_input": "x"}
        fp = _bangumi_fingerprint(d)
        self.assertEqual(fp, (67890, 1438464, "x"))

    def test_put_and_get_bangumi(self):
        c = Cache(self.path, record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint)
        b = make_bangumi(season_id=67890, rating_score=9.5)
        c.put(b)
        self.assertIn("ss:67890", c._data)
        got = c.get(make_bangumi(season_id=67890))
        self.assertIsNotNone(got)
        self.assertEqual(got.rating_score, 9.5)

    def test_bangumi_dual_index_lookup(self):
        """ss + ep 同时存，按任意一种都能查到。"""
        c = Cache(self.path, record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint)
        b = make_bangumi(season_id=67890, ep_id=1438464, rating_score=9.5)
        c.put(b)
        # 用 season 查
        by_ss = c.get(make_bangumi(season_id=67890))
        self.assertIsNotNone(by_ss)
        # 用 ep 查
        by_ep = c.get(make_bangumi(season_id=None, ep_id=1438464))
        self.assertIsNotNone(by_ep)
        # 同一份数据
        self.assertEqual(by_ss.title, by_ep.title)
        # unique_count 是 1
        self.assertEqual(c.unique_count(), 1)

    def test_bangumi_persistence_dual(self):
        """存盘后再加载，双索引仍然有效。"""
        c1 = Cache(self.path, record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint)
        c1.put(make_bangumi(season_id=67890, ep_id=1438464, rating_score=9.5))
        c1.save()
        c2 = Cache(self.path, record_class=BangumiInfo, key_func=_bangumi_keys, fingerprint=_bangumi_fingerprint)
        self.assertIsNotNone(c2.get(make_bangumi(season_id=67890)))
        self.assertIsNotNone(c2.get(make_bangumi(season_id=None, ep_id=1438464)))
        self.assertEqual(c2.unique_count(), 1)


class TestCacheBackwardCompat(unittest.TestCase):
    """v2.8.0 旧 API 完全兼容。"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_default_cache_uses_video(self):
        """不传 record_class 也能用（默认 VideoInfo）"""
        c = Cache(self.path)
        v = VideoInfo(input_kind="bv", bvid="BV1xxx", title="旧", status="ok", view=100,
                      fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        c.put(v)
        self.assertIn("bv:BV1xxx", c._data)
        got = c.get(VideoInfo(input_kind="bv", bvid="BV1xxx"))
        self.assertEqual(got.view, 100)

    def test_old_video_cache_loads_correctly(self):
        """旧的 video cache.json 仍然能读"""
        import json
        old_data = {
            "bv:BV1xxx": {
                "bvid": "BV1xxx", "aid": 170001, "title": "老数据", "status": "ok", "view": 999,
                "raw_input": "BV1xxx", "input_kind": "bv", "fetched_at": "2026-08-21 13:00:00",
            }
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)
        c = Cache(self.path)
        # 旧单 key 索引，加载后自动升级为双索引
        self.assertEqual(c.unique_count(), 1)
        got = c.get(VideoInfo(input_kind="bv", bvid="BV1xxx"))
        self.assertEqual(got.view, 999)
        got2 = c.get(VideoInfo(input_kind="av", aid=170001))
        self.assertEqual(got2.view, 999)


class TestOpusSupport(unittest.TestCase):
    """v2.8.1+：opus 新版专栏必须走新 API 端点（/x/polymer/web-dynamic/v1/opus/detail），
    不能用老端点 /x/article/view（否则返回 -404 / -352）。"""

    def test_article_info_is_opus_field(self):
        """ArticleInfo 增加 is_opus 字段，默认 False。"""
        a = make_article(cv_id="cv1")
        self.assertFalse(a.is_opus)
        a_opus = make_article(cv_id="988046566348554242", is_opus=True)
        self.assertTrue(a_opus.is_opus)
        # 序列化包含 is_opus
        d = a_opus.to_dict()
        self.assertTrue(d["is_opus"])

    def test_article_info_opus_display_title(self):
        """display_title 根据 is_opus 显示 opus/cv 前缀。"""
        # title="" 强制走 fallback（fallback 才有 opus/cv 前缀）
        a_cv = make_article(cv_id="cv1", title="")
        self.assertIn("cv1", a_cv.display_title)
        self.assertIn("cv", a_cv.display_title)
        a_opus = make_article(cv_id="988046566348554242", is_opus=True, title="")
        self.assertIn("opus", a_opus.display_title)
        self.assertIn("988046566348554242", a_opus.display_title)

    def test_explain_code_minus_352(self):
        """v2.8.1+：-352 状态码有友好提示（风控校验失败）。"""
        msg = explain_code(-352)
        # 不应该是 "未知错误码"
        self.assertNotIn("未知", msg)
        self.assertIn("风控", msg)

    def test_explain_code_minus_404_generic(self):
        """-404 文案应该是"资源不存在"，不再说"视频不存在"（专栏/番剧也用 -404）。"""
        msg = explain_code(-404)
        # 关键：不再用旧的"视频不存在"文案（专栏/番剧也用 -404）
        self.assertNotIn("视频不存在", msg)
        # 新的"资源不存在"文案应该出现
        self.assertIn("资源不存在", msg)

    def test_explain_code_minus_509(self):
        """-509 限流仍然有友好提示。"""
        msg = explain_code(-509)
        self.assertIn("频繁", msg)
        self.assertIn("限流", msg)

    def test_parsed_item_is_opus_default_false(self):
        from bilibili_tool.parser import ParsedItem
        p = ParsedItem(kind="article", value="12345", raw="12345")
        self.assertFalse(p.is_opus)
        p_opus = ParsedItem(kind="article", value="12345", raw="12345", is_opus=True)
        self.assertTrue(p_opus.is_opus)

    def test_parser_marks_opus_url(self):
        """opus URL 必须标记 is_opus=True。"""
        from bilibili_tool.parser import parse_text
        items = parse_text("https://www.bilibili.com/opus/988046566348554242")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")
        self.assertTrue(items[0].is_opus)

    def test_parser_marks_cv_url_not_opus(self):
        """cv URL 标记 is_opus=False。"""
        from bilibili_tool.parser import parse_text
        items = parse_text("https://www.bilibili.com/read/cv12345")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")
        self.assertFalse(items[0].is_opus)

    def test_expand_short_url_preserves_opus_flag(self):
        """b23 短链展开后，is_opus 标志从 opus 路径传递。"""
        from bilibili_tool.parser import parse_text, expand_short_urls
        # b23.tv/0qnXLMe 实际跳转到 opus 路径
        items = parse_text("https://b23.tv/0qnXLMe")
        expanded = expand_short_urls(items)
        # 展开后 is_opus 应为 True
        if expanded:
            self.assertTrue(expanded[0].is_opus)

    def test_fetcher_skeleton_opus_flag_passthrough(self):
        """BilibiliArticleFetcher._build_skeleton 透传 is_opus 标志。"""
        from bilibili_tool.fetcher import BilibiliArticleFetcher
        from bilibili_tool.parser import ParsedItem
        fetcher = BilibiliArticleFetcher()
        # 用 ParsedItem(is_opus=True) 构造
        p = ParsedItem(kind="article", value="988046566348554242", raw="x", is_opus=True)
        sk = fetcher._build_skeleton(p)
        self.assertTrue(sk.is_opus)
        self.assertEqual(sk.cv_id, "988046566348554242")

    def test_fetcher_skeleton_string_default_not_opus(self):
        """字符串输入默认 is_opus=False（旧 API 兼容）。"""
        from bilibili_tool.fetcher import BilibiliArticleFetcher
        fetcher = BilibiliArticleFetcher()
        sk = fetcher._build_skeleton("12345")
        self.assertFalse(sk.is_opus)

    def test_fetcher_has_fallback_html_method(self):
        """v2.8.1+：_fallback_opus_html 方法存在（opus API 失败时降级）。"""
        from bilibili_tool.fetcher import BilibiliArticleFetcher
        fetcher = BilibiliArticleFetcher()
        self.assertTrue(hasattr(fetcher, "_fallback_opus_html"))
        self.assertTrue(callable(fetcher._fallback_opus_html))

    def test_article_info_is_only_fans_field(self):
        """v2.8.1+：ArticleInfo 增加 is_only_fans 字段，默认 False。"""
        a = make_article(cv_id="cv1")
        self.assertFalse(a.is_only_fans)
        d = a.to_dict()
        self.assertIn("is_only_fans", d)
        self.assertFalse(d["is_only_fans"])

    def test_article_info_is_only_fans_setter(self):
        """is_only_fans 字段可以被设置。"""
        a = make_article(cv_id="cv1", is_only_fans=True)
        self.assertTrue(a.is_only_fans)
        d = a.to_dict()
        self.assertTrue(d["is_only_fans"])

    def test_article_fetcher_hydrate_opus_recognizes_only_fans(self):
        """_hydrate_opus 识别 basic.is_only_fans 字段。"""
        from bilibili_tool.fetcher import BilibiliArticleFetcher
        from bilibili_tool.models import ArticleInfo
        fetcher = BilibiliArticleFetcher()
        a = ArticleInfo(input_kind="article", cv_id="12345", is_opus=True)
        # 模拟 opus 响应：basic.is_only_fans = True
        item = {
            "id_str": "12345",
            "type": 1,
            "basic": {
                "title": "测试仅粉丝可见",
                "uid": "100",
                "is_only_fans": True,  # 关键
            },
            "modules": [],
        }
        fetcher._hydrate_opus(a, item)
        self.assertTrue(a.is_only_fans)
        self.assertEqual(a.title, "测试仅粉丝可见")
        # error 字段应该标记"仅粉丝可见"
        self.assertIn("仅粉丝可见", a.error)

    def test_article_fetcher_hydrate_opus_default_no_only_fans(self):
        """_hydrate_opus 默认 is_only_fans=False。"""
        from bilibili_tool.fetcher import BilibiliArticleFetcher
        from bilibili_tool.models import ArticleInfo
        fetcher = BilibiliArticleFetcher()
        a = ArticleInfo(input_kind="article", cv_id="12345", is_opus=True)
        item = {
            "id_str": "12345",
            "basic": {
                "title": "公开专栏",
                "uid": "100",
                # 缺 is_only_fans 字段
            },
            "modules": [],
        }
        fetcher._hydrate_opus(a, item)
        self.assertFalse(a.is_only_fans)
        self.assertEqual(a.title, "公开专栏")
        # 默认无 error
        self.assertNotIn("仅粉丝可见", a.error)


if __name__ == "__main__":
    unittest.main()

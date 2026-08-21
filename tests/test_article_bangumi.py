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
from bilibili_tool.models import ArticleInfo, BangumiInfo, VideoInfo


def make_article(*, cv_id="cv123", status="ok", view=1000, fetched_at=None, **kw) -> ArticleInfo:
    if fetched_at is None:
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return ArticleInfo(
        input_kind="article", cv_id=cv_id, title=f"article-{cv_id}",
        author_name=f"author-{cv_id}", status=status, view=view,
        fetched_at=fetched_at, **kw,
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


if __name__ == "__main__":
    unittest.main()

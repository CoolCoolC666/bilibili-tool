"""Cache 单元测试：新鲜度逻辑、字段差异化过期。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from bilibili_tool.cache import Cache, parse_duration
from bilibili_tool.models import VideoInfo


def make_info(
    *,
    bvid: str = "BV1abc",
    status: str = "ok",
    fetched_at=None,
    view: int = 1000,
) -> VideoInfo:
    """构造一条 VideoInfo。fetched_at=None 时用"现在"，空字符串 "" 时保持空。"""
    if fetched_at is None:
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return VideoInfo(
        input_kind="bv",
        bvid=bvid,
        status=status,
        title=f"title-{bvid}",
        up_name=f"up-{bvid}",
        view=view,
        like=view // 10,
        fetched_at=fetched_at,
    )


class TestParseDuration(unittest.TestCase):
    def test_hours(self):
        self.assertEqual(parse_duration("1h"), 3600)
        self.assertEqual(parse_duration("24h"), 86400)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_minutes(self):
        self.assertEqual(parse_duration("30m"), 1800)
        self.assertEqual(parse_duration("5m"), 300)

    def test_days(self):
        self.assertEqual(parse_duration("1d"), 86400)
        self.assertEqual(parse_duration("7d"), 604800)

    def test_seconds(self):
        self.assertEqual(parse_duration("30s"), 30)

    def test_zero(self):
        self.assertEqual(parse_duration("0"), 0)
        self.assertEqual(parse_duration("no"), 0)

    def test_never(self):
        self.assertIsNone(parse_duration("never"))
        self.assertIsNone(parse_duration("always"))
        self.assertIsNone(parse_duration(""))
        self.assertIsNone(parse_duration(None))

    def test_bare_number(self):
        # 纯数字按小时
        self.assertEqual(parse_duration("2"), 7200)


class TestCacheFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_no_cache_returns_none(self):
        c = Cache(self.path)
        self.assertIsNone(c.get_fresh(make_info(), max_age_seconds=3600))

    def test_max_age_zero_always_misses(self):
        c = Cache(self.path)
        c.put(make_info())
        # 即使有 cache，max_age=0 强制不命中
        self.assertIsNone(c.get_fresh(make_info(), max_age_seconds=0))

    def test_max_age_none_always_hits(self):
        c = Cache(self.path)
        c.put(make_info())
        # max_age=None 永远命中
        cached = c.get_fresh(make_info(), max_age_seconds=None)
        self.assertIsNotNone(cached)

    def test_fresh_within_window(self):
        c = Cache(self.path)
        # 刚刚抓的（1 秒前），max_age 1h 必然新鲜
        recent = make_info(
            fetched_at=(datetime.now() - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        )
        c.put(recent)
        cached = c.get_fresh(make_info(), max_age_seconds=3600)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.view, recent.view)

    def test_stale_outside_window(self):
        c = Cache(self.path)
        # 2 小时前抓的，max_age 1h 应该过期
        old = make_info(
            fetched_at=(datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        )
        c.put(old)
        self.assertIsNone(c.get_fresh(make_info(), max_age_seconds=3600))
        # 但 max_age 3h 仍然新鲜
        cached = c.get_fresh(make_info(), max_age_seconds=3 * 3600)
        self.assertIsNotNone(cached)

    def test_exact_boundary(self):
        """正好 max_age 秒的时刻：算过期（严格大于）。"""
        c = Cache(self.path)
        boundary = make_info(
            fetched_at=(datetime.now() - timedelta(seconds=3600)).strftime("%Y-%m-%d %H:%M:%S")
        )
        c.put(boundary)
        # 3600 秒前、max_age 3600：过期
        self.assertIsNone(c.get_fresh(make_info(), max_age_seconds=3600))

    def test_failed_status_always_fresh(self):
        """失败/失效状态（status != "ok"）永远算新鲜，不受 max_age 限制。"""
        c = Cache(self.path)
        # 10 年前"抓的"失败记录
        very_old_failed = make_info(
            status="not_found",
            fetched_at=(datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(very_old_failed)
        # 即使 max_age=0（强制不命中），失败状态也算新鲜
        cached = c.get_fresh(make_info(status="not_found"), max_age_seconds=0)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.status, "not_found")

    def test_missing_fetched_at_treated_stale(self):
        """没有 fetched_at 字段的 cache 视为过期。"""
        c = Cache(self.path)
        no_time = make_info(fetched_at="")
        c.put(no_time)
        self.assertIsNone(c.get_fresh(make_info(), max_age_seconds=3600))

    def test_different_bv_different_cache(self):
        """不同 BV 各自有 cache，不会串。"""
        c = Cache(self.path)
        c.put(make_info(bvid="BV1aaa", view=100))
        c.put(make_info(bvid="BV1bbb", view=200))
        self.assertEqual(c.get(make_info(bvid="BV1aaa")).view, 100)
        self.assertEqual(c.get(make_info(bvid="BV1bbb")).view, 200)


class TestCachePersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_atomic_write(self):
        c = Cache(self.path)
        c.put(make_info(bvid="BV1aaa"))
        c.put(make_info(bvid="BV1bbb"))
        c.save()

        # 重新加载
        c2 = Cache(self.path)
        self.assertEqual(len(c2.all_records()), 2)

    def test_corrupt_cache_recovered(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("not a json{{{")

        # 应该当作空 cache，不抛
        c = Cache(self.path)
        self.assertEqual(len(c.all_records()), 0)


class TestCacheDualIndex(unittest.TestCase):
    """核心场景：同一条记录同时有 BV 和 AV，应该按两边都索引。
    这样用户输入 'BV1xxx 170001' 第一次跑就只发 1 个请求。
    """

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_dual_index_look_up(self):
        """存一条同时有 bvid 和 aid 的记录，用任何一种 ID 都能查到。"""
        c = Cache(self.path)
        record = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            title="测试视频",
            up_name="up",
            status="ok",
            view=1000,
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(record)

        # 用 BV 查
        bv_query = VideoInfo(input_kind="bv", bvid="BV1xxx")
        self.assertIsNotNone(c.get(bv_query))
        self.assertEqual(c.get(bv_query).aid, 170001)

        # 用 AV 查
        av_query = VideoInfo(input_kind="av", aid=170001)
        self.assertIsNotNone(c.get(av_query))
        self.assertEqual(c.get(av_query).bvid, "BV1xxx")

    def test_dual_index_preserves_both(self):
        """put 时同时按两个 key 写。"""
        c = Cache(self.path)
        record = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            status="ok",
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(record)

        # 内部应该有两个 key
        self.assertIn("bv:BV1xxx", c._data)
        self.assertIn("av:170001", c._data)
        # 但都是同一份 dict
        self.assertIs(c._data["bv:BV1xxx"], c._data["av:170001"])

    def test_all_records_dedup(self):
        """all_records 不会因为双索引返回重复。"""
        c = Cache(self.path)
        record = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            status="ok",
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(record)

        # 实际只有 1 条视频
        self.assertEqual(c.unique_count(), 1)
        self.assertEqual(len(c.all_records()), 1)

    def test_stats_dedup(self):
        """stats 不应该把同一条记录算两遍。"""
        c = Cache(self.path)
        record = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            status="ok",
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(record)

        stats = c.stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["ok"], 1)
        self.assertEqual(stats["failed"], 0)

    def test_fresh_works_for_both_keys(self):
        """用 AV 查询时也能判断新鲜度（不只是用 BV 查的那次）。"""
        c = Cache(self.path)
        # 1 小时前抓的
        old = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            status="ok",
            fetched_at=(datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        c.put(old)

        # 用 BV 查：max-age 1h 应该过期
        bv_query = VideoInfo(input_kind="bv", bvid="BV1xxx")
        self.assertIsNone(c.get_fresh(bv_query, max_age_seconds=3600))

        # 用 AV 查：同样应该过期（因为是同一条记录）
        av_query = VideoInfo(input_kind="av", aid=170001)
        self.assertIsNone(c.get_fresh(av_query, max_age_seconds=3600))

    def test_failed_status_still_dual_indexed(self):
        """失败记录也按双索引。"""
        c = Cache(self.path)
        record = VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            status="not_found",
            api_code=62002,
            error="稿件不可见",
        )
        c.put(record)

        # 用任何方式查都拿得到
        self.assertIsNotNone(c.get(VideoInfo(input_kind="bv", bvid="BV1xxx")))
        self.assertIsNotNone(c.get(VideoInfo(input_kind="av", aid=170001)))

    def test_persistence_dual_index(self):
        """存盘后再加载，双索引仍然有效。"""
        c1 = Cache(self.path)
        c1.put(VideoInfo(
            input_kind="bv",
            bvid="BV1xxx",
            aid=170001,
            title="持久化测试",
            status="ok",
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        c1.save()

        c2 = Cache(self.path)
        # 两个 key 都能查到
        self.assertIsNotNone(c2.get(VideoInfo(input_kind="bv", bvid="BV1xxx")))
        self.assertIsNotNone(c2.get(VideoInfo(input_kind="av", aid=170001)))
        # 实际只 1 条
        self.assertEqual(c2.unique_count(), 1)

    def test_upgrade_single_index_to_dual(self):
        """旧 cache.json 是单 key 索引，加载时自动升级为双索引。"""
        # 模拟旧 cache：只写了 bv:BV1xxx，但 record 里有 aid=170001
        import json as _json
        old_cache = {
            "bv:BV1xxx": {
                "bvid": "BV1xxx",
                "aid": 170001,
                "title": "旧数据",
                "status": "ok",
                "view": 999,
            }
        }
        with open(self.path, "w", encoding="utf-8") as f:
            _json.dump(old_cache, f)

        c = Cache(self.path)
        # 升级后用 AV 查也能查到
        result = c.get(VideoInfo(input_kind="av", aid=170001))
        self.assertIsNotNone(result)
        self.assertEqual(result.bvid, "BV1xxx")
        self.assertEqual(result.view, 999)
        # 实际只有 1 条
        self.assertEqual(c.unique_count(), 1)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()

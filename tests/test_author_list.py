"""v2.9.0+ 阶段 1 测试：UP 主视频列表 → CSV 导出。

Mock 掉 _fetch_page_seek_arc / _fetch_page_arc_search，避免真实网络请求。
"""
import csv
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from bilibili_tool.author import AuthorVideoFetcher, TZ_BJ
from bilibili_tool.author_list import AuthorListExporter


def _now_ts() -> int:
    return int(datetime.now(TZ_BJ).timestamp())


def _make_archive(bvid, aid, days_ago, title=None, duration=130, tid=0):
    """模拟 B 站 archive 字典。"""
    return {
        "bvid": bvid,
        "aid": aid,
        "title": title or f"测试视频 {bvid}",
        "duration": duration,
        "pubdate": _now_ts() - days_ago * 86400,
        "tid": tid,
    }


class TestAuthorListExport(unittest.TestCase):

    def setUp(self):
        # 每个测试用独立的临时目录
        self.tmpdir = tempfile.mkdtemp(prefix="bilibili_author_list_")
        self.exporter = AuthorListExporter(output_dir=self.tmpdir)

    def tearDown(self):
        # 清理临时目录
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_basic_csv(self, mock_seek, mock_old):
        """3 条 archive → CSV 有 3 条数据行 + 1 条表头"""
        mock_seek.return_value = [
            _make_archive("BV1aaa", 1001, 1, title="招行视频1", duration=130),
            _make_archive("BV1bbb", 1002, 2, title="招行视频2", duration=200),
            _make_archive("BV1ccc", 1003, 3, title="招行视频3", duration=60),
        ]
        mock_old.return_value = None

        path, count = self.exporter.export(uid=473965081, days=7)

        self.assertEqual(count, 3)
        self.assertTrue(os.path.exists(path))
        self.assertIn("author_473965081_", os.path.basename(path))
        self.assertTrue(path.endswith(".csv"))

        # 读 CSV 验证
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
        self.assertEqual(len(rows), 4)  # 表头 + 3 条
        self.assertEqual(rows[0], ["bvid", "aid", "title", "duration", "pubdate", "tid", "up_uid"])
        self.assertEqual(rows[1][0], "BV1aaa")
        self.assertEqual(rows[1][1], "1001")
        self.assertEqual(rows[1][2], "招行视频1")
        self.assertEqual(rows[1][3], "130")
        self.assertEqual(rows[1][5], "0")
        self.assertEqual(rows[1][6], "473965081")

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_no_results(self, mock_seek, mock_old):
        """UP 主没投稿 → CSV 只有表头"""
        mock_seek.return_value = []
        mock_old.return_value = None

        path, count = self.exporter.export(uid=123456, days=7)
        self.assertEqual(count, 0)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 1)  # 只表头

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_uses_raw_dict_fields(self, mock_seek, mock_old):
        """验证 CSV 字段是 archive 字典里的真实字段（不是 ParsedItem）"""
        mock_seek.return_value = [
            _make_archive("BV1xxx", 9999, 1, title="标题测试", duration=300, tid=122),
        ]
        mock_old.return_value = None

        path, _ = self.exporter.export(uid=53456, days=7)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[1], ["BV1xxx", "9999", "标题测试", "300",
                                   rows[1][4],  # pubdate 略过（依赖时间）
                                   "122", "53456"])
        # pubdate 应该是 YYYY-MM-DD HH:MM:SS 格式
        self.assertRegex(rows[1][4], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_with_since_until(self, mock_seek, mock_old):
        """显式 since/until 应覆盖 days 参数"""
        mock_seek.return_value = [
            _make_archive("BV1new", 1, 1),
            _make_archive("BV1mid", 2, 2),
        ]
        mock_old.return_value = None
        from datetime import datetime
        since_dt = datetime.now(TZ_BJ) - timedelta(days=2)
        since_dt = since_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        # days=30 但 since 限定到 2 天前
        path, count = self.exporter.export(uid=123, days=30, since=since_dt)
        self.assertEqual(count, 2)  # 2 条都还在 since 范围内

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_max_count_truncates(self, mock_seek, mock_old):
        """max_count 限制条数"""
        mock_seek.return_value = [
            _make_archive(f"BV{i:04d}", i, i + 1) for i in range(1, 11)
        ]
        mock_old.return_value = None
        path, count = self.exporter.export(uid=999, days=30, max_count=3)
        self.assertEqual(count, 3)

    @patch.object(AuthorVideoFetcher, "_fetch_page_arc_search")
    @patch.object(AuthorVideoFetcher, "_fetch_page_seek_arc")
    def test_export_fallback_uses_arc_search(self, mock_seek, mock_old):
        """新端点返回 None → 降级到旧端点"""
        mock_seek.return_value = None
        mock_old.return_value = [
            _make_archive("BV1fall", 2001, 1, title="降级到旧端点"),
        ]
        path, count = self.exporter.export(uid=123, days=7)
        self.assertEqual(count, 1)
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[1][2], "降级到旧端点")

    def test_export_invalid_uid_raises(self):
        with self.assertRaises(ValueError):
            self.exporter.export(uid=0)
        with self.assertRaises(ValueError):
            self.exporter.export(uid=-1)
        with self.assertRaises(ValueError):
            self.exporter.export(uid="abc")  # type: ignore

    def test_filename_format(self):
        """文件名格式：author_<uid>_<时间戳>.csv"""
        import re
        # 任意 path，验证文件名格式
        import os.path
        from unittest.mock import patch as _p
        with _p.object(AuthorVideoFetcher, "_fetch_page_arc_search", return_value=None), \
             _p.object(AuthorVideoFetcher, "_fetch_page_seek_arc", return_value=[]):
            path, _ = self.exporter.export(uid=123456789, days=7)
        name = os.path.basename(path)
        self.assertRegex(name, r"^author_123456789_\d{8}_\d{6}\.csv$")


class TestAuthorListExportFormat(unittest.TestCase):
    """CSV 格式细节：UTF-8 BOM + Excel 兼容性"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bilibili_author_list_fmt_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_csv_has_bom(self):
        """UTF-8 BOM 头：让 Excel 打开不乱码"""
        from unittest.mock import patch as _p
        with _p.object(AuthorVideoFetcher, "_fetch_page_arc_search", return_value=None), \
             _p.object(AuthorVideoFetcher, "_fetch_page_seek_arc",
                       return_value=[_make_archive("BV1zz", 99, 1, title="中文标题测试")]):
            exporter = AuthorListExporter(output_dir=self.tmpdir)
            path, _ = exporter.export(uid=123, days=7)

        with open(path, "rb") as f:
            raw = f.read(3)
        self.assertEqual(raw, b"\xef\xbb\xbf", "CSV 应该以 UTF-8 BOM 开头（Excel 兼容）")

    def test_v3_export_from_preloaded_archives(self):
        """v3.0+：直接传 archives（跟 chain 配合），跳过 fetcher。"""
        archives = [
            _make_archive("BV1chain1", 100, 1, title="chain 视频 1"),
            _make_archive("BV1chain2", 101, 2, title="chain 视频 2"),
        ]
        exporter = AuthorListExporter(output_dir=self.tmpdir)
        path, count = exporter.export(uid=999, archives=archives)
        self.assertEqual(count, 2)
        # 不应调 fetcher
        # 注：fetcher 存在但不会被调用（因为 archives 已传）
        import csv
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["bvid", "aid", "title", "duration", "pubdate", "tid", "up_uid"])
        self.assertEqual(len(rows), 3)  # 1 header + 2 data
        self.assertEqual(rows[1][0], "BV1chain1")
        self.assertEqual(rows[1][6], "999")  # up_uid

    def test_v3_export_archives_with_uapis_source(self):
        """v3.0+：uapis.cn 拉的 archives（含 _source 字段）也能正常写。"""
        archives = [
            {
                "aid": 12345, "bvid": "BV1uapis",
                "title": "uapis 视频", "duration": 600, "play": 100,
                "pubdate": 1758000000, "_source": "uapis.cn",
            }
        ]
        exporter = AuthorListExporter(output_dir=self.tmpdir)
        path, count = exporter.export(uid=483307278, archives=archives)
        self.assertEqual(count, 1)
        import csv
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[1][0], "BV1uapis")
        # up_uid 是 uid（不是 _source）
        self.assertEqual(rows[1][6], "483307278")


if __name__ == "__main__":
    unittest.main()


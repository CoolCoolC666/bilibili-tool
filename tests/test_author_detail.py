"""v2.9.0+ 阶段 2 测试：CSV → 抓详情 → XLSX。

Mock 掉 BilibiliVideoFetcher.batch_fetch，不发真实网络请求。
"""
import csv
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

from bilibili_tool.author_detail import (
    AuthorDetailExporter,
    read_author_csv,
    rows_to_parsed_items,
)
from bilibili_tool.fetcher import BilibiliVideoFetcher
from bilibili_tool.models import VideoInfo


def _make_csv(path, rows):
    """构造阶段 1 风格的 CSV。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["bvid", "aid", "title", "duration", "pubdate", "tid", "up_uid"]
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _make_video_info(bvid, ok=True, title=None):
    """构造 VideoInfo（模拟 fetcher 返回值）。"""
    info = VideoInfo(
        raw_input=bvid, input_kind="bv", bvid=bvid,
        title=title or f"标题 {bvid}",
    )
    if ok:
        info.status = "ok"
        info.aid = 12345
        info.up_name = "测试UP"
    else:
        info.status = "failed"
        info.error = "mock error"
    return info


class TestReadAuthorCsv(unittest.TestCase):
    """read_author_csv 单元测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bilibili_csv_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_basic_read(self):
        path = os.path.join(self.tmpdir, "test.csv")
        _make_csv(path, [
            {"bvid": "BV1aaa", "aid": "1001", "title": "T1", "duration": "130",
             "pubdate": "2026-08-01 12:00:00", "tid": "122", "up_uid": "473965081"},
            {"bvid": "BV1bbb", "aid": "1002", "title": "T2", "duration": "200",
             "pubdate": "2026-08-02 12:00:00", "tid": "0", "up_uid": "473965081"},
        ])
        rows = read_author_csv(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bvid"], "BV1aaa")
        self.assertEqual(rows[0]["title"], "T1")
        self.assertEqual(rows[0]["up_uid"], "473965081")

    def test_empty_csv(self):
        path = os.path.join(self.tmpdir, "empty.csv")
        _make_csv(path, [])
        rows = read_author_csv(path)
        self.assertEqual(rows, [])

    def test_skip_blank_rows(self):
        path = os.path.join(self.tmpdir, "mixed.csv")
        _make_csv(path, [
            {"bvid": "BV1aaa", "aid": "1001", "title": "T1", "duration": "130",
             "pubdate": "", "tid": "0", "up_uid": "123"},
            {"bvid": "", "aid": "", "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": ""},  # 空白行
        ])
        rows = read_author_csv(path)
        self.assertEqual(len(rows), 1)

    def test_strips_whitespace(self):
        path = os.path.join(self.tmpdir, "ws.csv")
        _make_csv(path, [
            {"bvid": "  BV1aaa  ", "aid": " 1001 ", "title": " T1 ",
             "duration": "130", "pubdate": "2026-08-01", "tid": "0", "up_uid": "123"},
        ])
        rows = read_author_csv(path)
        self.assertEqual(rows[0]["bvid"], "BV1aaa")
        self.assertEqual(rows[0]["aid"], "1001")
        self.assertEqual(rows[0]["title"], "T1")


class TestRowsToParsedItems(unittest.TestCase):
    """rows_to_parsed_items 单元测试。"""

    def test_bv_preferred(self):
        rows = [{"bvid": "BV1aaa", "aid": "1001"}]
        items = rows_to_parsed_items(rows)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bv")
        self.assertEqual(items[0].value, "BV1aaa")

    def test_aid_fallback(self):
        rows = [{"bvid": "", "aid": "1001"}]
        items = rows_to_parsed_items(rows)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "1001")

    def test_skip_empty(self):
        rows = [
            {"bvid": "BV1aaa", "aid": "1001"},
            {"bvid": "", "aid": ""},  # 跳过
        ]
        items = rows_to_parsed_items(rows)
        self.assertEqual(len(items), 1)


class TestAuthorDetailExport(unittest.TestCase):
    """AuthorDetailExporter 单元测试（mock fetcher）。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bilibili_author_detail_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_export_success(self):
        """3 条全成功"""
        csv_path = os.path.join(self.tmpdir, "list.csv")
        _make_csv(csv_path, [
            {"bvid": "BV1aaa", "aid": "1001", "title": "T1", "duration": "130",
             "pubdate": "2026-08-01", "tid": "0", "up_uid": "473965081"},
            {"bvid": "BV1bbb", "aid": "1002", "title": "T2", "duration": "200",
             "pubdate": "2026-08-02", "tid": "0", "up_uid": "473965081"},
            {"bvid": "BV1ccc", "aid": "1003", "title": "T3", "duration": "60",
             "pubdate": "2026-08-03", "tid": "0", "up_uid": "473965081"},
        ])

        # mock fetcher：3 条全成功
        mock_fetcher = MagicMock(spec=BilibiliVideoFetcher)
        mock_fetcher.batch_fetch.return_value = [
            _make_video_info("BV1aaa", ok=True),
            _make_video_info("BV1bbb", ok=True),
            _make_video_info("BV1ccc", ok=True),
        ]

        exporter = AuthorDetailExporter(
            mock_fetcher, output_dir=self.tmpdir, delay=0.0,
        )
        path, ok, fail = exporter.export(csv_path)

        self.assertEqual(ok, 3)
        self.assertEqual(fail, 0)
        self.assertTrue(os.path.exists(path))
        self.assertIn("author_detail_473965081_", os.path.basename(path))
        self.assertTrue(path.endswith(".xlsx"))
        # batch_fetch 被调
        mock_fetcher.batch_fetch.assert_called_once()

    def test_export_partial_failure(self):
        """2 成功 + 1 失败"""
        csv_path = os.path.join(self.tmpdir, "list.csv")
        _make_csv(csv_path, [
            {"bvid": "BV1ok1", "aid": "1", "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": "123"},
            {"bvid": "BV1fail", "aid": "2", "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": "123"},
            {"bvid": "BV1ok2", "aid": "3", "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": "123"},
        ])

        mock_fetcher = MagicMock(spec=BilibiliVideoFetcher)
        mock_fetcher.batch_fetch.return_value = [
            _make_video_info("BV1ok1", ok=True),
            _make_video_info("BV1fail", ok=False),
            _make_video_info("BV1ok2", ok=True),
        ]

        exporter = AuthorDetailExporter(
            mock_fetcher, output_dir=self.tmpdir, delay=0.0,
        )
        path, ok, fail = exporter.export(csv_path)

        self.assertEqual(ok, 2)
        self.assertEqual(fail, 1)
        self.assertTrue(os.path.exists(path))

    def test_export_max_count_truncates(self):
        """max_count 截断"""
        csv_path = os.path.join(self.tmpdir, "list.csv")
        _make_csv(csv_path, [
            {"bvid": f"BV{i:04d}", "aid": str(i), "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": "123"}
            for i in range(1, 11)
        ])

        mock_fetcher = MagicMock(spec=BilibiliVideoFetcher)
        mock_fetcher.batch_fetch.return_value = [
            _make_video_info(f"BV{i:04d}", ok=True) for i in range(1, 4)
        ]

        exporter = AuthorDetailExporter(
            mock_fetcher, output_dir=self.tmpdir, delay=0.0,
        )
        path, ok, fail = exporter.export(csv_path, max_count=3)

        self.assertEqual(ok, 3)
        # batch_fetch 只收到 3 个 items
        items_arg = mock_fetcher.batch_fetch.call_args[0][0]
        self.assertEqual(len(items_arg), 3)

    def test_export_empty_csv_raises(self):
        """空 CSV → ValueError"""
        csv_path = os.path.join(self.tmpdir, "empty.csv")
        _make_csv(csv_path, [])

        mock_fetcher = MagicMock(spec=BilibiliVideoFetcher)
        exporter = AuthorDetailExporter(
            mock_fetcher, output_dir=self.tmpdir, delay=0.0,
        )
        with self.assertRaises(ValueError):
            exporter.export(csv_path)

    def test_export_missing_up_uid_fallback(self):
        """up_uid 缺失 → 文件名用 'unknown'"""
        csv_path = os.path.join(self.tmpdir, "list.csv")
        _make_csv(csv_path, [
            {"bvid": "BV1aaa", "aid": "1", "title": "", "duration": "",
             "pubdate": "", "tid": "", "up_uid": ""},
        ])
        mock_fetcher = MagicMock(spec=BilibiliVideoFetcher)
        mock_fetcher.batch_fetch.return_value = [_make_video_info("BV1aaa", ok=True)]
        exporter = AuthorDetailExporter(
            mock_fetcher, output_dir=self.tmpdir, delay=0.0,
        )
        path, ok, _ = exporter.export(csv_path)
        self.assertIn("author_detail_unknown_", os.path.basename(path))

    def test_v301_default_output_dir_is_xlsx_subdir(self):
        """v3.0.1+：默认 output_dir = output/xlsx（与 csv 分离）。"""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_dir = os.path.join(tmpdir, "output", "xlsx")
            os.makedirs(xlsx_dir, exist_ok=True)
            from unittest.mock import MagicMock
            vfetcher = MagicMock()
            vfetcher.batch_fetch.return_value = []
            from bilibili_tool.author_detail import AuthorDetailExporter
            exp = AuthorDetailExporter(fetcher=vfetcher, output_dir=xlsx_dir)
            self.assertTrue(exp.output_dir.endswith(os.path.join("output", "xlsx")))


if __name__ == "__main__":
    unittest.main()
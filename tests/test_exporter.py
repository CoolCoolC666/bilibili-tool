"""Exporter 单元测试：去重逻辑 + 4 种格式。"""
import csv
import json
import os
import tempfile
import unittest
from datetime import datetime

from bilibili_tool.exporter import (
    dedupe_videos,
    save_xlsx,
    save_csv,
    save_json,
    save_txt,
    export_all,
    filter_valid,
    _dedupe_key,
)
from bilibili_tool.models import VideoInfo


def make(bvid="", aid=None, title="t", status="ok", raw="", **kw):
    return VideoInfo(
        raw_input=raw or (bvid or str(aid or "x")),
        input_kind="bv" if bvid else "av",
        bvid=bvid,
        aid=aid,
        title=title,
        status=status,
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **kw,
    )


class TestDedupeKey(unittest.TestCase):
    def test_bv_key(self):
        self.assertEqual(_dedupe_key(make(bvid="BV1xxx")), ("bv", "BV1xxx"))

    def test_av_key(self):
        self.assertEqual(_dedupe_key(make(aid=170001, bvid="")), ("av", 170001))

    def test_bv_wins_over_av(self):
        # 都有的话用 BV（更稳定）
        v = make(bvid="BV1xxx", aid=170001)
        self.assertEqual(_dedupe_key(v), ("bv", "BV1xxx"))

    def test_raw_fallback(self):
        v = VideoInfo(raw_input="something", input_kind="raw")
        self.assertEqual(_dedupe_key(v), ("raw", "something"))

    def test_no_key(self):
        v = VideoInfo()
        self.assertIsNone(_dedupe_key(v))


class TestDedupeVideos(unittest.TestCase):
    def test_keeps_unique(self):
        v1 = make(bvid="BV1aaa")
        v2 = make(bvid="BV1bbb")
        out = dedupe_videos([v1, v2])
        self.assertEqual(len(out), 2)

    def test_merges_same_bv(self):
        v1 = make(bvid="BV1xxx", view=100)
        v2 = make(bvid="BV1xxx", view=200)  # 同一视频（理论上不会出现，但兜底）
        out = dedupe_videos([v1, v2])
        self.assertEqual(len(out), 1)
        # 保留第一次的
        self.assertEqual(out[0].view, 100)

    def test_bv_av_same_video(self):
        """用户输入 BV1xxx + av170001（同一视频），导出只 1 条。"""
        v_bv = make(bvid="BV1xxx", aid=170001, title="测试视频", raw="BV1xxx")
        v_av = make(bvid="BV1xxx", aid=170001, title="测试视频", raw="av170001")
        out = dedupe_videos([v_bv, v_av])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].bvid, "BV1xxx")
        self.assertEqual(out[0].aid, 170001)

    def test_preserves_input_order(self):
        v1 = make(bvid="BV1aaa", title="A")
        v2 = make(bvid="BV1bbb", title="B")
        v3 = make(bvid="BV1ccc", title="C")
        out = dedupe_videos([v1, v2, v3, v1])  # v1 重复一次
        self.assertEqual([v.title for v in out], ["A", "B", "C"])

    def test_no_key_videos_kept(self):
        v1 = VideoInfo()
        v2 = VideoInfo()
        out = dedupe_videos([v1, v2])
        self.assertEqual(len(out), 2)  # 没 key 的不参与去重

    def test_mixed_with_dupes(self):
        v1 = make(bvid="BV1a")
        v2 = make(bvid="BV1b")
        v3 = make(bvid="BV1a")  # dup of v1
        v4 = make(aid=999, bvid="")  # 没 bvid，用 av
        v5 = make(bvid="BV1c", aid=999)  # 有 bvid，bvid 不跟 v4 重复
        out = dedupe_videos([v1, v2, v3, v4, v5])
        # v1, v2, v4, v5（v3 dup v1）
        self.assertEqual(len(out), 4)


class TestExportFormats(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_csv(self):
        v1 = make(bvid="BV1a", title="视频A")
        v2 = make(bvid="BV1b", title="视频B")
        path = save_csv([v1, v2], os.path.join(self.tmpdir, "t.csv"))
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["BV号"], "BV1a")

    def test_save_json(self):
        v1 = make(bvid="BV1a", title="视频A")
        path = save_json([v1], os.path.join(self.tmpdir, "t.json"))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["bvid"], "BV1a")

    def test_save_txt(self):
        v1 = make(bvid="BV1a", title="视频A")
        v2 = make(bvid="BV1b", title="视频B", status="not_found", api_code=62002)
        path = save_txt([v1, v2], os.path.join(self.tmpdir, "t.txt"))
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("视频A", text)
        self.assertIn("not_found", text)
        self.assertIn("共 2 条记录", text)

    def test_save_xlsx(self):
        v1 = make(bvid="BV1a", title="视频A")
        v2 = make(bvid="BV1b", title="视频B")
        path = save_xlsx([v1, v2], os.path.join(self.tmpdir, "t.xlsx"))
        self.assertTrue(os.path.exists(path))
        # 读回来验证
        from openpyxl import load_workbook
        wb = load_workbook(path)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        # 第 1 行表头 + 2 行数据
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][6], "BV1a")  # BV号 列
        self.assertEqual(rows[2][6], "BV1b")

    def test_export_all_dedupes_by_default(self):
        # 两条同一视频（BV + AV）
        v1 = make(bvid="BV1xxx", aid=170001, title="测试", raw="BV1xxx")
        v2 = make(bvid="BV1xxx", aid=170001, title="测试", raw="av170001")
        saved = export_all([v1, v2], base="test", out_dir=self.tmpdir)
        # 4 个文件都生成了
        for fmt, path in saved.items():
            self.assertTrue(os.path.exists(path), f"{fmt} 文件不存在")
        # 验证：CSV 只有 1 行数据
        with open(saved["csv"], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1, f"应只有 1 条去重后的记录，实际 {len(rows)}")

    def test_export_all_no_dedupe(self):
        v1 = make(bvid="BV1xxx", aid=170001, title="测试", raw="BV1xxx")
        v2 = make(bvid="BV1xxx", aid=170001, title="测试", raw="av170001")
        saved = export_all([v1, v2], base="test", out_dir=self.tmpdir, dedupe=False)
        with open(saved["csv"], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2, f"不去重应保留 2 条，实际 {len(rows)}")

    def test_filter_valid(self):
        ok1 = make(bvid="BV1a", title="A")
        ok2 = make(bvid="BV1b", title="B")
        fail1 = make(bvid="BV1c", status="not_found", api_code=62002)
        fail2 = make(bvid="BV1d", status="failed", error="network")
        out = filter_valid([ok1, fail1, ok2, fail2])
        self.assertEqual(len(out), 2)
        self.assertEqual([v.bvid for v in out], ["BV1a", "BV1b"])

    def test_export_all_exclude_invalid(self):
        """--exclude-invalid 开启时，导出文件只含 status=ok 的记录。"""
        ok = make(bvid="BV1a", title="A")
        fail = make(bvid="BV1c", status="not_found", api_code=62002)
        saved = export_all(
            [ok, fail, fail],
            base="test",
            out_dir=self.tmpdir,
            exclude_invalid=True,
        )
        # CSV 应只有 1 行
        with open(saved["csv"], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1, f"应只 1 条 ok 记录，实际 {len(rows)}")
        self.assertEqual(rows[0]["BV号"], "BV1a")

    def test_export_all_exclude_invalid_false_keeps_failed(self):
        """--exclude-invalid 关闭时（默认），保留所有状态。"""
        ok = make(bvid="BV1a", title="A")
        fail = make(bvid="BV1c", status="not_found", api_code=62002)
        saved = export_all(
            [ok, fail],
            base="test",
            out_dir=self.tmpdir,
            exclude_invalid=False,
        )
        with open(saved["csv"], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)

    def test_export_all_filter_before_dedupe(self):
        """过滤应在去重之前：同一视频的 ok + failed 两种状态，先 filter 再 dedupe。"""
        ok = make(bvid="BV1x", title="OK")
        fail_same = make(bvid="BV1x", status="not_found", api_code=62002)
        # 开启 filter：fail 过滤掉，ok 保留；去重：1 条
        saved = export_all(
            [ok, fail_same],
            base="test",
            out_dir=self.tmpdir,
            exclude_invalid=True,
            dedupe=True,
        )
        with open(saved["csv"], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["状态"], "ok")


if __name__ == "__main__":
    unittest.main()

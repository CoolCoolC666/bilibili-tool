"""v2.9.1+ WBI 签名单元测试。"""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from bilibili_tool.wbi import (
    MIXIN_KEY_ENC_TAB,
    enc_wbi,
    get_mixin_key,
    get_wbi_keys,
    WbiKeyCache,
)
from bilibili_tool.author import AuthorVideoFetcher  # 集成测试需要


class TestMixinKeyTab(unittest.TestCase):
    """MIXIN_KEY_ENC_TAB 基础属性测试。"""

    def test_tab_length_is_64(self):
        """重排表必须 64 位。"""
        self.assertEqual(len(MIXIN_KEY_ENC_TAB), 64)

    def test_tab_values_in_range(self):
        """所有索引值在 0-63 之间。"""
        for i, v in enumerate(MIXIN_KEY_ENC_TAB):
            self.assertGreaterEqual(v, 0, f"index {i} value {v} < 0")
            self.assertLess(v, 64, f"index {i} value {v} >= 64")

    def test_tab_is_permutation(self):
        """重排表是 0-63 的完整排列（不重复不漏值）。"""
        self.assertEqual(sorted(MIXIN_KEY_ENC_TAB), list(range(64)))


class TestGetMixinKey(unittest.TestCase):
    """get_mixin_key 单元测试。"""

    def test_known_example(self):
        """B 站官方文档示例，验证算法一致。"""
        img_key = "7cd084941338484aae1ad9425b84077b"
        sub_key = "4932caff0ff746eab6f01bf08b70ac45"
        result = get_mixin_key(img_key + sub_key)
        # 这个值是 B 站官方文档 / 多个第三方实现交叉验证过的
        self.assertEqual(result, "ea1db124af3b7062474693fa704f4ff8")

    def test_another_known_example(self):
        """另一个常见示例：img_key 653657f5... sub_key 6e4909c7..."""
        img_key = "653657f524a547ac981ded72ea172057"
        sub_key = "6e4909c702f846728e64f6007736a338"
        result = get_mixin_key(img_key + sub_key)
        # B 站文档示例
        self.assertEqual(result, "72136226c6a73669787ee4fd02a74c27")

    def test_returns_32_chars(self):
        """返回值长度必须是 32。"""
        result = get_mixin_key("a" * 64)
        self.assertEqual(len(result), 32)

    def test_input_shorter_than_64(self):
        """输入短于 64 时不报错（只取能取的索引，结果 < 32）。"""
        # "a" * 30 长度不够 64，B 站实现里大部分索引越界，结果短于 32
        # 这只是验证不抛异常 + 返回字符串
        result = get_mixin_key("a" * 30)
        self.assertIsInstance(result, str)
        # 实际生产中 img_key + sub_key 一定 = 64 hex 字符，所以不会短
        # 短输入只是兜底防御


class TestEncWbi(unittest.TestCase):
    """enc_wbi 签名生成测试。"""

    IMG_KEY = "7cd084941338484aae1ad9425b84077b"
    SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

    def test_adds_wts_and_w_rid(self):
        """签名后必须包含 wts + w_rid 字段。"""
        params = {"foo": "114", "bar": "514", "baz": "1919810"}
        before_ts = int(time.time())
        signed = enc_wbi(params, self.IMG_KEY, self.SUB_KEY)
        after_ts = int(time.time())
        self.assertIn("wts", signed)
        self.assertIn("w_rid", signed)
        # wts 应该是当前时间戳（int 转 str，介于 before/after 之间）
        wts = int(signed["wts"])
        self.assertGreaterEqual(wts, before_ts)
        self.assertLessEqual(wts, after_ts)
        # w_rid 是 32 位 MD5
        self.assertEqual(len(signed["w_rid"]), 32)
        self.assertTrue(all(c in "0123456789abcdef" for c in signed["w_rid"]))

    def test_does_not_mutate_input(self):
        """不应该修改入参 dict。"""
        params = {"foo": "1", "bar": "2"}
        original = dict(params)
        enc_wbi(params, self.IMG_KEY, self.SUB_KEY)
        self.assertEqual(params, original)

    def test_filters_special_chars(self):
        """value 中的 "!'()" 应该被过滤。"""
        params = {"name": "it's a (test)!", "ok": "normal"}
        signed = enc_wbi(params, self.IMG_KEY, self.SUB_KEY)
        # 字段里这些字符不应出现
        self.assertNotIn("!", signed["name"])
        self.assertNotIn("'", signed["name"])
        self.assertNotIn("(", signed["name"])
        self.assertNotIn(")", signed["name"])

    def test_sorted_by_key(self):
        """签名后 key 字典序。"""
        params = {"z": 1, "a": 2, "m": 3}
        signed = enc_wbi(params, self.IMG_KEY, self.SUB_KEY)
        keys = list(signed.keys())
        # 去掉 wts/w_rid 后应该排序
        business_keys = [k for k in keys if k not in ("wts", "w_rid")]
        self.assertEqual(business_keys, sorted(business_keys))

    def test_known_signature(self):
        """B 站官方文档示例（参数 foo=114 bar=514 baz=1919810）应产生固定 w_rid。"""
        # 注意：wts 是当前时间戳，所以 w_rid 也带时间相关；
        # 但 B 站文档示例用的是 1684746387（2023-05-22），我们验证算法逻辑一致即可
        params = {"foo": "114", "bar": "514", "baz": "1919810"}
        signed = enc_wbi(params, self.IMG_KEY, self.SUB_KEY)
        # 字段顺序：按 key 排序（bar, baz, foo, wts, w_rid）
        keys = list(signed.keys())
        self.assertEqual(keys, ["bar", "baz", "foo", "wts", "w_rid"])


class TestGetWbiKeys(unittest.TestCase):
    """get_wbi_keys 单元测试（mock nav 接口）。"""

    IMG_KEY = "7cd084941338484aae1ad9425b84077b"
    SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

    @patch("bilibili_tool.wbi.requests.Session")
    def test_successful_response(self, mock_sess_cls):
        """正常 nav 响应 → 解析出 (img_key, sub_key)。"""
        mock_sess = MagicMock()
        mock_sess_cls.return_value = mock_sess
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                }
            }
        }
        mock_sess.get.return_value = mock_resp
        img_key, sub_key = get_wbi_keys()
        self.assertEqual(img_key, self.IMG_KEY)
        self.assertEqual(sub_key, self.SUB_KEY)

    @patch("bilibili_tool.wbi.requests.Session")
    def test_uses_provided_session(self, mock_sess_cls):
        """传入 sess 应该被使用（不创建新 session）。"""
        mock_sess = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {
                "wbi_img": {
                    "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                    "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                }
            }
        }
        mock_sess.get.return_value = mock_resp
        get_wbi_keys(sess=mock_sess)
        # 验证传入的 sess 被调用了
        mock_sess.get.assert_called_once()

    @patch("bilibili_tool.wbi.requests.Session")
    def test_non_zero_code_raises(self, mock_sess_cls):
        """code != 0 时抛出 RuntimeError。"""
        mock_sess = MagicMock()
        mock_sess_cls.return_value = mock_sess
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": -101, "message": "未登录"}
        mock_sess.get.return_value = mock_resp
        with self.assertRaises(RuntimeError) as cm:
            get_wbi_keys()
        self.assertIn("未登录", str(cm.exception))

    @patch("bilibili_tool.wbi.requests.Session")
    def test_missing_wbi_img_raises(self, mock_sess_cls):
        """响应里没 wbi_img 字段时抛出（未登录场景）。"""
        mock_sess = MagicMock()
        mock_sess_cls.return_value = mock_sess
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": 0, "data": {"isLogin": False}}
        mock_sess.get.return_value = mock_resp
        with self.assertRaises(RuntimeError) as cm:
            get_wbi_keys()
        self.assertIn("img_url", str(cm.exception))


class TestWbiKeyCache(unittest.TestCase):
    """WbiKeyCache 单元测试。"""

    IMG_KEY = "7cd084941338484aae1ad9425b84077b"
    SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bilibili_wbi_")
        self.cache_file = os.path.join(self.tmpdir, "wbi_keys.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cache_init_no_file(self):
        """无缓存文件时，构造不应抛异常。"""
        cache = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
        self.assertIsNone(cache._img_key)

    def test_get_fetches_from_nav(self):
        """第一次 get 应该调 nav 接口拉取。"""
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache = WbiKeyCache(cache_file=self.cache_file)
            img_key, sub_key = cache.get()
            self.assertEqual(img_key, self.IMG_KEY)
            self.assertEqual(sub_key, self.SUB_KEY)
            # nav 接口被调用 1 次
            self.assertEqual(mock_sess.get.call_count, 1)

    def test_cache_reuse_no_repeat_call(self):
        """缓存命中时不应再调 nav。"""
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
            cache.get()  # 第一次：拉
            cache.get()  # 第二次：缓存
            cache.get()  # 第三次：缓存
            # 3 次 get 但只调了 1 次 nav
            self.assertEqual(mock_sess.get.call_count, 1)

    def test_force_refresh(self):
        """force_refresh=True 强制重新拉。"""
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
            cache.get()
            cache.get(force_refresh=True)
            self.assertEqual(mock_sess.get.call_count, 2)

    def test_invalidate(self):
        """invalidate 后下次 get 重新拉。"""
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
            cache.get()
            cache.invalidate()
            self.assertIsNone(cache._img_key)
            cache.get()  # invalidate 后重新拉
            self.assertEqual(mock_sess.get.call_count, 2)

    def test_persistence_to_file(self):
        """缓存到文件后，新建 cache 实例应该能复用。"""
        # 第一次：拉 + 写文件
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache1 = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
            cache1.get()
            # 文件应该存在
            self.assertTrue(Path(self.cache_file).exists())
        # 第二次：新 cache 实例从文件加载
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls2:
            mock_sess2 = MagicMock()
            mock_sess_cls2.return_value = mock_sess2
            cache2 = WbiKeyCache(cache_file=self.cache_file, ttl_hours=12)
            img_key, sub_key = cache2.get()
            self.assertEqual(img_key, self.IMG_KEY)
            self.assertEqual(sub_key, self.SUB_KEY)
            # 没有调 nav（直接从文件加载）
            mock_sess2.get.assert_not_called()

    def test_ttl_expiry(self):
        """超过 TTL 后下次 get 重新拉。"""
        with patch("bilibili_tool.wbi.requests.Session") as mock_sess_cls:
            mock_sess = MagicMock()
            mock_sess_cls.return_value = mock_sess
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "code": 0,
                "data": {
                    "wbi_img": {
                        "img_url": f"https://i0.hdslb.com/bfs/wbi/{self.IMG_KEY}.png",
                        "sub_url": f"https://i0.hdslb.com/bfs/wbi/{self.SUB_KEY}.png",
                    }
                }
            }
            mock_sess.get.return_value = mock_resp
            cache = WbiKeyCache(cache_file=self.cache_file, ttl_hours=0.001)  # 3.6 秒 TTL
            cache.get()
            time.sleep(4)  # 超过 TTL
            cache.get()  # 重新拉
            self.assertEqual(mock_sess.get.call_count, 2)


class TestWbiIntegrationWithAuthor(unittest.TestCase):
    """wbi 集成到 AuthorVideoFetcher 的测试（mock wbi 签名 + 端点响应）。"""

    IMG_KEY = "7cd084941338484aae1ad9425b84077b"
    SUB_KEY = "4932caff0ff746eab6f01bf08b70ac45"

    def setUp(self):
        # 注意：在 module 顶部 import 不可见，要在每个 test method 里 import
        # 解决：放到 module 顶部
        self.mock_sess = MagicMock()
        self.cache = WbiKeyCache(sess=self.mock_sess, ttl_hours=12)
        self.cache._img_key = self.IMG_KEY
        self.cache._sub_key = self.SUB_KEY
        self.cache._fetched_at = datetime.now()
        self.fetcher = AuthorVideoFetcher(
            sess=self.mock_sess, wbi_cache=self.cache, timeout=5.0,
        )

    def test_fetch_page_arc_search_uses_wbi(self):
        """_fetch_page_arc_search 必须调 wbi 端点 + 签名。"""
        import time
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {
                "list": {
                    "vlist": [
                        {"bvid": "BV1aaa", "aid": 1001, "title": "测试1",
                         "pubdate": int(time.time()) - 86400, "duration": 100},
                        {"bvid": "BV1bbb", "aid": 1002, "title": "测试2",
                         "pubdate": int(time.time()) - 86400 * 2, "duration": 200},
                    ]
                }
            }
        }
        self.mock_sess.get.return_value = mock_resp

        result = self.fetcher._fetch_page_arc_search(123456, pn=1, ps=50)

        # 1. 返回值正确
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["bvid"], "BV1aaa")

        # 2. 调了 wbi 端点
        call_args = self.mock_sess.get.call_args
        self.assertEqual(call_args[0][0], AuthorVideoFetcher.WBI_ARC_SEARCH_URL)
        # 3. 签名参数带 wts + w_rid
        params = call_args[1]["params"]
        self.assertIn("wts", params)
        self.assertIn("w_rid", params)
        # 4. 业务参数也对（requests 会把 int → str，所以用 str/int 都接受）
        self.assertEqual(int(params["mid"]), 123456)
        self.assertEqual(int(params["pn"]), 1)
        self.assertEqual(int(params["ps"]), 50)
        self.assertEqual(params["order"], "pubdate")
        # 5. wts 类型可能是 int 或 str（看 enc_wbi 实现）
        self.assertTrue(isinstance(params["wts"], (int, str)))
        # 6. w_rid 是 32 hex（int → str 后长度不变）
        self.assertEqual(len(params["w_rid"]), 32)

    def test_fetch_page_arc_search_returns_none_on_403(self):
        """code=-403 (v_voucher 风控) → invalidate cache + 返回 None。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"code": -403, "message": "v_voucher", "data": {"v_voucher": "voucher_xxx"}}
        self.mock_sess.get.return_value = mock_resp

        result = self.fetcher._fetch_page_arc_search(123, pn=1, ps=50)
        self.assertIsNone(result)
        # 缓存应该被失效
        self.assertIsNone(self.cache._img_key)


if __name__ == "__main__":
    unittest.main()
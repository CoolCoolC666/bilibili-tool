"""Parser 单元测试：纯逻辑，不需要联网。"""
import unittest

from bilibili_tool.parser import parse_text, ParsedItem


class TestParseText(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse_text(""), [])

    def test_plain_av(self):
        # 裸数字默认不识别（避免把年份/统计数字当 AV 号）
        items = parse_text("170001")
        self.assertEqual(len(items), 0)
        # 显式 av 前缀仍然能识别短数字
        items = parse_text("av170001")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "170001")

    def test_plain_av_with_flag(self):
        # allow_bare_numbers=True 时识别 6+ 位裸数字
        items = parse_text("170001", allow_bare_numbers=True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")

    def test_av_with_prefix(self):
        items = parse_text("av170001")
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "170001")

    def test_av_with_prefix_uppercase(self):
        items = parse_text("AV170002")
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "170002")

    def test_bv(self):
        items = parse_text("BV1FpLU62EZW")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bv")
        self.assertEqual(items[0].value, "BV1FpLU62EZW")

    def test_full_url_bv(self):
        items = parse_text("https://www.bilibili.com/video/BV1FpLU62EZW")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bv")
        self.assertEqual(items[0].value, "BV1FpLU62EZW")

    def test_full_url_av(self):
        items = parse_text("https://www.bilibili.com/video/av170001")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "170001")

    def test_url_with_query(self):
        items = parse_text("https://www.bilibili.com/video/BV1FpLU62EZW?p=2&spm_id_from=test")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].value, "BV1FpLU62EZW")

    def test_mixed(self):
        text = "BV1FpLU62EZW av170001 av170002 https://www.bilibili.com/video/BV14QLU6dEuf"
        items = parse_text(text)
        kinds = [i.kind for i in items]
        values = [i.value for i in items]
        self.assertEqual(kinds, ["bv", "av", "av", "bv"])
        self.assertEqual(values, ["BV1FpLU62EZW", "170001", "170002", "BV14QLU6dEuf"])

    def test_dedupe(self):
        items = parse_text("BV1FpLU62EZW BV1FpLU62EZW av170001 170001")
        # 应该是 2 个：BV 和 AV 各一
        self.assertEqual(len(items), 2)

    def test_short_url(self):
        items = parse_text("https://b23.tv/abcdef")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "short_url")

    def test_short_numbers_ignored(self):
        # 默认模式：短数字 / 年份 / 统计数字都不识别
        self.assertEqual(parse_text("20"), [])
        self.assertEqual(parse_text("123"), [])
        self.assertEqual(parse_text("2026"), [])
        self.assertEqual(parse_text("1949"), [])

    def test_bare_numbers_default_off(self):
        # 默认 allow_bare_numbers=False：6 位裸数字也不识别
        self.assertEqual(parse_text("170001"), [])
        self.assertEqual(parse_text("12345678"), [])

    def test_bare_numbers_when_enabled(self):
        # 显式打开：6-16 位才识别（年份 4 位仍然不识别）
        from bilibili_tool.parser import parse_text as pt
        self.assertEqual(pt("170001", allow_bare_numbers=True), [ParsedItem("av", "170001", "170001")])
        self.assertEqual(pt("12345678", allow_bare_numbers=True), [ParsedItem("av", "12345678", "12345678")])
        # 年份仍然不识别（4 位 < 6 位）
        self.assertEqual(pt("2026 1949 1917", allow_bare_numbers=True), [])

    def test_bare_numbers_upper_limit(self):
        """--allow-bare-numbers 模式下，6-16 位数字识别；超过 16 位拒绝（避免误识别）。"""
        # 6 位边界
        self.assertEqual(len(parse_text("100000", allow_bare_numbers=True)), 1)
        # 13 位（旧的硬编码上限）现在仍识别
        self.assertEqual(len(parse_text("1234567890123", allow_bare_numbers=True)), 1)
        # 15 位（用户的真实场景）
        items = parse_text("113102813136198", allow_bare_numbers=True)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].value, "113102813136198")
        # 16 位边界
        self.assertEqual(len(parse_text("1234567890123456", allow_bare_numbers=True)), 1)
        # 17 位（超过上限）不识别
        self.assertEqual(len(parse_text("12345678901234567", allow_bare_numbers=True)), 0)

    def test_banquan_text_does_not_misfire(self):
        # 取自 ../测试数据/版权清单.txt 的前 15 行片段（无 bangumi/ep URL）
        text = """▶ [1] 今天，带你重读人民英雄纪念碑碑文！
  👤 UP主: 中国军号
  🔗 链接: https://www.bilibili.com/video/BV1P7DTBQEGm
  📅 时间: 2026-04-05
  --------------------------------------------------------
▶ [2] 全球最大经济体 | 国内生产总值史诗对决 (1560–2025)
  👤 UP主: Web3天空之城
  🔗 链接: https://www.bilibili.com/video/BV1moZCBjEHi
  📅 时间: 2026-02-17
  --------------------------------------------------------
▶ [5] 【五四运动】纪念五四运动100周年
  👤 UP主: 浙江共青团
  🔗 链接: https://www.bilibili.com/video/BV1c441147Hz
  📅 时间: 2019-05-03
"""
        items = parse_text(text)
        bvs = [i for i in items if i.kind == "bv"]
        # 期望：3 个 BV
        self.assertEqual(len(bvs), 3)
        bv_values = sorted(b.value for b in bvs)
        self.assertEqual(bv_values, ["BV1P7DTBQEGm", "BV1c441147Hz", "BV1moZCBjEHi"])
        # 不应该有 av 项（年份 2026/1949/1917 不应被当 AV 号）
        self.assertEqual([i for i in items if i.kind == "av"], [])
        # 也不应该把"2026""1949""1917""2019"误当 AV
        all_raw = [i.raw for i in items]
        for forbidden in ("2026", "1949", "1917", "2019", "2025", "100"):
            self.assertNotIn(forbidden, all_raw)

    def test_old_bv_format_still_works(self):
        # 2009-2010 年的老 BV 格式 BV1xx411c7mW 仍能识别
        items = parse_text("BV1xx411c7mW")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bv")
        self.assertEqual(items[0].value, "BV1xx411c7mW")

    def test_long_av_recognized(self):
        """回归测试：超过 12 位的 AV 号（15-18 位）也能识别，
        不会在 parser 阶段被截断或漏掉。语义上是否有效由 B 站 API 决定。"""
        # 15 位（v1 批量脚本里 30 个都是这个长度）
        self.assertEqual(
            parse_text("AV113102813136198"),
            [ParsedItem("av", "113102813136198", "AV113102813136198")],
        )
        # 18 位（B 站动态/评论/专栏 ID 也是 18 位，常常被某些抓取工具误当 av）
        self.assertEqual(
            parse_text("AV1700000000000000001"),
            [ParsedItem("av", "1700000000000000001", "AV1700000000000000001")],
        )
        # URL 里的 15 位 av
        self.assertEqual(
            parse_text("https://www.bilibili.com/video/av113102813136198"),
            [ParsedItem("av", "113102813136198", "https://www.bilibili.com/video/av113102813136198")],
        )

    def test_scientific_notation_recognized(self):
        """Excel 复制出来的科学记数法 AV 号（如 1.13103E+14）也能识别。

        精度会丢失（113103000000000 vs 真实 113102813136198），但 parser 不做
        语义判断，让 B 站 API 自己决定。
        """
        # 裸科学记数法
        items = parse_text("1.13103E+14")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "113103000000000")  # 精度丢失
        self.assertTrue(items[0].from_scientific)

        # 小写 e
        items = parse_text("1.13103e+14")
        self.assertEqual(items[0].value, "113103000000000")

        # 没 +
        items = parse_text("1.13103E14")
        self.assertEqual(items[0].value, "113103000000000")

        # 负指数不识别
        items = parse_text("1.5E-3")
        self.assertEqual(items, [])

        # 太短（< 6 位）不识别（避免把 1.0E+2 = 100 当 AV 号）
        items = parse_text("1.0E+2")
        self.assertEqual(items, [])

        # av 前缀 + 科学记数法
        items = parse_text("av1.13103E+14")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].value, "113103000000000")
        self.assertTrue(items[0].from_scientific)

    def test_scientific_in_mixed_text(self):
        """混合输入：科学记数法 + 普通 AV + 纯数字 + BV。"""
        text = """1.13103E+14
1103528937
BV1FpLU62EZW
"""
        items = parse_text(text)
        kinds = [i.kind for i in items]
        values = [i.value for i in items]
        self.assertEqual(kinds, ["av", "bv"])
        # 注意：1103528937 不会被识别（默认不识别裸数字）
        self.assertEqual(values, ["113103000000000", "BV1FpLU62EZW"])
        # 第一个标记为科学记数法
        self.assertTrue(items[0].from_scientific)
        self.assertFalse(items[1].from_scientific)

    def test_scientific_dedupes_same_value(self):
        """同一个数字用科学记数法 + 普通写两次，应该去重。"""
        items = parse_text("1.13103E+14 113103000000000")
        # 两种写法转成同一个 aid，去重后只 1 条
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].value, "113103000000000")

    def test_chunshanxiang_av_list(self):
        avs = """AV113102813136198
AV113458423078711
AV1103528937
AV113476374696630
AV116619502230093
AV113334976323110
AV1703515575
AV116832035937125
AV1255711161
AV113108735496084
AV113124489369161
AV113311437822880
AV116619502164179
AV113867820634857
AV116551604766319
AV116578414763925
AV116567543191244
AV116590393755720
AV116584471333577
AV116622656277271
AV116508453767007
AV116508386659007
AV116508285994813
AV116824821860180
AV116476795226846
AV116476711275018
AV116529676945259
AV116508520941172
AV116476828847077
AV116529643389126
AV116508252441280
AV116508504098576
AV116454968068779"""
        items = parse_text(avs)
        # 关键断言：33 个全部识别，0 个落
        self.assertEqual(len(items), 33, f"期望 33 项，实际 {len(items)} 项")
        # 都是 av 类型
        self.assertTrue(all(it.kind == "av" for it in items))
        # 数字部分保留完整
        self.assertEqual(items[0].value, "113102813136198")
        self.assertEqual(items[2].value, "1103528937")
        self.assertEqual(items[32].value, "116454968068779")

    def test_chinese_garbage(self):
        self.assertEqual(parse_text("随便写点中文，没有ID"), [])

    def test_garbage_with_bv(self):
        items = parse_text("这个视频 BV1FpLU62EZW 一定要看")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bv")

    def test_multi_line(self):
        text = """第一行 BV1FpLU62EZW
第二行 av170001
第三行 https://www.bilibili.com/video/BV14QLU6dEuf"""
        items = parse_text(text)
        self.assertEqual(len(items), 3)
        self.assertEqual([i.kind for i in items], ["bv", "av", "bv"])

    def test_url_does_not_double_count_inner_digits(self):
        # 完整 URL 里的 av170001 不能再被裸号识别一次
        text = "https://www.bilibili.com/video/av170001"
        items = parse_text(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "av")
        self.assertEqual(items[0].value, "170001")

    # === v2.8.0：专栏 / 番剧 / opus 识别 ===

    def test_article_url_old_format(self):
        """旧版专栏 URL：bilibili.com/read/cv{数字}"""
        items = parse_text("https://www.bilibili.com/read/cv12345")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")
        self.assertEqual(items[0].value, "12345")

    def test_article_url_opus_format(self):
        """v2.8.0：新增识别新版 opus URL：bilibili.com/opus/{数字}"""
        items = parse_text("https://www.bilibili.com/opus/1187639855606136839")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")
        self.assertEqual(items[0].value, "1187639855606136839")

    def test_article_url_mobile_subdomain(self):
        """m.bilibili.com 子域名也能识别（b23 短链有时跳移动版）"""
        items = parse_text("https://m.bilibili.com/opus/1176715576215601174")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")

    def test_article_url_no_subdomain(self):
        """无子域名也能识别"""
        items = parse_text("https://bilibili.com/read/cv999")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "article")

    def test_bangumi_ss_url(self):
        """番剧整季 URL：/bangumi/play/ss{数字}"""
        items = parse_text("https://www.bilibili.com/bangumi/play/ss67890")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bangumi_ss")
        self.assertEqual(items[0].value, "67890")

    def test_bangumi_ep_url(self):
        """番剧单集 URL：/bangumi/play/ep{数字}"""
        items = parse_text("https://www.bilibili.com/bangumi/play/ep1438464")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "bangumi_ep")
        self.assertEqual(items[0].value, "1438464")

    def test_mixed_video_article_bangumi(self):
        """混合输入：视频 + 专栏 + 番剧 + 短链"""
        text = (
            "BV1FpLU62EZW "
            "https://www.bilibili.com/read/cv12345 "
            "https://www.bilibili.com/bangumi/play/ss67890 "
            "https://www.bilibili.com/bangumi/play/ep1438464"
        )
        items = parse_text(text)
        kinds = [i.kind for i in items]
        self.assertEqual(kinds, ["bv", "article", "bangumi_ss", "bangumi_ep"])

    def test_mixed_article_opus_and_old_cv(self):
        """opus + cv 同时出现：都是 article，dedupe 按 (kind, value) 保留第一次"""
        text = (
            "https://www.bilibili.com/opus/111 "
            "https://www.bilibili.com/read/cv222"
        )
        items = parse_text(text)
        self.assertEqual([i.value for i in items], ["111", "222"])
        self.assertTrue(all(i.kind == "article" for i in items))

    def test_bangumi_ss_and_ep_same_season_dedup(self):
        """ss + ep 是同一季：先按 value 去重，保留 ss 形式（短数字优先）"""
        text = "https://www.bilibili.com/bangumi/play/ss67890 https://www.bilibili.com/bangumi/play/ep1438464"
        items = parse_text(text)
        # 两种 kind 不一样（bangumi_ss vs bangumi_ep），value 也不一样，不会自动去重
        self.assertEqual(len(items), 2)
        # 实际去重是 cache 阶段的事（同一条记录 ss+ep 都指向同一份 cache 记录）
        # parser 阶段保留 2 条，让下游 fetcher 处理
        self.assertEqual(items[0].kind, "bangumi_ss")
        self.assertEqual(items[1].kind, "bangumi_ep")

    def test_expand_short_url_to_bv(self):
        """b23 短链展开后是视频（BV/AV）"""
        from bilibili_tool.parser import expand_short_urls
        items = parse_text("https://b23.tv/HXDxEfr")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "short_url")
        expanded = expand_short_urls(items)
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0].kind, "bv")
        self.assertTrue(expanded[0].value.startswith("BV1"))

    def test_expand_short_url_to_article(self):
        """b23 短链展开后是专栏（opus）"""
        from bilibili_tool.parser import expand_short_urls
        items = parse_text("https://b23.tv/0qnXLMe")
        self.assertEqual(len(items), 1)
        expanded = expand_short_urls(items)
        # 0qnXLMe 实际跳转到 opus 形式
        self.assertEqual(expanded[0].kind, "article")

    def test_expand_short_url_to_bangumi(self):
        """b23 短链展开后是番剧（ep）"""
        from bilibili_tool.parser import expand_short_urls
        items = parse_text("https://b23.tv/ep1438464")
        self.assertEqual(len(items), 1)
        expanded = expand_short_urls(items)
        self.assertEqual(expanded[0].kind, "bangumi_ep")


if __name__ == "__main__":
    unittest.main()

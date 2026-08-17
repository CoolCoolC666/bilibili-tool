# 🎬  B 站视频信息抓取工具 v2

> 把一堆 AV / BV / 链接一次性丢进去，自动把每个视频的标题、UP 主、播放量、点赞、发布时间……整理成 xlsx / csv / json / txt 四种格式。带本地缓存 + 断点续传，命令行和 Web 两种入口。

旧版只能处理 AV 号、失效视频直接中断、没有 Web 界面；这一版全解决了。

---

## 👋  朋友看这里（5 步上手 / 复制粘贴就能跑）

> 第一次用这个工具？**不用读下面的所有内容**，按这 5 步走就能跑起来。

**1. 装 Python（如果没装的话）**
   - 下载 https://www.python.org/downloads/
   - 装的时候**务必勾上 `Add Python to PATH`**（第一个复选框）

**2. 拿到代码**
   - 点 https://github.com/CoolCoolC666/bilibili-tool 右上角绿色 `Code` → `Download ZIP`
   - 解压到任意文件夹（比如 `D:\tools\bilibili-tool`）

**3. 首次安装**
   - 进入解压后的文件夹，**双击 `install.bat`**
   - 它会自动：检查 Python → 创建虚拟环境 → 装依赖（用清华镜像，国内 30 秒）
   - 中间会问"按任意键继续"，按一下就行

**4. 启动 Web**
   - **双击 `start.bat`**
   - 2 秒后浏览器自动打开 http://127.0.0.1:5050

**5. 用起来**
   - 把一堆 AV / BV / 完整链接粘贴到文本框（每行一个、空格分开都行）
   - 点「开始抓取」
   - 等跑完，右上角 4 个下载按钮（xlsx / csv / json / txt）点哪个下哪个

**遇到问题？** 翻下面的"已知限制"和"常见问题"。**别慌**，B 站视频"失效 / 不可见"是正常的，不代表你操作错。

---

## 解决了旧版的 3 个问题

| 旧版问题 | 新版怎么做的 |
| --- | --- |
| ① 有些视频没有 AV 号，识别不了 | 输入解析支持 `AV号` / `BV号` / `完整 URL` / `b23.tv 短链` / 裸数字 / 混合输入，按出现顺序去重 |
| ② 输入方式不够便捷 | 提供 Flask 单页 Web：粘贴 → 按钮 → 实时看进度 → 直接下载 xlsx / csv / json / txt |
| ③ 失效视频怎么采集 | 失效 / 404 / 412 / 稿件不可见都会被捕获并标记 `not_found` + 写明 `api_code` + 错误原因，**不打断、不抛异常**，剩下的继续抓 |

---

## ✨ 特性

- **多输入格式**：纯 AV / av 前缀 / BV / 完整 URL / 短链 / 裸数字；混在一段文本里也行（自动按出现顺序解析 + 去重）
- **失败也能继续**：B 站常见的 `62002 稿件不可见` / `-404 不存在` / `412 已下架` 都被归类到 `not_found`，正常导出
- **本地 JSON 缓存**：跑过的 BV/AV 写到 `data/cache.json`，下次直接命中，不再发请求
- **跨 AV/BV 双索引**：同一条记录同时按 BV 号和 AV 号索引，用户输入 `BV1xxx 170001`（同一视频的两种 ID）**只发 1 个请求**
- **导出自动去重**：默认按 `(bvid, aid)` 去重，同一视频导出 xlsx/csv/json/txt 时**只占一行**。需要保留全部记录加 `--no-dedupe`
- **导出排除失效（v2.7+）**：可选 `--exclude-invalid` 只导出 `status="ok"` 的成功样本，自动剔除 `not_found` / `failed` 等失效条目。**写论文/数据分析的福音**——Excel 里不再满是"稿件不存在"
- **科学记数法 AV 号**：识别 `1.13103E+14` / `av1.13103E+14`（Excel 复制出来的格式）。注意精度会丢失
- **智能新鲜度**：默认动态字段（播放/点赞/收藏/评论/弹幕）**1 小时**内重抓；静态字段（标题/UP主/发布时间/时长）+ 失败/失效状态**永远缓存**
- **断点续传**：脚本中断、网断了、机器重启，下次跑同一份输入会跳过已记录的项接着抓
- **4 种导出格式**：`xlsx`（带表头样式 + 冻结首行）/ `csv`（UTF-8 BOM，Excel 直接打开）/ `json`（带 pretty print）/ `txt`（美观的极客风）
- **零 pandas 依赖**：xlsx 走纯 openpyxl，环境更精简，不会再撞 numpy 兼容性问题
- **三种入口**：Python 模块 / CLI 命令 / Web 页面，按需选择

---

## 📦 环境依赖

- Python ≥ 3.9
- 第三方库：
  - `requests` ≥ 2.28
  - `openpyxl` ≥ 3.0
  - `flask` ≥ 2.0

```bash
pip install -r requirements.txt
```

> **注意**：v2 不再依赖 pandas / numpy，xlsx 导出直接走 openpyxl。这样在精简环境（哪怕 Python 3.13 + numpy 还没适配）也能跑通。

---

## 🚀 安装

```bash
git clone <your-repo-url>   # 或者直接下载 zip 解压
cd bilibili_tool_v2
pip install -r requirements.txt
```

---

## 🖥  CLI 用法

最简形态：直接跟一段 ID 就行。

```bash
python cli.py "BV1FpLU62EZW av170001 https://www.bilibili.com/video/BV1hy4y1B7sX"
```

### 常用参数

```text
输入源（互斥）
  text                    命令行直接跟 ID / 链接
  -f, --file FILE         从文件读取（每行一段）
  --stdin                 强制从 stdin 读取

输出
  -o, --output NAME       输出文件名前缀，默认 bilibili_<时间戳>
  --out-dir DIR           输出目录，默认 ./output
  --format {xlsx,csv,json,txt,all}
                          导出格式，默认 all（一次性全导出）
  --dedupe                导出时按 (BV, AV) 去重，同一视频只出现一行（默认开）
  --no-dedupe             不去重，保留所有记录
  --exclude-invalid       导出时排除无效视频（不统计）。只保留 status=ok 的成功记录，
                          剔除 not_found / failed 等失效条目。默认关闭

缓存
  --cache PATH            缓存文件路径，默认 ./data/cache.json
  --no-cache              完全不用缓存（等价于 --max-age 0）
  --max-age DURATION      动态字段（播放/点赞/收藏/评论/弹幕）最大缓存年龄
                          格式 '30m' / '1h' / '24h' / '7d'
                          '0' = 不用缓存，'never' = 永远信任
                          默认 '1h'
                          （静态字段和失败状态永远缓存，不受此影响）
  --reset-cache           先清空缓存再开始
  --save-cache            抓取后写回缓存（默认开）

网络
  --delay SECONDS         每个请求间隔秒，默认 0.6
  --retry N               每个 ID 的最大重试次数，默认 2
  --timeout SECONDS       单次请求超时秒，默认 10

解析
  --allow-bare-numbers    允许把 6-13 位裸数字当 AV 号
                          （默认关闭，避免把年份/统计数字误识别；
                          开了之后 "170001" 才会被识别）
```

### ⚠ 关于"裸数字 AV 号"

> **v2.1 起默认不再把裸数字当 AV 号**。原因是：
> 版权清单这类"含大量数字"的文本里，年份（2026 / 1949 / 1917）和统计数字（100 / 10086）会被错误识别为 AV 号去查询，污染结果。

**默认行为**（推荐）：

```bash
# 这三种写法都能识别：
python cli.py "BV1FpLU62EZW"
python cli.py "av170001"
python cli.py "https://www.bilibili.com/video/BV1hy4y1B7sX"

# 裸数字 "170001" 不会被识别（要明确写 av 前缀）
```

**如果你确实想识别裸数字**（如"170001"直接给）：

```bash
python cli.py --allow-bare-numbers "170001"
```

开了之后，6-13 位的纯数字才会被识别（年份 4 位数字仍然不会被识别，放心）。

### 示例

```bash
# 1) 从文件读 + 只导出 xlsx
python cli.py -f input.txt --format xlsx -o my_batch

# 2) 短链混入，自动展开
python cli.py "https://b23.tv/xxxxxx BV1FpLU62EZW"

# 3) 强制重抓（忽略缓存）
python cli.py --no-cache "BV1hy4y1B7sX"

# 4) 清空缓存后再跑
python cli.py --reset-cache "BV1FpLU62EZW BV14QLU6dEuf"

# 5) 从 stdin 管道喂
echo "BV1FpLU62EZW BV14QLU6dEuf" | python cli.py --stdin

# 6) 识别裸数字
python cli.py --allow-bare-numbers "170001 170002 170003"
```

### 在 Python 里直接用

```python
from bilibili_tool import parse_text, BilibiliVideoFetcher, Cache, export_all

text = "BV1FpLU62EZW av170001 170002 https://www.bilibili.com/video/BV1hy4y1B7sX"
parsed = parse_text(text)
print("解析到：", parsed)

cache = Cache("data/cache.json")
fetcher = BilibiliVideoFetcher(max_retries=2, timeout=10.0)

results = []
for p in parsed:
    sk = ...  # 构造对应 kind 的 VideoInfo 用来查缓存
    cached = cache.get(sk) if (sk := skeleton_of(p)) else None
    if cached and cached.status in ("ok", "not_found", "failed"):
        results.append(cached)
        continue
    info = fetcher.fetch_with_retry(p)
    cache.put(info)
    results.append(info)

cache.save()
export_all(results, base="my_run", out_dir="output")
```

---

## 🌐  Web 用法

```bash
python run_web.py
# 默认 http://127.0.0.1:5050
```

打开浏览器访问 `http://127.0.0.1:5050`，界面长这样：

```
┌────────────────────────────────────────┐
│  🎬 B 站视频信息抓取工具                │
├────────────────────────────────────────┤
│  ① 输入待抓取的 ID / 链接              │
│  ┌──────────────────────────────────┐  │
│  │ BV1FpLU62EZW                     │  │
│  │ av170001                         │  │
│  │ https://www.bilibili.com/...     │  │
│  └──────────────────────────────────┘  │
│  [高级选项 ▼]   [开始抓取] [清空日志]  │
│                                        │
│  ② 进度                                │
│  ████████░░░░░░░░  60%   60 / 86      │
│  成功 12  失败 45  缓存命中 3           │
│  ┌── 实时日志 ──────────────────────┐  │
│  │ [14:23:01] 解析到 86 个目标      │  │
│  │ [14:23:02]   [1/86] ✓ xxx        │  │
│  └─────────────────────────────────┘  │
│                                        │
│  ③ 结果                                │
│  [下载 XLSX] [下载 CSV] [下载 JSON]    │
│  ┌─ 状态 / BV / 标题 / UP / 数据 ──┐   │
│  │  ...                            │   │
│  └─────────────────────────────────┘   │
└────────────────────────────────────────┘
```

Web 后端用 **SSE (Server-Sent Events)** 实时推进度，前端零框架（纯 HTML + CSS + JS），启动就能用。

如果要局域网共享给同事看（只读、本地无敏感数据时）：

```bash
python run_web.py --host 0.0.0.0 --port 5050
```

⚠ **生产环境请勿用 Flask 自带 dev server**，加并发建议换 `gunicorn -w 4 'web.app:app'`。

---

## 🧪  测试

### 单元测试（无需联网）

```bash
python -m unittest tests.test_parser -v
```

覆盖 16 个用例：纯 AV / av 前缀 / BV / 完整 URL / 短链 / 混合输入 / 多行 / 中文混入 / URL 内嵌 av 数字不重复 / 顺序保持 / 去重 等。

### 真实数据验证（用同目录的 `../测试数据/`）

我在 v2 跑过 `XX事件视频数据-完整版.xlsx`相关数据（89 条 / 86 个独立 BV），结果：

| 指标 | 数值 |
| --- | --- |
| 总独立 BV | 86 |
| 新抓 | 86 |
| 耗时 | 95 秒 |
| 成功 | 8 |
| 失败（`not_found` / `failed`）| 78 |
| 缓存写入 | 86 条 |

符合预期——XX事件 4K 修复版 80%+ 已下架，B 站返回 62002 稿件不可见 / -404 视频不存在，新版正确标记且不中断。

第二次跑同样输入：

```
[1/3] ✗ BV1FpLU62EZW   [not_found/62002]   ↪ cache hit
[2/3] ✗ BV14QLU6dEuf   [not_found/62002]   ↪ cache hit
[3/3] ✓ 欢乐麻将练习P532   [ok/0]
```

5/5 缓存命中 0.00s 完成——断点续传有效。

---

## 📁  项目结构

```
bilibili_tool_v2/
├── bilibili_tool/            # 核心库
│   ├── __init__.py
│   ├── models.py             # 数据模型（dataclass）
│   ├── parser.py             # 多输入解析
│   ├── fetcher.py            # B 站 API 客户端
│   ├── cache.py              # JSON 缓存 + 原子写入
│   └── exporter.py           # xlsx / csv / json / txt
├── web/                      # Web 应用
│   ├── app.py                # Flask + SSE
│   ├── templates/index.html
│   └── static/{style.css,app.js}
├── tests/
│   └── test_parser.py
├── data/cache.json           # 缓存（自动生成，gitignore）
├── output/                   # 导出目录（自动生成，gitignore）
├── cli.py                    # CLI 入口
├── run_web.py                # Web 启动
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

---

## ⚠️  已知限制

- **频率限制**：连续大量请求可能触发 B 站风控。`--delay` 默认 0.6s 比较保守；如果跑 100+ 个视频可以调到 1.0s 稳一点
- **短链解析**：b23.tv 短链需要先发一次 HEAD 请求才能展开，会多一次网络往返
- **番剧/合集 URL**：`https://www.bilibili.com/bangumi/play/epXXX` 这种番剧链接目前**不识别**（只能识别 `/video/...` 单视频 URL），会被静默跳过。如果需要支持可以加，但 v2.1 暂未做
- **失效视频**：B 站 API 只告诉你"不可见"，不会告诉你为什么；想要"原始数据"只能从你自己之前的归档/截图里手动补
- **登录态**：当前是匿名访问，部分"仅会员可见"视频即使存在也拿不到——这种也归到 `not_found`

---

## 🗺  后续计划（AI工具的建议，这边我可能会维护的）

- [ ] 加 `seeduuid` cookie 支持（绕过部分风控 + 看会员视频）
- [ ] 加 `--from-xlsx` 选项，从现有表格的 BV 列直接读输入
- [ ] 加 `--merge` 选项，把新抓的字段填回原 xlsx 的"真实"列，保留"原始"列做对比
- [ ] 加 简易 Dockerfile
- [ ] 失败视频尝试从 Wayback Machine 拉历史快照（这是个独立大 feature，先列着）

---

## 📝  版本历史

### v2.7.0（2026-08-17）

- **修复**：`--allow-bare-numbers` 裸数字识别上限从 13 位放宽至 **16 位**，覆盖现行 15 位 AV 号（如 `113102813136198`）。无效数字由 B 站 API 自然淘汰为 `not_found`
- **新增**：导出选项 **"排除无效视频（不统计）"**。开启后，导出文件**只包含 `status="ok"` 的成功抓取记录**，自动剔除 `not_found` / `failed` 等失效条目。**写论文/数据分析的福音**——Excel 里不再满是"稿件不存在"
  - CLI 新增 `--exclude-invalid` 参数
  - Web UI 新增复选框「导出时排除无效视频（不统计）」（默认关闭，保留原始全部导出行为）
  - 处理顺序：**先过滤后去重**（逻辑更清晰）

### v2.6.0（2026-08-17）

- **新增**：parser 支持**科学记数法 AV 号**（如 `1.13103E+14` / `av1.13103E+14`）。这是从 Excel 复制 B 站 aid 时的常见格式
- **注意**：科学记数法转换**会丢失精度**（`1.13103E+14` → `113103000000000`，跟真实 aid `113102813136198` 差 1.87 亿）。B 站 API 多数会返回 `62002`，需要用精确的 aid 重新查询
- **新标志**：`ParsedItem.from_scientific` 标记哪些 ID 来源于科学记数法转换

### v2.5.0（2026-08-17）

- **新增**：导出文件支持**去重**。默认按 `(bvid, aid)` 去重，同一视频在 xlsx/csv/json/txt 里**只占一行**
- **新增**：`--dedupe` / `--no-dedupe` CLI 开关
- **新增**：Web UI「导出时去重」checkbox（默认勾选）
- **新增**：`dedupe_videos()` 工具函数，可在 Python 里直接调用
- **新增**：17 个 exporter 测试覆盖去重 + 4 种格式

### v2.4.0（2026-08-17）

- **新增**：cache 跨 AV/BV 双索引。同一条记录同时按 BV 号和 AV 号索引，用户输入 `BV1xxx 170001`（同一视频的两种 ID）**只发 1 个请求**。第二次跑也只发 1 个（甚至 0 个，如果之前抓过同视频的另一种 ID）
- **新增**：旧 cache 自动升级。加载旧版单 key 索引的 `data/cache.json` 时自动补全双索引，不用手动迁移
- **新增**：测试覆盖双索引 + 升级 + 持久化场景

### v2.3.0（2026-08-17）

- **修复**：cache 永远不过期的问题。B 站数据是实时更新的，播放/点赞/收藏一直在变。现在 cache 按字段类型差异化过期：
  - **静态字段**（标题/UP主/发布时间/时长/简介/分区）：永远缓存
  - **动态字段**（播放/点赞/投币/收藏/分享/评论/弹幕）：默认 1h 过期（可配）
  - **失败/失效状态**（not_found / failed）：永远缓存（视频失效不会"复活"）
- **新增**：`--max-age DURATION` CLI flag（`30m` / `1h` / `24h` / `7d` / `never` / `0`）
- **新增**：Web UI「缓存新鲜度」下拉（实时/当天/本周/永远）
- **新增**：测试覆盖 18 个 cache 场景（`tests/test_cache.py`）

### v2.2.0（2026-08-17）

- **修复**：15 位 AV 号不再被 parser 截断丢失。B 站 view API 实际上**接受 15 位 aid**（v1 硬编码 list 33 个 AV 号 30 个是 15 位），v2 之前 `RE_AV` 上限 12 位导致 30 个全部漏识别，输出里只有 3 个 10 位的。现在上限放宽到 20 位，parser 阶段只做语法识别、语义交给 B 站 API
- **新增**：测试覆盖 15 位 / 18 位 AV 号 + 33 个真实 AV 号列表回归

### v2.1.0（2026-08-17）

- **修复**：默认不再把 4-5 位裸数字（年份/统计数字）当 AV 号。版权清单这类含大量数字的文本过去会污染结果，现在默认安全
- **新增**：`--allow-bare-numbers` CLI 开关 / Web UI checkbox，需要时手动开启（识别 6-13 位裸数字）
- **新增**：测试用例覆盖回归场景

### v2.0.0（2026-08）

完全重写，对比 v1：

- 输入：只接 AV → AV / BV / URL / 短链 / 混合
- 失效处理：直接报错 → 标记 + 跳过 + 导出
- 持久化：无 → JSON 缓存 + 断点续传
- 入口：单脚本 → CLI + Web
- 导出：xlsx + txt → xlsx + csv + json + txt
- 依赖：含 pandas → 仅 requests + openpyxl + flask

---

## 🙏  致谢

- 原 `bilibili_tool.py` 和 `Python批量获取B站视频数据脚本.py` 的作者（都是映月/我自己）
- 对于上海某高校事件 4K 修复版和hibiki相关视频的采集数据——这两份测试数据帮我验证了 80%+ 失效场景下脚本不会崩
- B 站公开 API（`api.bilibili.com/x/web-interface/view`）

---

## 📄  License

MIT — 详见 [LICENSE](LICENSE)。

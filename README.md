# 🎬  B 站信息抓取工具 v3.0.9-alpha（视频 / 专栏 / 番剧 + 按 UP 主抓取）

> 把一堆 **VIDEO 视频** / **ARTICLE 专栏** / **BANGUMI 番剧** 的 ID 或链接一次性丢进去，自动按类型分类 + 抓取，整理成 xlsx / csv / json / txt 四种格式。带本地缓存 + 断点续传，命令行和 Web 两种入口。
>
> **v3.0+ 新增**：按 UP 主批量抓取（`/author` 页面）+ 4 套可切换数据源（**自主 WBI / uapis.cn / 旧端点 / 自动降级链**）+ 翻页间隔自定义。

| 🎬 VIDEO 视频 | 📝 ARTICLE 专栏 | 🎬 BANGUMI 番剧 | 🆕 按 UP 主抓取（v3.0+） |
|:---:|:---:|:---:|:---:|
| BV / av / URL / 短链 | read/cv + opus + 短链 | ss / ep + 短链 | UID / space 链接 / 短链 → 阶段 1 列表 + 阶段 2 详情 |

---
> ## ⚠️ 使用限制
>
> 本工具仅供学习与研究用途，使用即代表您同意以下限制：
> 1. **禁止**用于大规模、自动化地爬取 bilibili.com 数据。
> 2. **禁止**尝试绕过 bilibili.com 的任何技术措施或频率限制。
> 3. **禁止**将本工具获取的数据进行批量再分发。
> 4. **禁止**以任何违反 bilibili.com 服务条款的方式使用本工具。

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
   - 把一堆 **视频 / 专栏 / 番剧** ID 或链接粘贴到文本框（每行一个、空格分开都行）
   - 点「开始抓取」
   - 等跑完，右上角下载按钮点哪个下哪个（**类型名直接显示在文件名里**，详见下方"下载文件类型"）
   - **v3.0+ 想按 UP 主批量抓？** 直接点顶部导航的「按 UP 主抓取」（`/author`），详见下方 v3.0+ 新功能专区

---

## 🚀 v3.0+ 新功能专区（按 UP 主批量抓 + 数据源切换）

> **一句话**：除了原来"按 ID 抓"模式，v3.0+ 还支持"按 UP 主 UID 抓该 UP 的全部投稿"。**数据源可切**（自主 WBI / uapis.cn / 旧端点 / 自动降级链），避开 B 站风控。

### 入口

```
http://127.0.0.1:5050/author    ← 启动 Web 后访问这个路径
```

### 流程

```
阶段 1：拉 UP 主视频列表（UID/链接/短链 → CSV）
   ↓
阶段 2：从 CSV 抓每条视频详情（XLSX）
```

两阶段都支持批量、实时进度、文件管理（删除 / 打开 / 批量删除）。

### 4 套数据源（v3.0+ 关键新功能）

| 数据源 | 是否需要 key | QPS | 特点 | 适用 |
|---|---|---|---|---|
| **uapis.cn**（默认）| 可选（访客免 key）| 访客 4 / 登录 7 | 国产第三方 + 5 端点 + 访客 1500 积分/月（基础接口 1 积分/次；B 站 5 端点 4 积分/次）| **首选**：风控少、积分便宜 |
| **self-wbi** | 不需要 | 0（受 B 站风控，-799/412 多）| 自主 WBI 签名调用 B 站官方端点 | 网络好 + B 站不限流时 |
| **self-legacy** | 不需要 | 0（受 B 站风控，5 个 UP 主后必触发 -799）| 旧端点（无 WBI）| 仅最末位降级 |
| **自动降级链** | — | — | 优先 self-wbi → uapis 访客 → self-legacy | **默认**：自动选最稳的 |

**降级链逻辑**：所选 provider 限流（uapis 429 / B 站 -799）时**自动切换到下一个 provider**。其他错误（鉴权 / 资源不存在 / 网络）直接抛，不降级。

### ⏱ 翻页请求间隔自定义（v3.0.9+）

> **新功能**：在「⚙ 数据源设置」卡片可以**手动设置翻页间隔**（毫秒），避开 429 / 月度额度过快耗尽。

| 推荐场景 | 间隔 |
|---|---|
| uapis 访客 + 日常抓取 | **250ms**（默认 = 4 QPS）|
| uapis 访客 + 保守抓取 | **1500ms**（FAQ Q15 推荐）|
| uapis 访客 + 429 频发 | **2000-4000ms**（Q14 退避）|
| uapis 登录 + 高速抓 | **142ms**（7 QPS）|
| 自测 / 调试 | **0ms**（不 sleep）|

依据：uapis FAQ Q13（QPS 表）/ Q14（429 退避 0.5/1/2/4s）/ Q15（≥1500ms 保守）。

### 🆕 还有什么 v3.0+ 才有的能力？

- **UP 主主页信息批量抓取**（`/api/author/profile`）：一次抓多个 UP 主的昵称 / 等级 / 粉丝数 / 投稿数，导出 CSV + XLSX
- **数据完整性提示**：uapis 数据不是 100% 完整时（如老 UP 主只能拿 50-60%），结果页会标"⚠ 数据可能不完整"
- **另存按钮**（v3.0.8+）：用 File System Access API 弹文件选择器，**不弹浏览器"另存为"**（Chrome/Edge 86+）
- **在文件管理器中打开**（v3.0.7+）：智能定位（CSV → `output/`，XLSX → `output/xlsx/`）+ 高亮文件
- **批量删除**（v3.0.2+）：通配符 `*` / `?` / `[seq]` 一次清多个测试残留
- **日期快捷按钮**（v3.0.3+）：近 7/30/90 天 / 全部时间，4 个预设一键
- **实时进度**（v3.0.4+）：后台线程 + 前端 0.6s 轮询，看得见在抓哪个

---

## 🎯 三种内容类型速查（一图看懂）

| 类型 | 是什么 | URL 例子 | 抓取字段 |
|------|--------|---------|---------|
| 🎬 **VIDEO**（视频） | 普通投稿视频 | `bilibili.com/video/BV1xxx`<br>`bilibili.com/video/av170001`<br>`b23.tv/xxxxxx` | 标题、UP主、播放、点赞、投币、收藏、分享、评论、弹幕、时长、发布时间、简介 |
| 📝 **ARTICLE**（专栏） | B 站长文 / 动态专栏 | `bilibili.com/read/cv12345`<br>`bilibili.com/opus/12345`<br>`b23.tv/xxxxxx`（自动判断） | 标题、作者、阅读、点赞、投币、收藏、分享、评论、字数、创建时间、摘要、封面 |
| 🎬 **BANGUMI**（番剧） | 番剧 / 国创 / 纪录片 | `bilibili.com/bangumi/play/ss67890`<br>`bilibili.com/bangumi/play/ep12345`<br>`b23.tv/xxxxxx`（自动判断） | 标题、别名、类型、评分、评分人数、总集数、状态（已完结/连载中）、上线日期、播放、追番、投币 |

> **怎么用？** —— **不用选类型**！把链接粘进去，工具自动识别。Web UI 抓完会在结果表格里用**类型标签**标出来（视频/专栏/番剧）。

---

## 📦 下载文件类型（v2.8 输出 10 个文件）

抓完会同时生成 **xlsx 1 个 + csv/json/txt 各 3 个**，按类型区分：

```
output/
├── my_run.xlsx              ← 🎯 推荐！3 个 sheet：[视频数据] [专栏数据] [番剧数据]
├── my_run_video.csv         ← 只有视频
├── my_run_video.json
├── my_run_video.txt
├── my_run_article.csv       ← 只有专栏
├── my_run_article.json
├── my_run_article.txt
├── my_run_bangumi.csv       ← 只有番剧
├── my_run_bangumi.json
└── my_run_bangumi.txt
```

**Web UI 上**直接显示 10 个下载按钮，按类型命名：
```
下载 CSV_ARTICLE  下载 CSV_BANGUMI  下载 CSV_VIDEO
下载 JSON_ARTICLE 下载 JSON_BANGUMI 下载 JSON_VIDEO
下载 TXT_ARTICLE  下载 TXT_BANGUMI  下载 TXT_VIDEO
下载 XLSX                       ← 3 个 sheet 在同一文件
```

> **如果只抓视频**：只会有 `*_video.{csv,json,txt}` + `xlsx`（旧行为，向后兼容）。
> **如果只抓专栏/番剧**：同上，按类型拆分。

**遇到问题？** 翻下面的"已知限制"和"常见问题"。**别慌**，B 站视频"失效 / 不可见"是正常的，不代表你操作错。

---

## 解决了旧版的 4 个问题

| 旧版问题 | 新版怎么做的 |
| --- | --- |
| ① 有些视频没有 AV 号，识别不了 | 输入解析支持 `AV号` / `BV号` / `完整 URL` / `b23.tv 短链` / 裸数字 / 混合输入，按出现顺序去重 |
| ② 输入方式不够便捷 | 提供 Flask 单页 Web：粘贴 → 按钮 → 实时看进度 → 直接下载 xlsx / csv / json / txt |
| ③ 失效视频怎么采集 | 失效 / 404 / 412 / 稿件不可见都会被捕获并标记 `not_found` + 写明 `api_code` + 错误原因，**不打断、不抛异常**，剩下的继续抓 |
| ④ 只能抓视频（v2.7 及之前） | **v2.8 新增**：**ARTICLE 专栏**（read/cv + opus）和 **BANGUMI 番剧**（ss + ep）也支持，跟视频一样有缓存 / 去重 / 断点续传，下载文件按类型自动拆分 |

---

## ✨ 特性

### 按 ID 抓（v2.x 老能力）

- **🎬 三类内容支持（v2.8+）**：**VIDEO 视频**（AV/BV/URL/短链）+ **📝 ARTICLE 专栏**（read/cv + opus）+ **🎬 BANGUMI 番剧**（ss + ep）。混在一段文本里也能自动按出现顺序解析 + 去重
- **b23 短链自动分类**：粘贴 `b23.tv/xxxxxx`，自动跟随 302 跳转识别属于视频/专栏/番剧中的哪一类
- **失败也能继续**：B 站常见的 `62002 稿件不可见` / `-404 不存在` / `412 已下架` / `-509 限流` 都被归类到 `not_found`，正常导出
- **本地 JSON 缓存（3 类独立）**：视频写 `data/cache.json`，专栏写 `cache_article.json`，番剧写 `cache_bangumi.json`，下次直接命中，不再发请求
- **跨 ID 双索引**：视频（BV+AV）/ 番剧（ss+ep）都按两种 ID 索引，用户输入 `BV1xxx av170001`（同一视频的两种 ID）**只发 1 个请求**
- **导出自动去重**：默认按 `(bvid, aid)` / `cv` / `ss+ep` 去重。同一内容导出 xlsx/csv/json/txt 时**只占一行**。需要保留全部记录加 `--no-dedupe`
- **导出排除失效（v2.7+）**：可选 `--exclude-invalid` 只导出 `status="ok"` 的成功样本，自动剔除 `not_found` / `failed` 等失效条目。**写论文/数据分析的福音**——Excel 里不再满是"稿件不存在"
- **科学记数法 AV 号**：识别 `1.13103E+14` / `av1.13103E+14`（Excel 复制出来的格式）。注意精度会丢失
- **智能新鲜度**：默认动态字段（播放/点赞/收藏/评论/弹幕）**1 小时**内重抓；静态字段（标题/UP主/发布时间/时长）+ 失败/失效状态**永远缓存**
- **断点续传**：脚本中断、网断了、机器重启，下次跑同一份输入会跳过已记录的项接着抓
- **4 种导出格式 + 3 sheet xlsx（v2.8+）**：`xlsx`（带表头样式 + 冻结首行 + 3 sheet 视频/专栏/番剧）/ `csv`（UTF-8 BOM，Excel 直接打开）/ `json`（带 pretty print）/ `txt`（美观的极客风）。**每种类型单独成文件**（`*_video.csv` / `*_article.csv` / `*_bangumi.csv`）
- **零 pandas 依赖**：xlsx 走纯 openpyxl，环境更精简，不会再撞 numpy 兼容性问题
- **三种入口**：Python 模块 / CLI 命令 / Web 页面，按需选择

### 按 UP 主抓（v3.0+ 新能力）

- **🆕 按 UP 主 UID 批量抓**：阶段 1 拉列表（→ CSV）→ 阶段 2 抓详情（→ XLSX）。**支持多 UP 主批量 + 多 CSV 批量**
- **🆕 4 套数据源切换**：
  - **uapis.cn**（默认）：访客 4 QPS / 登录 7 QPS，中文文档 + 5 端点 + 15 分钟缓存
  - **self-wbi**：自主 WBI 签名调用 B 站官方端点（v2.9.1+），免费但受 B 站风控
  - **self-legacy**：旧端点（无 WBI），最末位降级
  - **自动降级链**：限流（uapis 429 / B 站 -799）时自动切到下一个 provider，其他错误直接抛
- **🆕 API key 只存 localStorage**（不上传服务器）：明文存浏览器，**用户隐私可控**
- **🆕 翻页间隔自定义（v3.0.9+）**：在「数据源设置」卡片手动设置毫秒值，避开 429。**默认 250ms = 4 QPS**（uapis 访客档）
- **🆕 数据完整性提示**：uapis 数据不是 100% 时（如老 UP 主只能拿 50-60%），结果页标 "⚠ 数据可能不完整"
- **🆕 UP 主主页信息批量抓**（v3.0.6+）：一次抓多个 UP 主的昵称/等级/粉丝数/投稿数，导出 CSV + XLSX
- **🆕 实时进度**（v3.0.4+）：异步任务 + 前端 0.6s 轮询，看得见在抓哪个
- **🆕 另存按钮**（v3.0.8+）：用 File System Access API 弹文件选择器，不弹浏览器"另存为"（Chrome/Edge 86+）
- **🆕 在文件管理器中打开**（v3.0.7+）：智能定位（CSV → `output/`，XLSX → `output/xlsx/`）+ 高亮文件
- **🆕 批量删除**（v3.0.2+）：通配符 `*` / `?` / `[seq]` 一次清多个测试残留
- **🆕 日期快捷按钮**（v3.0.3+）：近 7/30/90 天 / 全部时间

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
  --dedupe                导出时按 (BV, AV) / (cv) / (ss+ep) 去重（默认开）
  --no-dedupe             不去重，保留所有记录
  --exclude-invalid       导出时排除无效记录（不统计）。只保留 status=ok 的成功记录，
                          剔除 not_found / failed 等失效条目。默认关闭

抓取内容（v2.8+）
  --fetch-articles        识别到专栏 URL/ID 时自动抓取（默认开）
  --no-fetch-articles     跳过专栏抓取
  --fetch-bangumi         识别到番剧 URL/ID 时自动抓取（默认开）
  --no-fetch-bangumi      跳过番剧抓取

缓存
  --cache PATH            视频缓存文件路径，默认 ./data/cache.json
  --cache-article PATH    专栏缓存文件路径，默认 ./data/cache_article.json
  --cache-bangumi PATH    番剧缓存文件路径，默认 ./data/cache_bangumi.json
  --no-cache              完全不用缓存（等价于 --max-age 0）
  --max-age DURATION      动态字段最大缓存年龄
                          格式 '30m' / '1h' / '24h' / '7d'
                          '0' = 不用缓存，'never' = 永远信任
                          默认 '1h'
  --reset-cache           先清空全部缓存再开始
  --save-cache            抓取后写回缓存（默认开）

网络
  --delay SECONDS         每个请求间隔秒，默认 0.6
  --retry N               每个 ID 的最大重试次数，默认 2
  --timeout SECONDS       单次请求超时秒，默认 10

解析
  --allow-bare-numbers    允许把 6-16 位裸数字当 AV 号
                          （默认关闭，避免把年份/统计数字误识别）
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

开了之后，6-16 位的纯数字才会被识别（年份 4 位数字仍然不会被识别，放心）。

### 示例

```bash
# 1) 从文件读 + 只导出 xlsx
python cli.py -f input.txt --format xlsx -o my_batch

# 2) 短链混入，自动展开 + 自动分类（v2.8+）
python cli.py "https://b23.tv/HXDxEfr https://b23.tv/0qnXLMe https://b23.tv/ep1438464"

# 3) 强制重抓（忽略缓存）
python cli.py --no-cache "BV1hy4y1B7sX"

# 4) 清空缓存后再跑
python cli.py --reset-cache "BV1FpLU62EZW BV14QLU6dEuf"

# 5) 从 stdin 管道喂
echo "BV1FpLU62EZW BV14QLU6dEuf" | python cli.py --stdin

# 6) 识别裸数字
python cli.py --allow-bare-numbers "170001 170002 170003"

# 7) v2.8+ 混导视频/专栏/番剧
python cli.py "https://www.bilibili.com/video/BV1xxx https://www.bilibili.com/read/cv12345 https://www.bilibili.com/bangumi/play/ss67890" -o my_v280

# 8) 只抓视频，跳过专栏/番剧
python cli.py --no-fetch-articles --no-fetch-bangumi "https://www.bilibili.com/video/BV1xxx"
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
┌────────────────────────────────────────────────────────┐
│  🎬 B 站信息抓取工具（视频 / 专栏 / 番剧）            │
├────────────────────────────────────────────────────────┤
│  ① 输入待抓取的 ID / 链接                              │
│  ┌────────────────────────────────────────────────┐    │
│  │ https://www.bilibili.com/video/BV1FpLU62EZW    │    │
│  │ https://www.bilibili.com/read/cv12345          │    │
│  │ https://www.bilibili.com/bangumi/play/ss67890  │    │
│  │ https://b23.tv/xxxxxx                          │    │
│  └────────────────────────────────────────────────┘    │
│  [高级选项 ▼]   [开始抓取] [清空日志]                  │
│                                                        │
│  ② 进度                                                │
│  ████████████░░░░░░░  60%   视频 12 / 专栏 5 / 番剧 3 │
│  成功 18  失败 1  缓存命中 2                           │
│  ┌── 实时日志 ──────────────────────────────────────┐  │
│  │ [14:23:01] 解析到 86 个 → 视频 60 / 专栏 20 /...│  │
│  │ [14:23:02] 📹 [1/60] ✓ 视频A                     │  │
│  │ [14:23:05] 📝 [1/20] ✓ 专栏A                     │  │
│  │ [14:23:10] 🎬 [1/6]  ✓ 番剧A                     │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  ③ 结果（按类型下载）                                  │
│  [CSV_ARTICLE][CSV_BANGUMI][CSV_VIDEO]                 │
│  [JSON_ARTICLE][JSON_BANGUMI][JSON_VIDEO]              │
│  [TXT_ARTICLE] [TXT_BANGUMI] [TXT_VIDEO]               │
│  [XLSX ← 推荐！3 sheet]                               │
│  ┌─ 类型 / ID / 标题 / 作者 / 数据 / 链接 ──────┐     │
│  │ [视频] BV1xxx ...                              │     │
│  │ [专栏] cv12345 ...                             │     │
│  │ [番剧] ss67890 ...                             │     │
│  └─────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────┘
```

Web 后端用 **SSE (Server-Sent Events)** 实时推进度，前端零框架（纯 HTML + CSS + JS），启动就能用。

如果要局域网共享给同事看（只读、本地无敏感数据时）：

```bash
python run_web.py --host 0.0.0.0 --port 5050
```

⚠ **生产环境请勿用 Flask 自带 dev server**，加并发建议换 `gunicorn -w 4 'web.app:app'`。

### v3.0+ 按 UP 主抓取（`/author` 页面）

> 启动 Web 后访问 `http://127.0.0.1:5050/author`，或者点首页顶部导航的「按 UP 主抓取」。

页面长这样（ASCII 示意）：

```
┌──────────────────────────────────────────────────────────────────┐
│  📋 按 UP 主抓取视频（v3.0+ UAPI 集成）                          │
├──────────────────────────────────────────────────────────────────┤
│  ⚙ 数据源设置  自主 WBI / uapis.cn（访客或登录）/ 旧端点            │
│    数据源 [uapis.cn ▼]  API Key [*********]  请求间隔 [250]ms     │
│    ⏱ 推荐翻页间隔：250ms（4 QPS = 访客档）                         │
│    ⚠ 风险提示：数据过第三方服务器（UID 暴露）· 访客按 IP 算额度... │
├──────────────────────────────────────────────────────────────────┤
│  ① 阶段 1：拉取 UP 主视频列表                                    │
│    ┌────────────────────────────────────────────────┐            │
│    │ 53456                                           │            │
│    │ https://space.bilibili.com/483307278             │            │
│    │ https://b23.tv/3VlfaxC                          │            │
│    └────────────────────────────────────────────────┘            │
│    [近 7 天] [近 30 天] [近 90 天] [📅 全部时间]                  │
│    [拉取列表 → 导出 CSV]                                          │
│    → UP 53456：261 条（来源：uapis.cn）→ author_53456_xxx.csv   │
├──────────────────────────────────────────────────────────────────┤
│  ② 阶段 2：从 CSV 抓取视频详情                                    │
│    [今天] author_53456_xxx.csv (1.2 KB)                          │
│    [昨天] author_483307278_xxx.csv (3.4 KB)                       │
│    [✓ 全选] [✗ 全不选] [🗑 删除选中] [📂 在文件管理器中打开]     │
│    [抓取详情 → 导出 XLSX]  → output/xlsx/author_detail_53456.xlsx│
├──────────────────────────────────────────────────────────────────┤
│  ③ UP 主主页信息批量抓取（v3.0.6+ · uapis.cn 专属）             │
│    ┌────────────────────────────────────────────────┐            │
│    │ 53456                                            │            │
│    │ https://space.bilibili.com/483307278              │            │
│    └────────────────────────────────────────────────┘            │
│    [批量抓取主页 → 导出 CSV + XLSX]                              │
│    → profiles_xxx.csv + profiles_xxx.xlsx                         │
└──────────────────────────────────────────────────────────────────┘
```

**关键端点**（v3.0+ 实现的 7 个）：

| 端点 | 方法 | 用途 |
|---|---|---|
| `/api/author/providers` | GET | 返回 3 个 provider 元信息（QPS / 积分 / 风险 / **推荐间隔**）|
| `/api/author/list` | POST | 阶段 1：拉列表 + 导出 CSV（接 provider / key / days / **interval_ms**）|
| `/api/author/profile` | POST | 阶段 3：批量抓 UP 主主页信息（v3.0.6+）|
| `/api/author/detail` | POST | 阶段 2（单文件）：异步抓详情 + 实时进度（v3.0.4+）|
| `/api/author/detail/batch` | POST | 阶段 2（批量）：多 CSV 并行抓详情（v3.0.7+）|
| `/api/author/detail/progress` | GET | 阶段 2 进度轮询（兼容单/批量）|
| `/api/open-output-folder` | POST | 在文件管理器中打开 + 高亮（v3.0.7+ 智能定位）|

---

## 🧪  测试

### 单元测试（无需联网）

```bash
python -m unittest discover tests -v
```

**323 个测试**，覆盖：
- `tests/test_parser.py`（25 个）：纯 AV / av 前缀 / BV / 完整 URL / 短链 / 混合输入 / 多行 / 中文混入 / URL 内嵌 av 数字不重复 / 顺序保持 / 去重 / 科学记数法 / 6-16 位裸数字边界 / 版权清单回归 / 33 个真实 AV 号回归 / **专栏/番剧/opus URL 解析**（v2.8+ 13 个新增）
- `tests/test_cache.py`（23 个）：parse_duration / 字段差异化过期 / 失败状态永远新鲜 / 缺失 fetched_at 视为过期 / 持久化 / 损坏 cache 恢复 / **跨 AV/BV 双索引 + 自动升级**
- `tests/test_exporter.py`（26 个）：CSV/JSON/TXT/XLSX 4 种格式 / dedupe 各种边界 / 先过滤后去重 / **3 类型混合导出 + 3 sheet xlsx**（v2.8+ 13 个新增）
- `tests/test_article_bangumi.py`（18 个，v2.8 新增）：通用 Cache 对 ArticleInfo/BangumiInfo 的支持 / 双索引（ss+ep）/ 持久化 / 旧 API 兼容
- `tests/test_wbi.py`（25 个，v2.9.1 新增）：WBI 签名 / 缓存 / enc_wbi / 32 个测试点
- `tests/test_author.py`（v2.9.1+）：`AuthorVideoFetcher` 抓 UP 主投稿
- `tests/test_author_list.py` / `tests/test_author_detail.py`（v2.9.0+）：按 UP 主列表 / 详情抓取
- `tests/test_uapi_*.py`（3 个，v2.10.0+）：uapis.cn / self-wbi / chain 降级 56 测试
- **`tests/test_uapi_interval.py`（25 个，v3.0.9 新增）**：provider 翻页 sleep 行为 / 4 个 provider 默认值 / interval=0 / 负数修正 / 翻页次数
- **`tests/test_web_interval.py`（11 个，v3.0.9 新增）**：4 个 web 端点透传 interval_ms / provider 元信息 / 边界值

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
│   ├── __init__.py           # 版本号 v3.0.9-alpha
│   ├── models.py             # 数据模型（dataclass）
│   ├── parser.py             # 多输入解析
│   ├── fetcher.py            # B 站 API 客户端
│   ├── cache.py              # JSON 缓存 + 原子写入
│   ├── exporter.py           # xlsx / csv / json / txt
│   ├── wbi.py                # v2.9.1+ WBI 签名（25 测试）
│   ├── author.py             # v2.9.1+ AuthorVideoFetcher（WBI 主端点）
│   ├── author_list.py        # v2.9.0+ 按 UP 主列表抓取 + CSV 导出（v3.0+ archives= 参数）
│   ├── author_detail.py      # v2.9.0+ 按 UP 主详情抓取 + XLSX 导出（v3.0.1+ 默认 output/xlsx/）
│   └── uapi/                 # v2.10.0+ UAPI 抽象层
│       ├── __init__.py       # 导出 ArchiveProvider/AuthorArchiveChain
│       ├── base.py           # 5 类异常 + ArchiveProvider 基类（v3.0.9+ interval_ms）
│       ├── uapis_cn.py       # uapis.cn 5 端点（访客 4 QPS / 登录 7 QPS）
│       ├── self_wbi.py       # 适配 AuthorVideoFetcher
│       ├── self_legacy.py    # 旧端点（最末位降级）
│       └── chain.py          # 降级链（v3.0.5+ 完整性评估 + v3.0.9+ interval 透传）
├── web/                      # Web 应用
│   ├── app.py                # Flask + SSE + v3.0+ 7 个 author 端点
│   ├── templates/
│   │   ├── index.html        # 视频/专栏/番剧主页
│   │   └── author.html       # v3.0+ 按 UP 主抓取页
│   └── static/
│       ├── {style.css, app.js, author.js}  # author.js v3.0+ 数据源卡 / 进度轮询
├── tests/                    # 323 个测试
│   ├── test_parser.py
│   ├── test_cache.py
│   ├── test_exporter.py
│   ├── test_article_bangumi.py
│   ├── test_wbi.py           # v2.9.1+
│   ├── test_author.py        # v2.9.1+
│   ├── test_author_list.py
│   ├── test_author_detail.py
│   ├── test_uapi_*.py        # v2.10.0+ UAPI 抽象层（56 测试）
│   ├── test_uapi_interval.py # v3.0.9+ 翻页间隔（25 测试）
│   ├── test_web_interval.py  # v3.0.9+ web 端点（11 测试）
│   ├── test_uapi_v310.py     # v3.1.0+ disableCache + Q32 + usage（23 测试）
│   └── analyze_xlsx.py       # v3.1.0+ XLSX 整合分析（1382 条 → 互动率/年度分布/爆款）
├── tools/                    # v3.1.0+ 独立工具
│   └── README.md             # 工具说明
├── data/                     # 缓存（自动生成，gitignore）
│   ├── cache.json            # 视频
│   ├── cache_article.json    # 专栏
│   ├── cache_bangumi.json    # 番剧
│   └── wbi_keys.json         # v2.9.1+ WBI 签名 key（12h 自动刷新）
├── output/                   # 导出目录（自动生成，gitignore）
│   ├── *.csv / *.json / *.txt / *.xlsx
│   └── xlsx/                 # v3.0.1+ 详情 XLSX 单独目录
├── cli.py                    # CLI 入口
├── run_web.py                # Web 启动
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

---

## ⚠️  已知限制

### 按 ID 抓（v2.x）

- **频率限制**：连续大量请求可能触发 B 站风控。`--delay` 默认 0.6s 比较保守；如果跑 100+ 个视频可以调到 1.0s 稳一点
- **短链解析**：b23.tv 短链需要先发一次 HEAD 请求才能展开，会多一次网络往返
- **专栏正文**：抓专栏正文（`/x/article/detail/content`）需要登录 cookie，本版本**只抓公开字段**（标题/作者/阅读量/点赞/收藏/摘要/封面）。如需正文请加 SESSDATA cookie（v2.8.1+ 计划）
- **番剧单集 vs 整季**：本版本统一返回**整季的元数据**（title/cover/desc/评分/总集数）。单集 ID（ep）会先转 season_id 再查
- **失效视频/专栏/番剧**：B 站 API 只告诉你"不可见"，不会告诉你为什么；想要"原始数据"只能从你自己之前的归档/截图里手动补
- **登录态**：当前是匿名访问，部分"仅会员可见"视频即使存在也拿不到——这种也归到 `not_found`
- **作者改名**：B 站 up 主**可以改昵称**（改 mid 不变），所以同一作者的 name 可能随时间变化。**做作者历史数据分析请用 `author_mid` 而不是 `author_name` 关联**
- **v2.8.1+ opus 边界**：
  - **被转发的内容**：opus API 返回 `item=null, fallback={type:2, id: 原动态id}`。本版本会**降级到 web HTML 拿 `<title>`**（status=ok + error 字段标记降级原因）
  - **仅粉丝可见**：`ArticleInfo.is_only_fans=True` 时 error 字段会写"up 主设置仅粉丝可见（匿名访问看不到完整内容）"——这是 B 站权限限制，不是工具 bug

### 按 UP 主抓（v3.0+）

- **uapis.cn 数据完整性**（按 UP 主 + 时间窗口变，**不是硬限制**）：
  - 活跃 UP 主（1751577265）：~900/983（91.5%）
  - 老 UP 主（53456）：~140-160/262（53-61%）
  - 2019 年前数据视 UP 主而定（Warma 缺 2015-2018）
  - **不是 150 条硬限制**——是"动态"，4 QPS 间隔够慢时上限 ≈ 1000；太快被限速
- **B 站风控（self-wbi / self-legacy）**：当前网络环境下 self-wbi 经常被 412 / -799 屏蔽。**默认走 uapis 降级链**
- **uapis 访客额度按 IP 算**：切网络会重置；多人共用 IP 可能争抢
- **v3.0.9 翻页间隔是全局值**：不能分端点或分 UP 主。429 没有自动退避（v3.1+ 候选）
- **没有 429 自动退避**：用户需手动调大 interval（FAQ Q14 推荐 0.5s/1s/2s/4s 指数退避）
- **CSV 大小限制**：阶段 2 单文件按行读（不一次性加载），但 5000+ 行的 CSV 仍可能慢
- **⚠ 生产环境不建议直接用访客额度**（uapis FAQ Q40 原文）：1500 积分/月容易耗尽 + 4 QPS 容易触发 429 + 切网络会断档 + 没法追问题账号。**生产环境至少用登录账号（3500 积分/月 + 7 QPS）**

#### ⚠ 截断 + 服务端缓存陷阱（v3.0.9+ 诊断经验）

> **2026-08-21 用户现场确认**：uapis.cn 在请求被**中途截断**时，会让**下一次相同参数的请求**拿到**上次截断时的不完整缓存结果**。**实测症状**："测不出全量" + "全量数据与 25 年一模一样"——其实是拿到的**被截断的冻结版本**。

**典型场景**：
1. 浏览器关掉、用户点停、timeout、网络抖动 → 当前请求被截断
2. 服务端（uapis）请求**没收到完整响应**，但**已经写入了缓存**（15 分钟 TTL）
3. 用户立即用**同样的参数**重试 → uapis 直接返回**上次的（不完整）缓存**
4. 结果：拿到的数据**不是新的全量**，而是**上次的残缺版本**，且**看起来"成功"**

**诊断信号**：
- 同一个 UP 主反复跑，每次拿到的数据量**不一致**（如 140 → 165 → 158）
- 反复重试时**响应很快**（命中缓存）但**数据没变多**
- 数据有"时间分块"特征（如老 UP 主缺 2015-2018，每次都缺同几个月）
- 关掉网络 15 分钟后再试，结果变了

**FAQ 引用（Q12 关闭缓存）**：
> TypeScript SDK 用 `disableCache: true`；非 SDK 在 URL 加 `_t=Date.now()` 时间戳绕过。

**目前的工作绕**（v3.0.9）：
- **等待 15 分钟**让 uapis 缓存自然过期（最慢但最稳）
- **修改任一参数**（如把 days=7 改成 days=8）让缓存键变了
- **v3.1+ 候选**：实现 `disable_cache=true` 参数，给所有 uapis URL 加 `_t=<timestamp>` 后缀强制绕过缓存

**为什么 interval_ms 解决不了这个**：interval 控制**翻页间隔**避开 429；截断是**单次请求**的连接中断，跟间隔无关。

**✅ v3.1.0 修复验证（2026-08-22 真实数据）**：
4 个 UP 主 XLSX 抓取对比（UP 主姓名已匿名化，需 UID 查 B 站）：

| 公开标签 | UID | v3.1.0 前覆盖率 | v3.1.0 disableCache 后覆盖率 | 时间跨度 |
|---|---|---|---|---|
| UP-A | 53456 | — | **261/262 = 99.6%** | 2015-12 ~ 2026-08（10.6 年）|
| UP-D | 1751577265 | 780/983 = 79.3% (v3.1.0 前抓) | — | 2024-03 ~ 2026-08 |

**关键对比**：UP-A 用 v3.1.0 disableCache 抓出 **99.6%** 全量，UP-D 没开 disableCache 抓出 79.3%（且缺 2024-03 之前的老视频——正是 v3.1.0 修复的"截断陷阱"症状）。

> **UP 主姓名在公开 README 中已匿名化**（v3.1.1 隐私设计）：脚本内部维护映射表，公开版只显示 UID。需要回查时按 UID 访问 B 站即可。

---

## 🗺  后续计划（AI工具的建议，这边我可能会维护的）

### v3.1+ 候选（v3.0+ 已实装的）
- [ ] **429 自动退避**（uapis FAQ Q14）：触发指数退避 0.5s/1s/2s/4s
- [ ] **按 UP 主维度动态调间隔**：活跃 UP 主慢 / 老 UP 主快
- [ ] **interval_ms 服务端持久化**：多端共享
- [ ] **智能推荐**：根据"过去 10 分钟 429 次数"自动调大 interval

### v2.x 计划
- [ ] 加 `seeduuid` cookie 支持（绕过部分风控 + 看会员视频）
- [ ] 加 `--from-xlsx` 选项，从现有表格的 BV 列直接读输入
- [ ] 加 `--merge` 选项，把新抓的字段填回原 xlsx 的"真实"列，保留"原始"列做对比
- [ ] 加 简易 Dockerfile
- [ ] 失败视频尝试从 Wayback Machine 拉历史快照（这是个独立大 feature，先列着）

---

## 📝  版本历史

### v3.1.0-alpha（2026-08-22）—— **修复截断陷阱 + 实时额度查询**

**核心新功能 / 修复**：

- **🆕 A. `disableCache` 参数**（uapis FAQ Q12 修复"测不出全量"）：
  - TypeScript SDK 用 `disableCache: true`（驼峰），**本项目用 URL `_t=<timestamp>` 戳绕过**（非 SDK 推荐方式）
  - 4 个 web 端点全部接受 `disable_cache` 参数
  - 前端"数据源设置"卡加 🔓 复选框
  - localStorage key: `bilibili_tool:uapi_disable_cache`
  - 解决"截断 → 下次请求拿到上次残缺缓存"的隐蔽 bug

- **🆕 B. 错误响应 4 种结构兼容**（FAQ Q32）：
  - `_request()` 现在读 4 种结构：标准 `code+message+details` / 简化 `error+details` / 积分不足 `error+docs` / 限流类 `code+limit`
  - `UapiError` 增强：`details` / `docs` 字段
  - 区分 18 种错误码（Q33 错误码表）：`INVALID_PARAMETER` / `UNAUTHORIZED` / `INSUFFICIENT_CREDITS` / `CORS_FORBIDDEN` / `VISITOR_MONTHLY_QUOTA_EXHAUSTED` / `IP not allowed` 等
  - 特殊处理：`VISITOR_MONTHLY_QUOTA_EXHAUSTED` 不触发降级链（再换 provider 也无意义）

- **🆕 D. 实时额度查询 UI**（FAQ Q26）：
  - 新端点 `/api/author/usage` 调 `GET https://uapis.cn/api/v1/status/usage`（**免费端点，0 积分**）
  - 前端"数据源设置"卡加 📊 按钮 + 卡片显示访客/资源包/QPS
  - 包含 `original response` 折叠（识别未字段）

**关键文档修正**：
- uapis 积分半价：**"半价向下取整"**（B 站 4 积分 → 2 积分），不是"半价 0 积分"
- uapis 命名澄清：TypeScript SDK 用驼峰 `disableCache`（**不是** `disable_cache`）
- 积分档位细分：基础 1 积分 / 数据查询 2 / AI 服务 4（**不只是"B 站 5 端点 4 积分"**）
- 新增 Q40 生产警示："**不建议生产环境直接用访客额度**"（1500/月容易耗尽 + 4 QPS 容易触发 429 + 切网络断档）

**测试**：23 个新测试（`test_uapi_v310.py`）—— 全量 346/346 通过

**8 个新 HTTP 状态码支持**：401 / 402 / 403 / 413 / 429（细分 quota_exhausted）/ 500 / 502 / 503 / 504

### v3.0.9-alpha（2026-08-21）—— **请求间隔自定义**

**核心新功能**：
- **🆕 翻页间隔自定义**：在「数据源设置」卡片手动设置毫秒值，全局生效（4 个 web 端点 + 3 个 provider）
- **默认 250ms**（uapis 访客 4 QPS = 1000/4）
- **默认分档**：
  - uapis.cn: 250ms（4 QPS 访客档）
  - self-wbi: 300ms（保留旧 `time.sleep(0.3)` 行为）
  - self-legacy: 250ms（与 uapis 对齐）
- **provider 元信息加 `recommended_interval_ms`**：`/api/author/providers` 返回的元信息含推荐值，切 provider 时前端展示
- **响应回显 interval_ms**：每个端点响应都带 `interval_ms`，前端可显示"用了 X ms"

**实施 4 层透传**：
1. 前端 localStorage `bilibili_tool:uapi_interval_ms`
2. Web 4 端点接 `interval_ms`（默认 250，负数 clamp 到 0）
3. Provider 层 `ArchiveProvider.__init__` 统一加 + `_sleep_interval()` 方法
4. 翻页点 `uapis_cn` / `self_legacy` / `AuthorVideoFetcher._iter_author_archives` 在 `pn += 1` 后调用

**文档依据**：uapis FAQ Q13（QPS 表）/ Q14（429 退避 0.5/1/2/4s）/ Q15（≥1500ms 保守）

**测试**：25 个 `test_uapi_interval.py` + 11 个 `test_web_interval.py` = **36 新测试**，全量 **323/323** 通过

**已知限制**（v3.1+ 候选）：
- 没有 429 自动退避（用户需手动调大）
- 不能按 UP 主维度动态调整
- interval_ms 是全局值，不能分端点

### v3.0.8-alpha（2026-08-21）—— **另存 + 智能文件管理**

- **🆕 另存按钮**（v3.0.8+）：用 File System Access API 弹文件选择器，**不弹浏览器"另存为"**（Chrome/Edge 86+）
- **🆕 智能定位文件管理器**（v3.0.8+）：`/api/open-output-folder` 按文件类型选目录（CSV → `output/`，XLSX → `output/xlsx/`）+ 高亮文件
- **修正 150 条误判**：uapis "150 条限制" 实际是"动态"（按 UP 主 + 时间窗口），不是硬限制。**hibiki 900/983 (91.5%)** 是上限

### v3.0.7-alpha（2026-08-21）—— **阶段 2 批量 + 智能文件管理**

- **🆕 阶段 2 批量抓取**（`/api/author/detail/batch`）：多选 CSV 并行抓，每个 CSV 一个 XLSX
- **🆕 实时进度兼容批量**：`/api/author/detail/progress` 兼容单/批量模式（`sub_total` / `sub_done` / `xlsx_paths` / `errors`）
- **🆕 在文件管理器中打开**（v3.0.7+）：Windows / macOS / Linux 三平台支持
- **🆕 文件列表分组**：阶段 2 列表按 mtime 分组（今天 / 昨天 / 本周 / 更早）

### v3.0.6-alpha（2026-08-21）—— **UP 主主页信息批量抓取**

- **🆕 主页信息端点**（`/api/author/profile`）：批量抓多个 UP 主的昵称/等级/粉丝数/投稿数
- **🆕 双格式导出**：CSV（`output/profiles_*.csv`）+ XLSX（`output/xlsx/profiles_*.xlsx`）
- **🆕 uapis.cn userinfo 端点**：补全 B 站官方端点没暴露的字段

### v3.0.5-alpha（2026-08-21）—— **数据完整性诊断**

- **🆕 完整性评估**（`AuthorArchiveChain._assess_completeness`）：实际抓到 N 条 vs provider 报告的 total
- **🆕 3 档提示**：`ok`（≥90%）/ `partial`（< 50%）/ `unknown`（无 total）
- **🆕 元信息字段**：`_completeness` / `_chain` / `_provider_total` / `_actual_count` 写到 archive 第 1 条

### v3.0.4-alpha（2026-08-21）—— **阶段 2 实时进度**

- **🆕 异步抓详情**（`/api/author/detail`）：立即返回 `job_id`，后台线程跑抓取
- **🆕 进度轮询**（`/api/author/detail/progress`）：前端 0.6s 轮询，看得见在抓哪个

### v3.0.3-alpha（2026-08-21）—— **日期快捷 + unlimited 修复**

- **🆕 日期快捷按钮**（近 7/30/90 天 / 全部时间）
- **修复 unlimited bug**：`unlimited=true` 之前被默认 7 天覆盖

### v3.0.2-alpha（2026-08-21）—— **批量删除**

- **🆕 通配符批量删除**（`/api/author/files/delete-batch`）：`*` / `?` / `[seq]` 一次清多个测试残留

### v3.0.1-alpha（2026-08-21）—— **XLSX 单独目录 + 单文件删除**

- **🆕 XLSX 单独目录**：阶段 2 XLSX 默认存 `output/xlsx/`（与 CSV 分离）
- **🆕 单文件删除**（`/api/author/files/<path:filename>` DELETE）
- **修复**：作者详情 GBK emoji 打印 bug（用 `OK` / `FAIL` 替代 `✓` / `✗`）

### v3.0.0-alpha（2026-08-21）—— **Web 端集成（UAPI + 数据源切换）**

- **🆕 `/api/author/providers`** 端点：返回 3 个 provider 元信息（QPS / 积分 / 风险）
- **🆕 `/api/author/list`** 端点：阶段 1 拉列表 + 导出 CSV（接 provider / key / days）
- **🆕 4 套数据源**：
  - uapis.cn（默认）：访客 4 QPS / 登录 7 QPS
  - self-wbi：自主 WBI 签名（v2.9.1+）
  - self-legacy：旧端点（最末位降级）
  - 自动降级链：限流时自动切到下一个
- **🆕 前端「⚙ 数据源设置」卡片**：provider 下拉 + API key 输入 + localStorage + 风险卡
- **🆕 API key 只存 localStorage**（不上传服务器）
- **库改造**：`AuthorListExporter.export()` 新增 `archives=` 参数（与 chain 配合）

### v2.10.0-alpha（2026-08-21）—— **UAPI 抽象层**

- **🆕 6 个新文件**：`bilibili_tool/uapi/{base, uapis_cn, self_wbi, self_legacy, chain, __init__}.py`
- **🆕 56 个 UAPI 单元测试**（mock 模式，零网络）
- **🆕 5 类异常**：`UapiRateLimitError` / `UapiAuthError` / `UapiNotFoundError` / `UapiTimeoutError` / `UapiError`
- **🆕 降级链原则**：只有限流触发降级，其他错误直接抛
- **🆕 访客模式**：uapis.cn 不传 key 也能用（1500 积分/月，4 QPS）

### v2.9.1（2026-08-21）—— **WBI 签名 + UP 主空间端点**

- **🆕 WBI 签名**（`bilibili_tool/wbi.py`）：B 站 2023-03 起的官方接口，需要 WBI 鉴权
- **🆕 `/x/space/wbi/arc/search`** 端点：替代已 404 的 `/x/polymer/web-space/home/seek_arc`
- **🆕 WBI key 缓存**（`data/wbi_keys.json`）：12h 自动刷新
- **🆕 25 个 WBI 测试**（`test_wbi.py`）：签名 / 缓存 / enc_wbi

### v2.9.0（2026-08-21）—— **按 UP 主抓取（CLI 起步）**

- **🆕 `AuthorVideoFetcher`**：按 UP 主 UID 抓其投稿视频列表
- **🆕 `AuthorListExporter`**：列表 → CSV
- **🆕 `AuthorDetailExporter`**：CSV → XLSX（每条视频详情）
- **🆕 两阶段工作流**（CLI）：阶段 1 拉列表 → CSV → 阶段 2 抓详情 → XLSX

### v2.8.0（2026-08-21）—— **专栏 + 番剧支持**

**核心新功能**：
- **新增**专栏（article）抓取：识别 `bilibili.com/read/cv{数字}`（旧版）和 `bilibili.com/opus/{数字}`（B 站 2024 改版后的新版 URL）两种 URL
- **新增**番剧（bangumi）抓取：识别 `bilibili.com/bangumi/play/ss{数字}`（整季）和 `.../ep{数字}`（单集）两种 URL。`ep` 形式会自动转 `season_id` 再查
- **新增**b23 短链自动分类：解析后根据 302 目标 URL 路径自动归类到 `bv` / `article` / `bangumi_ss` / `bangumi_ep` 之一
- **修复**B 站短链跳转 `m.bilibili.com`（移动版域名）不识别的问题——所有 URL 正则都改为支持任意子域名

**架构升级**：
- **`Cache` 类通用化**：保持向后兼容（默认 VideoInfo），但可通过 `record_class + key_func` 注入支持任何 dataclass
- **3 类独立 cache 文件**：`data/cache.json`（视频）+ `cache_article.json`（专栏）+ `cache_bangumi.json`（番剧），各自动态字段 1h 过期，静态 + 失败状态永远缓存
- **导出器支持多类型**：
  - xlsx 单文件 3 个 sheet（视频/专栏/番剧）
  - csv/json/txt 拆 3 个独立文件（`{base}_video.csv` / `{base}_article.csv` / `{base}_bangumi.csv`）
  - 旧 API（`export_all(videos)`）完全兼容
- **CLI 新增**：
  - `--fetch-articles` / `--no-fetch-articles`（默认开）
  - `--fetch-bangumi` / `--no-fetch-bangumi`（默认开）
- **Web UI 新增**：
  - 「抓取专栏」checkbox（默认勾选）
  - 「抓取番剧」checkbox（默认勾选）
  - 结果表格加「类型」列（视频/专栏/番剧）

**API 端点**：
- 视频：`/x/web-interface/view`（不变）
- 专栏：`/x/article/view?id={cv_id}`（opus_id 数字直接当 cv_id 用）
- 番剧：`/pgc/view/pc/season?season_id={ss_id}` 或 `?ep_id={ep_id}`

**测试**：74 → **118**（+44 个新测试），全部通过

**新数据模型**：
- `ArticleInfo`：cv_id / title / author_mid / author_name / view / like / favorite / coin / share / reply / words / ctime / pubtime / summary / banner / url / status / ...
- `BangumiInfo`：season_id / ep_id / title / alias / type_name / rating_score / rating_count / total_ep / status_text / publish_date / view / favorite / coins / like / share / reply / danmaku / desc / cover / url / status / ...

**已知未做（v2.8.1+ 计划）**：
- 专栏正文（需 cookie）
- b23 短链并发展开
- Web UI 实时显示展开过程

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
- **新增**：`--allow-bare-numbers` CLI 开关 / Web UI checkbox，需要时手动开启（识别 6-16 位裸数字）
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

- 原 `bilibili_tool.py` 和 `Python批量获取B站视频数据脚本.py` 的作者（都是映月/我自己，这边先前利用AI工具写脚本留下的相关原代码）
- 对于上海某高校事件 4K 修复版和hibiki相关视频的采集数据——这两份测试数据帮我验证了 80%+ 失效场景下脚本不会崩
- B 站公开 API：
  - `api.bilibili.com/x/web-interface/view`（视频）
  - `api.bilibili.com/x/article/view`（专栏）
  - `api.bilibili.com/pgc/view/pc/season`（番剧）

---

## 📊 数据洞察附录（v3.1.0 实测 · 1382 条视频 · 4 个 UP 主）

> **v3.1.1 隐私设计**：UP 主姓名全部匿名化为 `UP-A/B/C/D`（按 UID 升序）。脚本内部维护真实姓名映射，公开版只显示 UID。详见 `tests/analyze_xlsx.py`。

### 数据规模

| 公开标签 | UID | 抓取条数 | 覆盖率 | 时间跨度 | 类型 |
|---|---|---|---|---|---|
| **UP-A** | 53456 | **261** | **99.6% (真实 262)** | 2015-12 ~ 2026-08（**10.6 年**）| 活跃多年 |
| UP-B | 131692216 | 1 | — | 2026-08 | 极少投稿 |
| UP-C | 399959326 | 340 | — | 2024-10 ~ 2026-08 | 新晋 1.9 年 |
| UP-D | 1751577265 | 780 | 79.3% (真实 983) | 2024-03 ~ 2026-08 | v3.1.0 前抓 |
| **合计** | — | **1382** | — | — | — |

**关键观察**：
- **UP-A 全量覆盖率 99.6%**（v3.1.0 disableCache 修复后）—— 证明截断陷阱已修复
- **UP-D 时间跨度仅 2.5 年**（2024-03 之前的数据丢了）—— **正是 v3.1.0 修复的症状**（截断 → 15 分钟缓存冻住 → 重试拿到陈旧版本）
- **全量 100% 有完整数据**（无空标题 / 无抓取失败）

### 年度分布（4 个 UP 主 × 12 年）

| UP | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| UP-A | 3 | 23 | 46 | 21 | **53** | 32 | 18 | 18 | 15 | 12 | 12 | 8 | 261 |
| UP-B | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| UP-C | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | **193** | 47 | 340 |
| UP-D | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 203 | **392** | 185 | 780 |

**亮点**：
- **UP-A 2019 年达到创作高峰**（53 条），2020 后逐年下降 50%——从"高产"转型为"少而精"
- **UP-C / UP-D 都是 2024 后才活跃**——可能跟"UP-D 2024 前数据被截断陷阱吃掉"有关
- **2026 年数据**（截至 8-22）UP-D 已有 185 条——可能追平 UP-A 的 2024 整年

### 互动率（赞/播放）

| UP | 总播放 | 赞/播放 | 币/播放 | 收/播放 | 解读 |
|---|---:|---:|---:|---:|---|
| UP-A | 5.96 亿 | **6.13%** | 2.79% | 2.08% | 行业高水平（爆款多）|
| UP-B | 14.8 万 | 9.81% | 2.40% | 2.78% | 数据少但单条粘性高 |
| UP-C | 266 万 | 3.88% | 0.21% | 0.38% | 新晋 UP，互动偏低 |
| **UP-D** | 3594 万 | **15.13%** | 0.85% | 3.01% | **粉丝粘性极强**（播放低但互动高）|

**反直觉发现**：UP-D 播放量只有 UP-A 的 1/17，但互动率（赞/播放）是 **UP-A 的 2.5 倍**。说明 UP-D 的受众更铁粉（粘性高），UP-A 走的是"大众爆款"路线（多但散）。

### 爆款视频 TOP 5（按播放量）

1. **UP-A · 2019-10-05** · `只需要3秒，你就会发现不对劲的歌……` · **1947 万播放** · 81 万赞 · 时长 137 秒
2. **UP-A · 2019-07-27** · `我家里有蜘蛛！！！【原创曲】` · 1440 万播放 · 75 万赞 · 145 秒
3. **UP-A · 2024-01-23** · `我制作了免费的养宠物游戏！` · 1398 万播放 · 47 万赞 · **1399 秒**（23 分钟）
4. **UP-A · 2022-02-13** · `300万关注啦！来纪念一下吧` · 893 万播放 · 83 万赞 · 359 秒
5. **UP-A · 2026-02-08** · `一个女孩擅自睡前偷看《山海经》` · 862 万播放 · 28 万赞 · 300 秒

**全 TOP 10 都是 UP-A**——Warma 是真的"中视频爆款制造机"。

### 有趣发现

- **最长视频**：UP-A `【双影奇境】实况` 12 小时 23 分（44612 秒 = 7.8 千万秒 = 12.4 小时）
- **短小精悍**（< 2 分钟 + 播放 > 10 万）：**78 条**，几乎全在 UP-D（如"叫一声听听？" 19 秒 = 50 万播放）
- **最高「币/赞」比**（粉丝付费意愿）：UP-A 血小板 1.47（10 万赞 = 17.8 万币），远高于行业 0.1
- **互动"双峰"**：UP-A 走播放量（量级大但分散），UP-D 走互动率（量级小但粘性高）

### v3.1.0 修复效果对比（最关键）

| UP | 修复前（v3.0.9） | 修复后（v3.1.0） |
|---|---|---|
| UP-A | — | **261/262 = 99.6%** |
| UP-D | 780/983 = 79.3% | — |

**UP-A 99.6% 全量 vs UP-D 79.3% 部分** = disableCache 真有效。UP-D 缺 2024-03 之前的 203 条数据 = 截断陷阱的"陈旧缓存"症状。**勾上 🔓 后，UP-D 重抓预期能拿回完整 ~983 条。**

## ⚠️ 重要声明：

本工具仅供个人学习与研究使用。
严禁用于任何形式的商业目的、大规模数据采集或干扰 bilibili.com 正常运营的行为。
使用者需自行承担因不当使用造成的风险，包括但不限于账号封禁、法律纠纷等。

---

## 📄  License

MIT — 详见 [LICENSE](LICENSE)。

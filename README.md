# ai-daily-collector —— AI 资讯采集 + Windows 计划任务

[![tests](https://github.com/gangrenboqe/ai-daily-collector/actions/workflows/test.yml/badge.svg)](https://github.com/gangrenboqe/ai-daily-collector/actions/workflows/test.yml)

> 一句话：**抓 6 个 RSS 源做成 AI 日报的原材料清单，用 PowerShell 注册成 Windows 计划任务自动跑；
> 零第三方依赖（标准库解析），单个源挂掉不影响整轮，还会把「哪个源失败、为什么」原样写进产出。**

---

## 三步跑起来（不需要联网、不需要任何 key）

```bash
git clone https://github.com/gangrenboqe/ai-daily-collector.git
cd ai-daily-collector
python demo.py
# → 离线生成一份日报样例：内置合成数据（8 条）→ 解析 → 关键词筛选（命中 6 / 过滤 2）→ 日报全文
#   真实运行输出样例见 docs/demo_output.txt
```

Python 3.9+，零第三方依赖。想跑**真实的联网采集**：`python ai_daily_scraper.py`（输出到 `daily/` 目录）。
陌生人复验记录见 [docs/STRANGER_REVIEW.md](docs/STRANGER_REVIEW.md)。

---

## 先说清楚它到什么程度（如实写）

**已验证：1 次完整运行**（采集 + 生成 Markdown 报告 + PowerShell 菜单脚本的注册/立即运行/查看状态流程）。
它不是"稳定运行 N 天的自动化日报系统"——没跑过那么多轮，就不那么写。

为什么还要放在这里：它练的是 **Windows 计划任务（Task Scheduler）的全套操作**
和**网络抓取的多级降级**，这两件事应届生基本没碰过，而它们正好是
**IT 支持 / 桌面运维 / 数字化专员**的日常工作内容。

---

## 两个文件

| 文件 | 干什么 |
|---|---|
| `ai_daily_scraper.py` | 抓 10 个 RSS 源 → 按关键词筛选 AI 相关 → 生成 Markdown 日报 |
| `setup_scheduler.ps1` | 交互式菜单：创建 / 删除 / 立即运行 / 测试 / 查看 Windows 计划任务 |

---

## 怎么用

```bash
python ai_daily_scraper.py                 # 联网抓 10 个 RSS 源，输出到脚本同级的 daily/ 目录
python ai_daily_scraper.py out/2026-10-10.md   # 指定输出文件
```

> 零第三方依赖，克隆下来直接跑，不需要 pip install（v1 的 `requirements.txt` 是遗留说明，见下方「依赖」一节）。

```powershell
# 以管理员身份打开 PowerShell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_scheduler.ps1
```

菜单：
```
1. 创建计划任务（每日 9:00 运行）       → Register-ScheduledTask
2. 删除计划任务                        → Unregister-ScheduledTask
3. 立即运行一次                        → Start-ScheduledTask
4. 测试脚本                            → 直接跑一次并列出最近产物
5. 查看任务信息                        → Get-ScheduledTask + Get-ScheduledTaskInfo
                                          （含最后运行结果 / 最后运行时间 / 下次运行时间）
```

所有路径都是**相对于脚本自身位置**的（`Split-Path -Parent $MyInvocation.MyCommand.Path`），
clone 到任何目录都能跑，没有写死的绝对路径。

---

## 迭代记录

> 这个仓库不是一次写完的。下面是真实发生过的几次「发现不对 → 改」的记录，
> 保留它们是因为：**一次失败后的归因，比十次顺利的提交更说明问题。**

### 日报静默变空：不报错、不崩溃，就是没内容

一次检查时发现，某天的日报生成出来是**空的**——
程序没抛异常、没崩、退出码也正常，就是没内容。
根因是上游数据的 `source_info` 在某天缺了键，代码没兜住，内容被静默吞掉。
**"安静的失败"比崩溃更危险：崩溃会有人看，安静没人发现。**

处理（提交 `34ccb85`，标题即修复内容）：

1. 修掉缺键吞内容的路径；
2. 补 **16 项离线测试**（不需要网络，断网也能跑），把"缺键""空数据"这类分支全部固化成用例；
   v2 零依赖重写（`8b0f1d4`）时部分用例合并，现为 **13 项**；
3. 接上 CI，让"再变空"这件事**在测试里就暴露，而不是在日报里才被发现**。

13 项现在仍可复跑验证：仓库根目录执行 `python -m unittest discover -s tests`，
输出 `Ran 13 tests ... OK`（2026-11-02 陌生人复验实跑确认）。

> 本节初稿由 AI 助手从提交历史中整理。按"写的人不审自己"的规矩，
> 它会先经另一位独立 AI 助手复核，再由设计者推送发布。

---

## 值得一看的三个点

### 1. 容错是分层的，不是 try/except 包一层

`fetch()` 按顺序试两条通道，`parse_feed()` 解析失败还有兜底：

```
抓取：先走系统代理（外网源需要）   → 失败 → 直连再试一次
解析：严格 XML 解析（xml.etree）    → 失败 → 正则抠 <item>/<entry> 块
读取：连接中途断开（IncompleteRead）→ 已读够 20KB 就用已读部分继续解析
单源：任何一个源彻底失败 → 记进源状态表，其它源照跑
```

源状态会**原样写进产出文件**：哪个源成功、抓到几条、命中几条、失败原因是什么。
下游（日报生成）据此判断"今天是真的没新闻，还是抓取挂了"——这两件事不能混。

> ⚠️ **只对 arXiv 关闭证书校验**（本机证书链校验失败），其它源默认开启。
> 这是写在源配置里的开关（`verify_nossl`），不是全局关闭。

### 2. Windows 计划任务全套操作

`Register-ScheduledTask` / `Unregister-ScheduledTask` / `Start-ScheduledTask` /
`Get-ScheduledTask` / `Get-ScheduledTaskInfo` 全部用到了，
还会检查任务是否已存在、要确认后再覆盖，并打印最后一次运行结果（排障时最关键的那个数字）。

### 3. 交付给不懂技术的人也能用

`Read-Host` + `switch` 做交互式菜单，不用记参数；每一步都有中文提示和成功/失败反馈。

---

## 数据源

**6 个源，2026-10-29 逐个实测确认可用**（按可信度分档）：

| 源 | 语言 | 可信度 | 备注 |
|---|---|---|---|
| OpenAI | en | 高 | RSS 已迁到 `/news/rss.xml`；连接常在 800KB 处被断开，靠部分读取容错 |
| DeepMind | en | 高 | |
| TechCrunch | en | 中高 | |
| Hacker News | en | 中 | **走官方 Algolia API**（`hn.algolia.com/api/v1/search?tags=front_page`）—— 官网 RSS 自 10-30 起连续超时，2026-11-01 换源；API 返回 JSON，脚本已支持 `type: json` 的源 |
| arXiv cs.AI | en | 中高 | 每日几十到几百条，**单源上限 15 条**，否则会淹没整份清单 |
| 量子位 | zh | 中高 | 目前唯一稳定的中文源 |

**已确认不可用（别再试一遍，源码里也留了同样的记录）**：

| 源 | 原因 |
|---|---|
| Anthropic | 已无公开 RSS：`/rss.xml`、`/news/feed.xml`、`/engineering/rss.xml` 全部 404 |
| 机器之心 | `jiqizhixin.com/rss` 返回 `text/html` 反爬页（约 3.4KB），不是 XML |
| 36氪 AI | `36kr.com/information/AI/feed` 返回非法 XML（反爬页） |

**筛选**：中英文关键词表，分四组（模型能力 / 工程部署 / 产业 / 与本地项目直接相关的方向）。
**时间窗**：默认只保留最近 48 小时（`--hours` 可改）。
**单源上限**：每源最多留 15~20 条（`cap` 字段），防止一个大源淹没整份清单。

---

## 依赖

**没有第三方依赖。** 只用 Python 标准库（`urllib` / `xml.etree` / `re` / `email.utils` / `ssl`）。

`requirements.txt` 现在只剩说明行——它是 v1 的遗留（v1 用 `feedparser` + `requests`）。
v2 重写后**克隆下来直接 `python ai_daily_scraper.py` 就能跑，不用 pip install**。

---

## 已知边界（如实写）

- **v1 只跑通过 1 次**。v2 于 2026-10-29 重写，同日连续实跑 4 次：3 次返回 5~6 个可用源，
  1 次只有 2 个可用源（`getaddrinfo failed` / SSL 中断）—— **本机网络本身会抖，不是脚本 bug**。
  所以下游必须容忍"部分源失败"，**不能把「抓不到」当成「今天没新闻」**。
- 依赖源站的 RSS 可用性；源站改版或限流会导致某些源抓不到（脚本会跳过，不会崩）。
- 不做去重与正文抽取，只做标题 / 链接 / 摘要级别的聚合。

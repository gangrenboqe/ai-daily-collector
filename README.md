# ai-daily-collector —— AI 资讯采集 + Windows 计划任务

> 一句话：**抓 10 个 RSS 源做 AI 日报，用 PowerShell 注册成 Windows 计划任务自动跑；
> 抓取那边做了三级降级——直连失败就下载再解析，还不行才忽略 SSL 再试一次。**

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
pip install -r requirements.txt
python ai_daily_scraper.py                 # 输出到脚本同级的 daily/ 目录
python ai_daily_scraper.py out/2026-10-10.md   # 指定输出文件
```

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
3. 接上 CI，让"再变空"这件事**在测试里就暴露，而不是在日报里才被发现**。

16 项现在仍可复跑验证：仓库根目录执行 `python -m unittest discover -s tests`，
输出 `Ran 16 tests ... OK`。

> 本节初稿由 AI 助手从提交历史中整理。按"写的人不审自己"的规矩，
> 它会先经另一位独立 AI 助手复核，再由设计者推送发布。

---

## 值得一看的三个点

### 1. 三级降级容错（不是 try/except 包一层）

`fetch_rss_feed()` 里真的排了三级退路：

```
第 1 级：feedparser 直连解析（带 UA / Accept 头，超时 15s）
   ↓ 失败（bozo，即解析异常）
第 2 级：requests 先下载（SSL 校验开启），再交给 feedparser 解析
   ↓ 失败
第 3 级：requests 下载时关闭 SSL 校验（最后兜底）
   ↓ 失败
返回 None，跳过这个源，不影响其它源
```

> ⚠️ **第 3 级是最后兜底，默认 SSL 校验是开着的。**
> 只在前两级都失败时才会走到 `verify=False`，并且日志里会明确打印
> 「尝试忽略SSL验证」，不静默降级。

### 2. Windows 计划任务全套操作

`Register-ScheduledTask` / `Unregister-ScheduledTask` / `Start-ScheduledTask` /
`Get-ScheduledTask` / `Get-ScheduledTaskInfo` 全部用到了，
还会检查任务是否已存在、要确认后再覆盖，并打印最后一次运行结果（排障时最关键的那个数字）。

### 3. 交付给不懂技术的人也能用

`Read-Host` + `switch` 做交互式菜单，不用记参数；每一步都有中文提示和成功/失败反馈。

---

## 数据源

10 个源，按可信度分档（高 / 中高 / 中）：
量子位、机器之心、36氪 AI、TechCrunch AI、Hacker News、arXiv cs.AI、arXiv cs.CL、
OpenAI Blog、Anthropic News、DeepMind Blog。

筛选：中英文关键词表 + arXiv 分类特判（cs.AI / cs.CL）。
时间窗：只保留最近 24 小时内的条目。

---

## 依赖

- `feedparser` —— 解析 RSS / Atom
- `requests` —— 第 2、3 级降级时的下载

---

## 已知边界（如实写）

- 只跑通过 1 次，长期稳定性未验证。
- 依赖源站的 RSS 可用性；源站改版或限流会导致某些源抓不到（脚本会跳过，不会崩）。
- 不做去重与正文抽取，只做标题 / 链接 / 摘要级别的聚合。

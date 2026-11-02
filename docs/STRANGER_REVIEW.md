# 陌生人复验记录（35 号工单 · P3 ai-daily-collector）

> 复验日期：2026-11-02 · 复验人：技术线（Trae）
> 方法：**真 clone**，严格照 README 命令走（本机 HTTPS 连 GitHub 握手失败——设计者实测记录在案——
> 故 clone 用 SSH 验「命令与目录名」；README 写的是 HTTPS，面试官环境可用）。

## 结果

**抓到 2 个真缺口（均已修/已定性），修复后 demo 一次走通。**

## 复验原文（命令 + 目录名）

```
PS Temp> git clone git@github.com:gangrenboqe/ai-daily-collector.git
Cloning into 'ai-daily-collector'...
clone 后目录名: ai-daily-collector        ← 与 README 的 `cd ai-daily-collector` 一致
```

## 抓到的 2 个缺口

| # | 缺口 | 处置 |
|---|---|---|
| 1 | 第一次复验用了 HTTPS clone → 本机连 GitHub 握手失败（设计者早有实测记录，我漏用 SSH） | 复验改 SSH；README 保持 HTTPS（面试官环境可用），两者不矛盾 |
| 2 | **README 写"16 项测试、`Ran 16 tests ... OK`"，真 clone 实跑只有 `Ran 13 tests`** | 查证：v2 零依赖重写（8b0f1d4）时用例合并为 13，README 数字没跟上 → 已修 README（两个数字都写明，演变可追，2026-11-02 复验实跑确认） |

## demo（离线日报样例）的验证状态

- `python demo.py` 在**本仓工作区**实跑通过（解析 8 条 → 筛选命中 6/过滤 2 → 生成日报全文），输出原文：[docs/demo_output.txt](demo_output.txt)
- 🔴 **demo.py / samples/ / docs/ 尚未推送**——远端 HEAD（以及真 clone）此刻还没有这些文件，"照 README 跑 python demo.py"要等设计者 commit/push 后才能真 clone 复验（同 P1 情形；README 三步命令已在工作区实跑 + 自查 grep 通过：无 SSH 地址 / 无占位符 / 无反斜杠 cd）
- HEAD 上可复验的部分已验：目录名正确、`python -m unittest discover -s tests` → `Ran 13 tests ... OK`

## 复验环境

- Windows 11，Python 3.11，SSH 认证，离线 demo 全程未联网未配 key

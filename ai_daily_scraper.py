#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 资讯采集器（v2 · 零第三方依赖）

抓多个 RSS/Atom 源，按关键词筛 AI 相关内容，输出 Markdown 素材清单。

v2 与 v1 的区别（2026-10-29 实测重写）：
1. **零依赖**：不再用 feedparser，改用标准库 xml.etree + 正则兜底
   （v1 需要 pip install feedparser，clone 下来不装就 ModuleNotFoundError）
2. **源清单按实测重排**：v1 的 10 个源里 5 个已失效/反爬
   - OpenAI 博客 RSS 迁到 /news/rss.xml（旧的 /blog/rss.xml 返回内容不全）
   - Anthropic 已无公开 RSS（三个地址都 404）→ 移出清单
   - 机器之心 / 36氪 返回反爬 HTML 而非 XML → 移出清单
   - arXiv 证书链在本机校验失败 → 单独关校验（只影响这一个源）
3. **单源失败不拖垮整轮**：记进 source_status，其它源照跑
4. **时效过滤**：只要窗口内（默认 48h）的条目，避免把旧闻当新闻
5. **诚实输出**：哪些源成功/失败、各拿几条，全部写进产出，不静默跳过

用法：
    python ai_daily_scraper.py                      # 写到脚本同目录 daily/YYYY-MM-DD-ai.md
    python ai_daily_scraper.py out.md               # 指定输出路径
    AI_DAILY_OUT=out.md python ai_daily_scraper.py  # 环境变量指定
    python ai_daily_scraper.py --hours 24           # 改时效窗口
    python ai_daily_scraper.py --print              # 只打印不写文件

退出码：0 = 有命中；2 = 一个都没命中；1 = 参数/IO 出错
"""

import argparse
import email.utils
from http.client import IncompleteRead
import html
import json
import os
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 源清单（2026-10-29 逐个实测；verify_nossl = 需要关闭证书校验）
# trust 只作下游筛选的参考，不是自动判定
# ---------------------------------------------------------------------------
FEEDS = [
    # cap = 单源最多留几条（实测：arXiv 24h 内 244 条，不设上限会把日报淹成论文列表）
    {"name": "OpenAI",      "url": "https://openai.com/news/rss.xml",      "lang": "en", "trust": "高",   "verify_nossl": False, "cap": 20},
    {"name": "DeepMind",    "url": "https://deepmind.google/blog/rss.xml", "lang": "en", "trust": "高",   "verify_nossl": False, "cap": 20},
    {"name": "TechCrunch",  "url": "https://techcrunch.com/feed/",         "lang": "en", "trust": "中高", "verify_nossl": False, "cap": 20},
    # 🔴 2026-11-01：官网 RSS 连续三天超时，改用官方 Algolia API（JSON，稳定）
    {"name": "Hacker News", "url": "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=40", "lang": "en", "trust": "中", "verify_nossl": False, "cap": 20, "type": "json"},
    {"name": "arXiv cs.AI", "url": "https://arxiv.org/rss/cs.AI",          "lang": "en", "trust": "中高", "verify_nossl": True,  "cap": 15},
    {"name": "量子位",       "url": "https://www.qbitai.com/feed",          "lang": "zh", "trust": "中高", "verify_nossl": False, "cap": 15},
]

# 已知不可用（留档，免得下一个人再试一遍）
KNOWN_DEAD = [
    ("Anthropic", "无公开 RSS：/rss.xml、/news/feed.xml、/engineering/rss.xml 全部 404"),
    ("机器之心",   "https://www.jiqizhixin.com/rss 返回 text/html 反爬页（约 3.4KB），不是 XML"),
    ("36氪 AI",   "https://36kr.com/information/AI/feed 返回非法 XML（反爬页）"),
]

KEYWORDS = [
    # 模型 / 能力
    "llm", "large language model", "gpt", "claude", "gemini", "deepseek", "qwen", "llama",
    "大模型", "模型", "多模态", "推理", "agent", "智能体", "rag", "embedding", "fine-tun",
    # 工程 / 部署
    "inference", "训练", "微调", "量化", "部署", "开源", "benchmark", "评测",
    # 产业
    "openai", "anthropic", "google", "nvidia", "英伟达", "融资", "funding", "acquire",
    "acquisition", "ipo", "开源",
    # 与本地项目直接相关的方向
    "memory", "记忆", "context", "上下文", "tool", "工具调用", "function call",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ai-daily-collector/2.0"


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
def _openers(nossl: bool):
    """按优先级返回 opener：先走系统代理（外网需要），再直连。"""
    if nossl:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handler = urllib.request.HTTPSHandler(context=ctx)
        return [urllib.request.build_opener(handler),
                urllib.request.build_opener(urllib.request.ProxyHandler({}), handler)]
    return [urllib.request.build_opener(),
            urllib.request.build_opener(urllib.request.ProxyHandler({}))]


def fetch(url: str, timeout: int = 20, nossl: bool = False) -> tuple[str, str]:
    """抓一个源，返回 (text, content_type)。代理失败自动改直连。"""
    last = None
    for opener in _openers(nossl):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            })
            with opener.open(req, timeout=timeout) as resp:
                try:
                    raw = resp.read()
                except IncompleteRead as exc:
                    # 部分读取：连接被掐断但已拿到大部分字节时，用已读部分继续解析
                    # （实测：openai.com/news/rss.xml 会返回 800KB 后被断开，整源判失败太浪费）
                    raw = exc.partial or b""
                    if len(raw) < 20000:
                        raise
                return raw.decode("utf-8", "ignore"), resp.headers.get("Content-Type", "?")
        except Exception as exc:          # noqa: BLE001 — 单源失败不能让整轮挂掉
            last = exc
    raise RuntimeError(f"{type(last).__name__}: {last}")


# ---------------------------------------------------------------------------
# 解析：严格 XML 优先，失败走正则兜底
# ---------------------------------------------------------------------------
def _tag(elem) -> str:
    return elem.tag.split("}")[-1].lower() if isinstance(elem.tag, str) else ""


def _text(elem, *names):
    for child in elem:
        if _tag(child) in names:
            return (child.text or "").strip()
    return ""


def _link(elem) -> str:
    for child in elem:
        if _tag(child) == "link":
            href = child.get("href")
            if href:
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    guid = _text(elem, "guid", "id")
    return guid if guid.startswith("http") else ""


def _parse_date(elem):
    """RSS 的 pubDate 是 RFC822，Atom 的 updated/published 是 ISO8601。"""
    raw = _text(elem, "pubdate", "published", "updated", "date")
    if not raw:
        return None
    return _parse_date_str(raw)


def _parse_date_str(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:                     # noqa: BLE001 — 格式不认识就往下试
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.replace(".000", ""), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clean(text: str, limit: int = 300) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def parse_feed(raw: str) -> list[dict]:
    """返回 [{'title','link','summary','published'}]；严格解析失败时正则兜底。"""
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = None

    if root is not None:
        for elem in root.iter():
            if _tag(elem) in ("item", "entry"):
                items.append({
                    "title": _clean(_text(elem, "title"), 200),
                    "link": _link(elem),
                    "summary": _clean(_text(elem, "description", "summary", "content"), 300),
                    "published": _parse_date(elem),
                })
        if items:
            return items

    # 兜底：内容不是合法 XML（反爬页 / 截断 / 非法字符）
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", raw, re.S | re.I):
        title = re.search(r"<title[^>]*>(.*?)</title>", block, re.S | re.I)
        link = (re.search(r"<link[^>]*href=[\"']([^\"']+)[\"']", block, re.I)
                or re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I))
        desc = re.search(r"<(?:description|summary|content)[^>]*>(.*?)</(?:description|summary|content)>",
                         block, re.S | re.I)
        date = re.search(r"<(?:pubDate|published|updated|date)[^>]*>(.*?)</", block, re.S | re.I)
        items.append({
            "title": _clean(title.group(1) if title else "", 200),
            "link": (link.group(1).strip() if link else ""),
            "summary": _clean(desc.group(1) if desc else "", 300),
            "published": _parse_date_str(date.group(1) if date else ""),
        })
    return items


def parse_json_feed(raw: str) -> list[dict]:
    """HN Algolia API 的 JSON → 统一的 item 结构。"""
    out = []
    try:
        d = json.loads(raw)
    except Exception:                     # noqa: BLE001
        return out
    for h in d.get("hits", []) or []:
        title = (h.get("title") or h.get("story_title") or "").strip()
        if not title:
            continue
        link = h.get("url") or ("https://news.ycombinator.com/item?id=" + str(h.get("objectID", "")))
        out.append({
            "title": title,
            "link": link,
            "summary": "HN %s 分 · %s 评论" % (h.get("points") or 0, h.get("num_comments") or 0),
            "published": _parse_date_str(h.get("created_at") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# 筛选与汇总
# ---------------------------------------------------------------------------
def is_ai_related(title: str, summary: str = "") -> bool:
    hay = (title + " " + summary).lower()
    return any(k in hay for k in KEYWORDS)


def collect(hours: int = 48) -> tuple[list[dict], list[dict]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    entries, status = [], []

    for feed in FEEDS:
        try:
            raw, ctype = fetch(feed["url"], nossl=feed["verify_nossl"])
            items = parse_json_feed(raw) if feed.get("type") == "json" else parse_feed(raw)
            cap = feed.get("cap", 25)
            kept = 0
            for it in items:
                if not it["title"]:
                    continue
                pub = it["published"]
                if pub and pub < cutoff:
                    continue
                if not is_ai_related(it["title"], it["summary"]):
                    continue
                if kept >= cap:           # 单源限量，防止一个源淹没整份清单
                    continue
                entries.append({
                    "source": feed["name"], "lang": feed["lang"], "trust": feed["trust"],
                    "title": it["title"], "link": it["link"], "summary": it["summary"],
                    "published": pub.astimezone().strftime("%m-%d %H:%M") if pub else "时间未知",
                    "_ts": pub or datetime.now(timezone.utc),
                })
                kept += 1
            status.append({"name": feed["name"], "ok": True, "total": len(items),
                           "kept": kept, "cap": cap, "ctype": ctype})
        except Exception as exc:          # noqa: BLE001
            status.append({"name": feed["name"], "ok": False, "total": 0, "kept": 0,
                           "error": str(exc)[:160]})

    entries.sort(key=lambda e: e["_ts"], reverse=True)
    return entries, status


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def render(entries: list[dict], status: list[dict], hours: int) -> str:
    now = datetime.now()
    lines = [
        f"# AI 资讯原始素材 · {now:%Y-%m-%d}",
        "",
        f"> 采集时间 {now:%H:%M} ｜ 时效窗口 最近 {hours} 小时 ｜ 命中 {len(entries)} 条",
        "> 本文件是**原材料清单**，只按时间倒序，不做判断、不做重要性排序；筛选与总结由下游完成。",
        "",
        "## 源状态",
        "",
        "| 源 | 结果 | 抓到条目 | 窗口内命中 |",
        "|---|---|---|---|",
    ]
    for s in status:
        if s["ok"]:
            capped = "（已达上限）" if s["kept"] >= s.get("cap", 99) else ""
            lines.append(f"| {s['name']} | ✅ | {s['total']} | {s['kept']}{capped} |")
        else:
            lines.append(f"| {s['name']} | ❌ {s.get('error', '')[:70]} | - | - |")

    lines += ["", "## 条目（按发布时间倒序）", ""]
    if not entries:
        lines.append("_窗口内没有命中任何条目（源今日可能无更新，或关键词过严）。_")
    for e in entries:
        lines.append(f"### {e['title']}")
        lines.append(f"- 来源：{e['source']}（{e['lang']}，可信度 {e['trust']}）｜发布：{e['published']}")
        if e["link"]:
            lines.append(f"- 链接：{e['link']}")
        if e["summary"]:
            lines.append(f"- 摘要：{e['summary']}")
        lines.append("")

    lines += ["---", "", "## 已知不可用的源（别再试）", ""]
    for name, why in KNOWN_DEAD:
        lines.append(f"- **{name}**：{why}")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 资讯采集（零依赖）")
    ap.add_argument("output", nargs="?", help="输出路径；省略则写 daily/YYYY-MM-DD-ai.md")
    ap.add_argument("--hours", type=int, default=48, help="时效窗口小时数，默认 48")
    ap.add_argument("--print", dest="to_stdout", action="store_true", help="只打印，不写文件")
    args = ap.parse_args()

    entries, status = collect(hours=args.hours)
    md = render(entries, status, args.hours)

    ok = sum(1 for s in status if s["ok"])
    print(f"源：{ok}/{len(status)} 可用 ｜ 命中 {len(entries)} 条", file=sys.stderr)
    for s in status:
        if not s["ok"]:
            print(f"  ❌ {s['name']}: {s.get('error', '')[:90]}", file=sys.stderr)

    if args.to_stdout:
        print(md)
        return 0 if entries else 2

    out = args.output or os.environ.get("AI_DAILY_OUT")
    if not out:
        out = str(Path(__file__).resolve().parent / "daily" / f"{datetime.now():%Y-%m-%d}-ai.md")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md)
    print(f"已写入 {out}", file=sys.stderr)
    return 0 if entries else 2


if __name__ == "__main__":
    sys.exit(main())

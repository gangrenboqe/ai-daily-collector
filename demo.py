"""ai-daily-collector 离线演示 —— 不联网、不配任何 key。

跑什么（全部复用 ai_daily_scraper.py 的现成函数，不新做功能）：
  1. 解析内置样例 RSS（samples/sample_feed.xml，合成数据，8 条）
  2. 关键词筛选：8 条里只有 AI 相关的能进日报（顺带看到 2 条被过滤）
  3. 生成一份日报样例 → daily/ 目录，并打印全文

它演示的是「解析 → 筛选 → 生成日报」这条离线管线；
真实的联网抓取（多源降级、部分读取容错）请跑 `python ai_daily_scraper.py`。

运行：python demo.py    （仓库根目录，Python 3.9+，零第三方依赖）
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import ai_daily_scraper as ads


def main() -> None:
    sample = Path(__file__).resolve().parent / "samples" / "sample_feed.xml"
    print("=" * 64)
    print("ai-daily-collector · 离线演示（合成样例数据，不联网）")
    print("=" * 64)

    # 1) 解析
    raw = sample.read_text(encoding="utf-8")
    items = ads.parse_feed(raw)
    print(f"\n[1] 解析 RSS：{len(items)} 条（内置样例 samples/sample_feed.xml）")

    # 2) 关键词筛选（与联网采集走同一个 is_ai_related）
    kept, dropped = [], []
    for it in items:
        (kept if ads.is_ai_related(it["title"], it["summary"]) else dropped).append(it)
    print(f"[2] 关键词筛选：命中 {len(kept)} 条 / 过滤 {len(dropped)} 条")
    for it in dropped:
        print(f"    × 被过滤（非 AI）：{it['title']}")

    # 3) 组装成日报（字段结构与联网采集 collect() 完全一致）
    now = datetime.now(timezone.utc)
    entries = [{
        "source": "样例源（离线）", "lang": "zh/en", "trust": "样例",
        "title": it["title"], "link": it["link"], "summary": it["summary"],
        "published": it["published"].astimezone().strftime("%m-%d %H:%M") if it["published"] else "时间未知",
        "_ts": it["published"] or now,
    } for it in kept]
    status = [{"name": "样例源（离线）", "ok": True, "total": len(items),
               "kept": len(kept), "cap": 25, "ctype": "样例 XML"}]
    report = ads.render(entries, status, hours=48)

    out_dir = Path(__file__).resolve().parent / "daily"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now():%Y-%m-%d}-sample.md"
    out.write_text(report, encoding="utf-8")

    print(f"\n[3] 日报样例已生成：{out.relative_to(Path(__file__).resolve().parent)}")
    print("-" * 64)
    print(report)
    print("-" * 64)
    print("联网跑真实采集：python ai_daily_scraper.py   （输出到 daily/ 目录）")


if __name__ == "__main__":
    main()

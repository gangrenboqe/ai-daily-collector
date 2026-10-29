#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_daily_scraper 的单元测试（v2 · 零依赖版）

只测纯函数，不碰网络——网络行为实测记录见 README「已知边界」。
跑：python -m unittest discover -s tests -v
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai_daily_scraper as ads  # noqa: E402

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>测试源</title>
  <item>
    <title>某公司发布新模型 X-2</title>
    <link>https://example.com/a</link>
    <description>&lt;p&gt;支持 128k 上下文&lt;/p&gt;</description>
    <pubDate>Tue, 28 Oct 2026 21:30:00 +0000</pubDate>
  </item>
  <item>
    <title>与 AI 无关的新闻</title>
    <link>https://example.com/b</link>
    <description>今天天气不错</description>
    <pubDate>Tue, 28 Oct 2026 20:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Gemini 4 Carbon</title>
    <link rel="alternate" href="https://example.com/gemini"/>
    <summary>下一代前沿模型</summary>
    <updated>2026-10-29T01:00:00Z</updated>
  </entry>
</feed>
"""

# 非法 XML（反爬页 / 截断）——必须有兜底
BROKEN_SAMPLE = """<html><body>
<item><title>被反爬页包住的条目</title><link>https://example.com/c</link>
<description>大模型相关内容</description><pubDate>2026-10-28T12:00:00Z</pubDate></item>
</body></html>"""


class TestParseFeed(unittest.TestCase):
    def test_rss2(self):
        items = ads.parse_feed(RSS_SAMPLE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "某公司发布新模型 X-2")
        self.assertEqual(items[0]["link"], "https://example.com/a")
        # HTML 标签要被清掉，实体要还原
        self.assertIn("128k", items[0]["summary"])
        self.assertNotIn("<p>", items[0]["summary"])

    def test_atom(self):
        items = ads.parse_feed(ATOM_SAMPLE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Gemini 4 Carbon")
        # Atom 的 link 在属性里，不在文本节点
        self.assertEqual(items[0]["link"], "https://example.com/gemini")

    def test_broken_xml_falls_back_to_regex(self):
        """反爬页/截断：严格解析必然失败，必须还能抠出条目。"""
        items = ads.parse_feed(BROKEN_SAMPLE)
        self.assertEqual(len(items), 1)
        self.assertIn("反爬页", items[0]["title"])
        self.assertEqual(items[0]["link"], "https://example.com/c")


class TestDates(unittest.TestCase):
    def test_rfc822(self):
        dt = ads._parse_date_str("Tue, 28 Oct 2026 21:30:00 +0000")
        self.assertEqual(dt.astimezone(timezone.utc).hour, 21)

    def test_iso8601_z(self):
        dt = ads._parse_date_str("2026-10-29T01:00:00Z")
        self.assertEqual(dt.astimezone(timezone.utc).hour, 1)

    def test_unknown_returns_none(self):
        self.assertIsNone(ads._parse_date_str(""))
        self.assertIsNone(ads._parse_date_str("昨天下午"))


class TestFilter(unittest.TestCase):
    def test_matches_chinese(self):
        self.assertTrue(ads.is_ai_related("蚂蚁开源新的大模型"))
        self.assertTrue(ads.is_ai_related("谈 agent 的工具调用"))

    def test_matches_english_case_insensitive(self):
        self.assertTrue(ads.is_ai_related("OpenAI ships new LLM"))

    def test_rejects_unrelated(self):
        self.assertFalse(ads.is_ai_related("TikTok 新增餐厅指南"))
        self.assertFalse(ads.is_ai_related("某地发布暴雨预警", "注意出行安全"))


class TestRender(unittest.TestCase):
    def test_source_status_written_into_output(self):
        """源失败必须出现在产出里——不许静默跳过。"""
        entries = [{
            "source": "测试源", "lang": "zh", "trust": "中高",
            "title": "标题", "link": "https://example.com/a", "summary": "摘要",
            "published": "10-28 21:30", "_ts": datetime.now(timezone.utc),
        }]
        status = [
            {"name": "测试源", "ok": True, "total": 10, "kept": 1, "cap": 20},
            {"name": "坏源", "ok": False, "total": 0, "kept": 0, "error": "getaddrinfo failed"},
        ]
        md = ads.render(entries, status, 36)
        self.assertIn("测试源", md)
        self.assertIn("getaddrinfo failed", md)
        self.assertIn("标题", md)
        self.assertIn("最近 36 小时", md)

    def test_empty_entries_says_so(self):
        md = ads.render([], [{"name": "源", "ok": True, "total": 0, "kept": 0}], 24)
        self.assertIn("没有命中", md)


class TestCaps(unittest.TestCase):
    def test_every_feed_has_cap(self):
        """单源必须有上限，否则 arXiv 会淹没整份清单（实测 244 条）。"""
        for feed in ads.FEEDS:
            self.assertIn("cap", feed, f"{feed['name']} 缺 cap")
            self.assertLessEqual(feed["cap"], 30, f"{feed['name']} 的 cap 太大")

    def test_only_arxiv_disables_ssl(self):
        nossl = [f["name"] for f in ads.FEEDS if f["verify_nossl"]]
        self.assertEqual(nossl, ["arXiv cs.AI"], "关证书校验的源必须只有 arXiv 一个")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""ai-daily-collector 的单元测试。

🔴 测试**绝不允许联网**：所有用例只用本地构造的数据。
   这类采集器最容易写出「测着测着就在线上了」的假测试，
   一旦网络抖动 CI 就红，而红的原因和代码无关。

要测的三块纯逻辑：
  · is_ai_related   —— 关键词过滤（决定哪些条目进日报）
  · extract_entry_info —— 24 小时窗口过滤 + 字段容错
  · generate_markdown —— 输出排版

运行：python -m unittest discover -s tests
"""

import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_daily_scraper import extract_entry_info, generate_markdown, is_ai_related


def make_entry(title="A new AI model release", link="https://example.com/a", days_ago=0, desc="deep learning"):
    """造一个长得像 feedparser 条目的对象（它返回的是类实例，不是 dict）。"""
    e = types.SimpleNamespace()
    e.title = title
    e.link = link
    e.description = desc
    e.summary = desc
    stamp = datetime.now() - timedelta(days=days_ago)
    e.published_parsed = stamp.timetuple()[:6]
    e.updated_parsed = stamp.timetuple()[:6]
    e.author = "someone"
    e.tags = []
    return e


# 必须给全：曾经因为这里少一个键，KeyError 被 except 吞掉，
# 结果整份日报静默变成空报告。现在 .get() 已兜住，测试专门守这条。
SRC = {"name": "Test Source", "category": "test", "trust": "high", "language": "en"}


class TestIsAiRelated(unittest.TestCase):
    def test_english_keyword(self):
        self.assertTrue(is_ai_related("Deep learning breakthrough", ""))

    def test_chinese_keyword(self):
        self.assertTrue(is_ai_related("大模型发布新版本", ""))

    def test_case_insensitive(self):
        self.assertTrue(is_ai_related("openai ships gpt", ""))

    def test_unrelated_rejected(self):
        self.assertFalse(is_ai_related("Local bakery opens downtown", "sandwiches"))

    def test_empty_rejected(self):
        self.assertFalse(is_ai_related("", ""))

    def test_keyword_in_description_counts(self):
        self.assertTrue(is_ai_related("无标题", "本文讨论人工智能"))

    def test_arxiv_category_path(self):
        self.assertTrue(is_ai_related("cs.AI paper", ""))


class TestExtractEntryInfo(unittest.TestCase):
    def test_recent_entry_kept(self):
        info = extract_entry_info(make_entry(days_ago=0), SRC)
        self.assertIsNotNone(info)

    def test_old_entry_dropped(self):
        """超过24 小时必须丢——日报只放当天的。"""
        self.assertIsNone(extract_entry_info(make_entry(days_ago=5), SRC))

    def test_missing_title_falls_back(self):
        e = make_entry()
        del e.title
        info = extract_entry_info(e, SRC)
        self.assertIsNotNone(info)
        self.assertEqual(info["title"], "无标题")

    def test_link_fallback_to_id(self):
        e = make_entry()
        del e.link
        e.id = "https://example.com/from-id"
        info = extract_entry_info(e, SRC)
        self.assertEqual(info["url"], "https://example.com/from-id")

    def test_entry_without_dates_kept(self):
        """没有日期的条目不该被丢掉（有些源不给时间）。"""
        e = make_entry()
        del e.published_parsed
        del e.updated_parsed
        self.assertIsNotNone(extract_entry_info(e, SRC))


class TestSilentFailureGuard(unittest.TestCase):
    """这条守一个真实修过的bug：配置少一个键就整份报告变空。"""

    def test_minimal_source_info_still_works(self):
        info = extract_entry_info(make_entry(), {"name": "S"})
        self.assertIsNotNone(info, "source_info 缺字段时不应把整条丢掉")
        self.assertEqual(info["trust"], "unknown")

    def test_empty_source_info_does_not_nuke_entry(self):
        info = extract_entry_info(make_entry(), {})
        self.assertIsNotNone(info, "空 source_info 也不该让条目消失")


class TestGenerateMarkdown(unittest.TestCase):
    def test_empty_is_safe(self):
        out = generate_markdown([])
        self.assertIsInstance(out, str)

    def test_with_entry_has_title(self):
        out = generate_markdown([{"title": "Hello AI", "source": "T", "url": "https://x.com/1",
                                  "trust": "high", "language": "en", "pub_date": "2026-10-12",
                                  "summary": "s"}])
        self.assertIn("Hello AI", out)
        self.assertIn("https://x.com/1", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
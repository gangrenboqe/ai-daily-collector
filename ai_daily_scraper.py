#!/usr/bin/env python3
"""
AI每日前沿信息抓取脚本（Python版本）
抓取多个RSS源，筛选AI相关内容
"""

import feedparser
import requests
from datetime import datetime, timedelta
import re
from urllib.parse import urlparse
import json
import os
import sys
from pathlib import Path

def fetch_rss_feed(url, timeout=15):
    """抓取并解析RSS源"""
    try:
        # 设置User-Agent和接受头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, application/atom+xml, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        
        # 尝试使用feedparser直接解析
        print(f"  尝试直接解析: {url}")
        feed = feedparser.parse(url, request_headers=headers, timeout=timeout)
        
        if feed.bozo:
            print(f"  解析失败: {feed.bozo_exception}")
            # 使用requests下载后解析
            try:
                print(f"  尝试下载后解析...")
                response = requests.get(url, headers=headers, timeout=timeout, verify=True)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                
                if feed.bozo:
                    print(f"  下载后解析仍失败")
                    return None
                else:
                    print(f"  ✓ 下载解析成功")
            except Exception as e:
                print(f"  下载失败: {e}")
                # 尝试不使用SSL验证
                try:
                    print(f"  尝试忽略SSL验证...")
                    response = requests.get(url, headers=headers, timeout=timeout, verify=False)
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                    print(f"  ✓ 忽略SSL验证后成功")
                except Exception as e2:
                    print(f"  ✗ 所有方法都失败: {e2}")
                    return None
        
        return feed
        
    except Exception as e:
        print(f"抓取失败 {url}: {e}")
        return None

def is_ai_related(title, description):
    """检查内容是否与AI相关"""
    ai_keywords = [
        # 英文关键词
        "AI", "artificial intelligence", "machine learning", "deep learning",
        "model", "LLM", "GPT", "transformer", "neural network", "NLP",
        "natural language processing", "computer vision", "CV", "reinforcement learning",
        "generative AI", "AIGC", "algorithm", "training", "inference", "deployment",
        "OpenAI", "Anthropic", "Google", "Meta", "Microsoft", "framework",
        "policy", "regulation", "ethics", "security", "evaluation", "benchmark",
        
        # 中文关键词
        "人工智能", "机器学习", "深度学习", "模型", "大模型",
        "自然语言处理", "计算机视觉", "强化学习", "生成式AI", "算法",
        "训练", "推理", "部署", "工具", "框架", "政策", "监管", "安全"
    ]
    
    text_to_check = f"{title} {description}".lower()
    
    for keyword in ai_keywords:
        if keyword.lower() in text_to_check:
            return True
    
    # 检查arxiv的特定分类
    if "arxiv" in text_to_check and any(kw in text_to_check for kw in ["cs.ai", "cs.cl", "ai", "nlp"]):
        return True
        
    return False

def extract_entry_info(entry, source_info):
    """从RSS条目中提取信息"""
    try:
        # 提取发布日期
        pub_date = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_date = datetime(*entry.published_parsed[:6])
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            pub_date = datetime(*entry.updated_parsed[:6])
        
        # 检查是否在最近24小时内
        if pub_date:
            time_delta = datetime.now() - pub_date
            if time_delta.days > 1 or (time_delta.days == 1 and time_delta.seconds > 0):
                return None
        
        # 提取标题
        title = entry.title if hasattr(entry, 'title') else "无标题"
        
        # 提取链接
        link = ""
        if hasattr(entry, 'link'):
            link = entry.link
        elif hasattr(entry, 'links') and entry.links:
            link = entry.links[0].href
        elif hasattr(entry, 'id'):
            link = entry.id
        
        # 提取描述
        description = ""
        if hasattr(entry, 'summary'):
            description = entry.summary
        elif hasattr(entry, 'description'):
            description = entry.description
        
        # 清理HTML标签
        description = re.sub(r'<[^>]+>', '', description)
        
        # 截断描述
        if len(description) > 200:
            description = description[:200] + "..."
        
        # 检查是否为AI相关内容
        if not is_ai_related(title, description):
            return None
        
        return {
            'title': title.strip(),
            'source': source_info['name'],
            'url': link,
            'trust': source_info['trust'],
            'language': source_info['language'],
            'pub_date': pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else "未知",
            'summary': description.strip() if description.strip() else "无摘要"
        }
        
    except Exception as e:
        print(f"解析条目失败: {e}")
        return None

def scrape_all_sources():
    """抓取所有配置的源"""
    # 配置源列表
    sources = [
        # 中文源
        {"name": "量子位", "url": "https://www.qbitai.com/feed", "language": "zh", "trust": "中高"},
        {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "language": "zh", "trust": "中高"},
        {"name": "36氪 AI", "url": "https://36kr.com/information/AI/feed", "language": "zh", "trust": "中高"},
        
        # 英文源
        {"name": "TechCrunch AI", "url": "https://techcrunch.com/feed/", "language": "en", "trust": "中高"},
        {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "language": "en", "trust": "中"},
        {"name": "arXiv cs.AI", "url": "https://arxiv.org/rss/cs.AI", "language": "en", "trust": "中高"},
        {"name": "arXiv cs.CL", "url": "https://arxiv.org/rss/cs.CL", "language": "en", "trust": "中高"},
        
        # 官方博客
        {"name": "OpenAI", "url": "https://openai.com/blog/rss.xml", "language": "en", "trust": "高"},
        {"name": "Anthropic", "url": "https://www.anthropic.com/news/rss.xml", "language": "en", "trust": "高"},
        {"name": "DeepMind", "url": "https://deepmind.google/blog/rss.xml", "language": "en", "trust": "高"}
    ]
    
    all_entries = []
    
    print(f"开始抓取AI前沿信息...")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"配置源数量: {len(sources)}")
    print("-" * 50)
    
    for source in sources:
        print(f"正在抓取: {source['name']}...")
        
        try:
            feed = fetch_rss_feed(source['url'])
            
            if not feed or not hasattr(feed, 'entries'):
                print(f"  ⚠ 未找到有效条目")
                continue
            
            for entry in feed.entries[:10]:  # 每个源最多取10条最新
                entry_info = extract_entry_info(entry, source)
                if entry_info:
                    all_entries.append(entry_info)
                    print(f"  ✓ {entry_info['title'][:50]}...")
            
        except Exception as e:
            print(f"  ✗ 抓取失败: {e}")
    
    print("-" * 50)
    print(f"完成！共收集 {len(all_entries)} 条AI相关内容")
    
    return all_entries

def generate_markdown(entries):
    """生成Markdown报告"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 按源分组并排序
    sources_dict = {}
    for entry in entries:
        source = entry['source']
        if source not in sources_dict:
            sources_dict[source] = []
        sources_dict[source].append(entry)
    
    # 按可信度排序
    trust_order = {"高": 3, "中高": 2, "中": 1}
    entries.sort(key=lambda x: trust_order.get(x['trust'], 0), reverse=True)
    
    # 生成Markdown内容
    md_content = f"""# AI前沿信息日报 ({date_str})

**数据采集时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**抓取源数**: {len(sources_dict)}
**总条目数**: {len(entries)}

---

"""
    
    # 按源分组展示
    for source_name, source_entries in sources_dict.items():
        # 获取该源的可信度
        trust_level = source_entries[0]['trust'] if source_entries else "未知"
        
        md_content += f"### 🔗 {source_name} (可信度: {trust_level})\n\n"
        
        for entry in source_entries:
            md_content += f"""- **{entry['title']}**  
  来源: {entry['source']} · 语言: {entry['language']} · 发布时间: {entry['pub_date']}  
  链接: [{entry['url']}]({entry['url']})  
  摘要: {entry['summary']}

"""
    
    # 统计信息
    md_content += """---

## 📊 统计信息

| 来源 | 条目数 | 可信度 |
|------|--------|--------|
"""
    
    for source_name, source_entries in sources_dict.items():
        trust_level = source_entries[0]['trust'] if source_entries else "未知"
        md_content += f"| {source_name} | {len(source_entries)} | {trust_level} |\n"
    
    md_content += f"| **总计** | **{len(entries)}** | - |\n\n"
    
    # 可信度分布
    trust_dist = {}
    for entry in entries:
        trust = entry['trust']
        trust_dist[trust] = trust_dist.get(trust, 0) + 1
    
    md_content += "### 📈 可信度分布\n"
    for trust, count in sorted(trust_dist.items(), key=lambda x: x[1], reverse=True):
        md_content += f"- {trust}: {count} 条\n"
    
    md_content += f"""

---

> 自动化采集于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 数据仅供参考，请以原文为准
"""
    
    return md_content

def main():
    """主函数"""
    try:
        # 输出路径：命令行参数优先，其次环境变量，最后默认落在脚本同级的 daily/ 目录
        # （不再依赖任何写死的绝对路径，clone 到任何机器都能跑）
        if len(sys.argv) > 1:
            output_path = sys.argv[1]
        elif os.environ.get("AI_DAILY_OUT"):
            output_path = os.environ["AI_DAILY_OUT"]
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
            default_dir = Path(__file__).resolve().parent / "daily"
            output_path = str(default_dir / f"{date_str}-ai.md")

        # 确保目录存在
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        # 抓取数据
        entries = scrape_all_sources()
        
        if entries:
            # 生成Markdown
            md_content = generate_markdown(entries)
            
            # 写入文件
            if os.path.exists(output_path):
                # 追加模式
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                # 查找并替换旧内容或追加新内容
                new_content = existing_content + "\n\n---\n\n" + md_content
                
                # 写入文件时添加UTF-8 BOM
                with open(output_path, 'w', encoding='utf-8-sig') as f:
                    f.write(new_content)
            else:
                # 写入文件时添加UTF-8 BOM
                with open(output_path, 'w', encoding='utf-8-sig') as f:
                    f.write(md_content)
            
            print(f"报告已保存到: {output_path}")
            
            # 返回成功信息
            return {
                'status': 'success',
                'entries_count': len(entries),
                'output_path': output_path
            }
        else:
            print("未找到AI相关内容")
            return {'status': 'no_content'}
            
    except Exception as e:
        print(f"脚本执行失败: {e}")
        return {'status': 'error', 'message': str(e)}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result['status'] == 'success' else 1)
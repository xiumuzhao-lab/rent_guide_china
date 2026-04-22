#!/usr/bin/env python3.10
"""
链家租房数据爬虫 (兼容入口)

功能已迁移至 scraper 包。此文件保留向后兼容。
详细文档请参考 scraper/ 目录下的各模块。

使用方法 (不变):
    python3.10 lianjia_scraper.py --areas all
    python3.10 lianjia_scraper.py --areas zhangjiang,jinqiao --max-pages 20
    python3.10 lianjia_scraper.py --analyze output/xxx.json
"""

import asyncio
import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scraper.config import OUTPUT_DIR, ALL_REGIONS, REGIONS
from scraper.utils import setup_logging
from scraper.scraper_core import scrape_with_browser, scrape_with_agent
from scraper.storage import save_results
from scraper.analyzer import analyze_listings


async def main():
    """兼容旧命令行入口."""
    from scraper.pipeline import parse_args, run_pipeline
    args = parse_args()
    setup_logging(OUTPUT_DIR)
    await run_pipeline(args)


if __name__ == '__main__':
    asyncio.run(main())

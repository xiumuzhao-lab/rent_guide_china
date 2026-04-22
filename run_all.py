#!/usr/bin/env python3.10
"""
一键运行: 爬取 + 分析 + 生成地图 (兼容入口)

功能已迁移至 scraper.pipeline。此文件保留向后兼容。

使用方法 (不变):
    python3.10 run_all.py --areas all --workplace 张江国创
    python3.10 run_all.py --skip-scrape --workplace 金桥
    python3.10 run_all.py --areas zhangjiang --skip-map
"""

import asyncio
import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scraper.config import OUTPUT_DIR
from scraper.utils import setup_logging
from scraper.pipeline import parse_args, run_pipeline


async def run():
    """兼容旧命令行入口."""
    args = parse_args()
    setup_logging(OUTPUT_DIR)
    await run_pipeline(args)


if __name__ == '__main__':
    asyncio.run(run())

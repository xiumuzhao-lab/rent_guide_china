#!/usr/bin/env python3.10
"""
支持 python3.10 -m scraper 运行.
"""

import asyncio
import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scraper.pipeline import main

if __name__ == '__main__':
    asyncio.run(main())

"""
通用工具模块

日志初始化、系统通知、去重、单价计算、环境变量加载。
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from scraper.config import OUTPUT_DIR, REGIONS


def load_env():
    """
    从 .env 文件加载环境变量 (不覆盖已存在的).

    Returns:
        bool: 是否成功加载了 .env 文件
    """
    env_file = Path(__file__).parent.parent / '.env'
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v
    return True


# 模块加载时自动读取 .env
load_env()


def setup_logging(output_dir: Path = None):
    """
    配置日志: 控制台 + 文件.

    Args:
        output_dir: 日志文件目录，默认使用 OUTPUT_DIR

    Returns:
        logging.Logger: 配置好的日志器
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    log = logging.getLogger('lianjia')
    log.setLevel(logging.INFO)

    # 避免重复添加 handler
    if log.handlers:
        return log

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(ch)

    # 文件
    fh = logging.FileHandler(output_dir / 'scraper.log', encoding='utf-8', mode='a')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    log.addHandler(fh)

    return log


logger = setup_logging()


def notify(title, message):
    """
    发送 macOS 系统通知 + 终端响铃.

    Args:
        title: 通知标题
        message: 通知内容
    """
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}" sound name "Glass"'
        ], timeout=5, capture_output=True)
    except Exception:
        pass
    sys.stdout.write('\a')
    sys.stdout.flush()


def add_unit_price(item):
    """
    为单条房源计算单价 (元/㎡/月).

    Args:
        item: 房源数据字典，会原地修改添加 unit_price 字段
    """
    try:
        price = int(item['price']) if str(item.get('price', '')).isdigit() else None
        area = float(item['area']) if item.get('area') else None
        if price and area and area > 0:
            item['unit_price'] = round(price / area, 1)
        else:
            item['unit_price'] = ''
    except (ValueError, TypeError):
        item['unit_price'] = ''


def deduplicate(data):
    """
    按 URL 去重，保留最新记录.

    Args:
        data: 房源数据列表

    Returns:
        list: 去重后的列表
    """
    seen = {}
    for item in data:
        key = item.get('url', '') or (
            item.get('community', '') + str(item.get('price', ''))
            + str(item.get('area', '')) + item.get('region', '')
        )
        if key:
            seen[key] = item
    return list(seen.values())


def get_area_url(slug: str, page: int = None) -> str:
    """
    根据区域 slug 和页码生成 URL.

    Args:
        slug: 区域标识 (如 zhangjiang)
        page: 页码，None 或 0 表示首页

    Returns:
        str: 完整 URL
    """
    base = f"https://sh.lianjia.com/zufang/{slug}/"
    if page is None or page <= 0:
        return base
    return f"{base}pg{page}/"

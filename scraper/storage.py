"""
数据存储模块

JSON/CSV 保存、断点续爬 (增强: 每 N 条自动保存中间结果)。
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from scraper.config import CSV_FIELDS, OUTPUT_DIR, SAVE_INTERVAL
from scraper.utils import deduplicate, add_unit_price, get_area_url

logger = logging.getLogger('lianjia')


# ============================================================
# 中间结果保存
# ============================================================

def partial_path(area_slug: str) -> Path:
    """
    断点续爬文件路径.

    Args:
        area_slug: 区域标识

    Returns:
        Path: 断点文件路径
    """
    return OUTPUT_DIR / f"lianjia_{area_slug}.partial.json"


def load_resume(area_slug: str):
    """
    加载断点续爬数据.

    Args:
        area_slug: 区域标识

    Returns:
        tuple: (existing_data, start_page, completed) — 已有数据、起始页码、是否已完成
    """
    pfile = partial_path(area_slug)
    if not pfile.exists():
        return [], 1, False
    try:
        resume = json.loads(pfile.read_text(encoding='utf-8'))
        data = resume.get('data', [])
        start_page = resume.get('last_page', 1)
        completed = resume.get('completed', False)
        if completed:
            logger.info(f"发现已完成数据: {len(data)} 条")
        else:
            logger.info(f"发现断点数据: {len(data)} 条, 从第 {start_page} 页续爬")
        return data, start_page, completed
    except Exception:
        return [], 1, False


def save_partial(area_slug: str, data: list, last_page: int,
                 completed: bool = False):
    """
    保存断点文件.

    Args:
        area_slug: 区域标识
        data: 当前已爬取的数据
        last_page: 最后完成的页码
        completed: 该区域是否已完整爬完
    """
    pfile = partial_path(area_slug)
    pfile.parent.mkdir(parents=True, exist_ok=True)
    pfile.write_text(
        json.dumps({'last_page': last_page, 'data': data,
                    'completed': completed},
                   ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def save_periodic(area_slug: str, data: list, page_num: int,
                  last_save_count: int) -> int:
    """
    每 SAVE_INTERVAL 条保存一次中间结果.

    Args:
        area_slug: 区域标识
        data: 当前累计数据
        page_num: 当前页码
        last_save_count: 上次保存时的数据条数

    Returns:
        int: 更新后的 last_save_count
    """
    current_count = len(data)
    if current_count - last_save_count >= SAVE_INTERVAL:
        save_partial(area_slug, deduplicate(data), page_num)
        logger.info(f"  [自动保存] 已保存 {current_count} 条中间数据")
        return current_count
    return last_save_count


def clear_partial(area_slug: str):
    """
    清除断点文件 (区域完成后调用).

    Args:
        area_slug: 区域标识
    """
    pfile = partial_path(area_slug)
    if pfile.exists():
        pfile.unlink()


def clear_all_partials():
    """清除所有断点文件 (--fresh 时调用)."""
    count = 0
    for pfile in OUTPUT_DIR.glob('lianjia_*.partial.json'):
        pfile.unlink()
        count += 1
    if count:
        logger.info(f"已清除 {count} 个断点文件")


# ============================================================
# 最终结果保存
# ============================================================

def save_to_csv(data: list, filepath: Path):
    """
    保存数据为 CSV 文件.

    Args:
        data: 房源数据列表
        filepath: 输出文件路径
    """
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"CSV 已保存: {filepath}")


def save_to_json(data: list, filepath: Path):
    """
    保存数据为 JSON 文件.

    Args:
        data: 房源数据列表
        filepath: 输出文件路径
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 已保存: {filepath}")


def enrich_with_geo(data: list):
    """
    为每条房源添加经纬度 (基于小区名批量地理编码).

    Args:
        data: 房源数据列表，原地修改添加 lat/lng 字段
    """
    from scraper.geo import get_geocoder

    geocoder = get_geocoder()

    community_regions = {}
    for item in data:
        community = item.get('community', '').strip()
        if community and community not in community_regions:
            community_regions[community] = item.get('region', '')

    if not community_regions:
        return

    logger.info(f"开始地理编码: {len(community_regions)} 个唯一小区...")
    geo_coords = geocoder.batch_geocode(community_regions)

    matched = 0
    for item in data:
        community = item.get('community', '').strip()
        if community and community in geo_coords:
            lat, lng = geo_coords[community]
            item['lat'] = round(lat, 6)
            item['lng'] = round(lng, 6)
            matched += 1
        else:
            item['lat'] = ''
            item['lng'] = ''

    logger.info(f"地理编码完成: {matched}/{len(data)} 条房源匹配到坐标")


def save_results(all_listings: list, selected_areas: list, fmt: str = 'both'):
    """
    统一保存: 去重 + 按区域 + 合并文件.

    Args:
        all_listings: 全部房源数据
        selected_areas: 选中的区域列表
        fmt: 输出格式 (csv/json/both)

    Returns:
        Path or None: 合并 JSON 的路径
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    OUTPUT_DIR.mkdir(exist_ok=True)

    all_listings = deduplicate(all_listings)
    logger.info(f"去重后: {len(all_listings)} 条")

    # 添加经纬度
    enrich_with_geo(all_listings)

    latest_json = None

    for slug in selected_areas:
        region_data = [l for l in all_listings if l.get('region') == slug]
        if not region_data:
            continue
        if fmt in ('csv', 'both'):
            save_to_csv(region_data, OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.json"
            save_to_json(region_data, p)
            if not latest_json:
                latest_json = p

    if len(selected_areas) > 1:
        if fmt in ('csv', 'both'):
            save_to_csv(all_listings, OUTPUT_DIR / f"lianjia_all_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_all_{timestamp}.json"
            save_to_json(all_listings, p)
            latest_json = p

    return latest_json

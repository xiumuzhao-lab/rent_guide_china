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

    独栋 (品牌公寓) 的社区名无法被地图 API 准确解析到具体门店，
    跳过地理编码以避免产生错误的统一坐标。

    Args:
        data: 房源数据列表，原地修改添加 lat/lng 字段
    """
    from scraper.geo import get_geocoder

    geocoder = get_geocoder()

    # 先标记独栋房源，跳过地理编码
    dudong_comms = set()
    for item in data:
        rt = item.get('rent_type', item.get('rentType', ''))
        if rt == '独栋':
            item['lat'] = None
            item['lng'] = None
            dudong_comms.add(item.get('community', '').strip())

    community_info = {}
    for item in data:
        community = item.get('community', '').strip()
        if not community or community in dudong_comms:
            continue
        if community not in community_info:
            community_info[community] = {
                'region': item.get('region', ''),
                'location': item.get('location', ''),
            }

    if not community_info:
        logger.info(f"无需要地理编码的小区 (跳过 {len(dudong_comms)} 个独栋社区)")
        return

    logger.info(f"开始地理编码: {len(community_info)} 个唯一小区"
                f" (跳过 {len(dudong_comms)} 个独栋社区)...")
    geo_coords = geocoder.batch_geocode(community_info)

    matched = 0
    missed = 0
    for item in data:
        if item.get('lat') is not None:
            continue  # 已处理 (独栋已设为 None)
        community = item.get('community', '').strip()
        if community and community in geo_coords:
            coords = geo_coords[community]
            if coords:
                lat, lng = coords
                item['lat'] = round(lat, 6)
                item['lng'] = round(lng, 6)
                matched += 1
            else:
                item['lat'] = None
                item['lng'] = None
                missed += 1
        else:
            item['lat'] = None
            item['lng'] = None
            missed += 1

    logger.info(f"地理编码完成: {matched}/{len(data)} 条匹配, {missed} 条无坐标"
                f" (跳过 {len(dudong_comms)} 个独栋社区)")


def save_results(all_listings: list, selected_areas: list, fmt: str = 'both'):
    """
    统一保存: 去重 + 按实际区域 + 合并文件.

    注意: 大区域 (如 pudong) 可能被展开为子区域，此时每条记录的 region
    是子区域 slug (如 beicai)，而非原始 selected_areas 中的父区域。
    因此按数据中实际出现的区域分文件保存，并始终生成合并文件。

    Args:
        all_listings: 全部房源数据
        selected_areas: 选中的区域列表 (可能被展开)
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

    # 按数据中实际出现的 region 分文件保存
    actual_regions = sorted({l.get('region', '') for l in all_listings
                             if l.get('region')})
    for slug in actual_regions:
        region_data = [l for l in all_listings if l.get('region') == slug]
        if not region_data:
            continue
        if fmt in ('csv', 'both'):
            save_to_csv(region_data,
                        OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.json"
            save_to_json(region_data, p)
            if not latest_json:
                latest_json = p

    # 始终生成合并文件 (多区域或展开后的子区域都需要)
    if len(actual_regions) > 1:
        if fmt in ('csv', 'both'):
            save_to_csv(all_listings,
                        OUTPUT_DIR / f"lianjia_all_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_all_{timestamp}.json"
            save_to_json(all_listings, p)
            latest_json = p

    return latest_json


# ============================================================
# 地理缓存刷新
# ============================================================

def _collect_communities_from_json(filepath):
    """
    从 JSON 文件中提取 {社区名: 区域} 映射.

    Args:
        filepath: JSON 文件路径

    Returns:
        dict: { community_name: region }
    """
    try:
        data = json.loads(filepath.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return {}
    # partial 文件结构: {"data": [...]}
    if isinstance(data, dict):
        data = data.get('data', [])
    if not isinstance(data, list):
        return {}
    communities = {}
    for item in data:
        name = item.get('community', '').strip()
        if name and name not in communities:
            communities[name] = item.get('region', '')
    return communities


def _collect_communities_from_csv(filepath):
    """
    从 CSV 文件中提取 {社区名: 区域} 映射.

    Args:
        filepath: CSV 文件路径

    Returns:
        dict: { community_name: region }
    """
    communities = {}
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get('community', '').strip()
                if name and name not in communities:
                    communities[name] = row.get('region', '')
    except (OSError, UnicodeDecodeError):
        pass
    return communities


def _collect_community_info(filepath):
    """
    从数据文件中提取 {社区名: {region, location}} 映射.

    Args:
        filepath: 数据文件路径 (JSON 或 CSV)

    Returns:
        dict: { community_name: { region: str, location: str } }
    """
    try:
        if filepath.suffix == '.json':
            data = json.loads(filepath.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data = data.get('data', [])
            if not isinstance(data, list):
                return {}
            rows = data
        else:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}

    communities = {}
    for item in rows:
        name = (item.get('community') or '').strip()
        if name and name not in communities:
            communities[name] = {
                'region': item.get('region', ''),
                'location': item.get('location', ''),
            }
    return communities


def _update_json_geo(filepath, geo_coords):
    """
    更新 JSON 文件中所有记录的 lat/lng.

    Args:
        filepath: JSON 文件路径
        geo_coords: dict { community_name: (lat, lng) }

    Returns:
        int: 更新的记录数
    """
    try:
        data = json.loads(filepath.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return 0

    is_partial = isinstance(data, dict)
    if is_partial:
        records = data.get('data', [])
    else:
        records = data

    if not isinstance(records, list):
        return 0

    updated = 0
    for item in records:
        community = item.get('community', '').strip()
        if community and community in geo_coords:
            coords = geo_coords[community]
            if coords:
                lat, lng = coords
                old_lat, old_lng = item.get('lat'), item.get('lng')
                item['lat'] = round(lat, 6)
                item['lng'] = round(lng, 6)
                if old_lat != item['lat'] or old_lng != item['lng']:
                    updated += 1
            else:
                item['lat'] = None
                item['lng'] = None
        else:
            item['lat'] = None
            item['lng'] = None

    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding='utf-8')

    return updated


def _update_csv_geo(filepath, geo_coords):
    """
    更新 CSV 文件中所有记录的 lat/lng.

    Args:
        filepath: CSV 文件路径
        geo_coords: dict { community_name: (lat, lng) }

    Returns:
        int: 更新的记录数
    """
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames or CSV_FIELDS
    except (OSError, UnicodeDecodeError):
        return 0

    if 'lat' not in fieldnames:
        fieldnames = list(fieldnames) + ['lat', 'lng']

    updated = 0
    for row in rows:
        community = row.get('community', '').strip()
        if community and community in geo_coords:
            coords = geo_coords[community]
            if coords:
                lat, lng = coords
                old_lat, old_lng = row.get('lat', ''), row.get('lng', '')
                row['lat'] = str(round(lat, 6))
                row['lng'] = str(round(lng, 6))
                if old_lat != row['lat'] or old_lng != row['lng']:
                    updated += 1
            else:
                row['lat'] = ''
                row['lng'] = ''
        else:
            row['lat'] = ''
            row['lng'] = ''

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    return updated


def refresh_geo_in_files(force=False):
    """
    刷新地理位置缓存，并更新 output/ 下所有数据文件的 lat/lng。

    步骤:
        1. 扫描所有数据文件，收集唯一小区名 (含 location 信息)
        2. 调用 batch_refresh 更新主缓存 (含坐标校验)
        3. 用新缓存更新每个文件的 lat/lng 字段

    Args:
        force: 是否强制重查所有条目 (包括已有腾讯API结果的)

    Returns:
        dict: 刷新统计 { refreshed, upgraded, files_updated, records_updated }
    """
    from scraper.geo import get_geocoder

    geocoder = get_geocoder()

    # 1. 收集所有文件中的小区名 (含 location 用于坐标校验)
    all_communities = {}
    file_list = []

    for pattern in ['lianjia_*.json', 'lianjia_*.csv']:
        for fp in sorted(OUTPUT_DIR.glob(pattern)):
            if fp.name == 'community_geo_cache.json':
                continue
            file_list.append(fp)
            comms = _collect_community_info(fp)
            for name, info in comms.items():
                if name not in all_communities:
                    all_communities[name] = info

    if not all_communities:
        logger.info("未找到数据文件，无需刷新")
        return {"refreshed": 0, "upgraded": 0,
                "files_updated": 0, "records_updated": 0}

    logger.info(f"扫描到 {len(file_list)} 个数据文件, "
                f"{len(all_communities)} 个唯一小区")

    # 2. 刷新主缓存
    geo_coords = geocoder.batch_refresh(all_communities, force=force)

    # 3. 更新每个文件
    total_updated = 0
    files_updated = 0

    for fp in file_list:
        if fp.suffix == '.json':
            count = _update_json_geo(fp, geo_coords)
        else:
            count = _update_csv_geo(fp, geo_coords)
        if count > 0:
            files_updated += 1
            total_updated += count
            logger.info(f"  更新 {fp.name}: {count} 条记录")

    # 4. 保存缓存
    geocoder._save_cache()

    # 统计
    stats = {
        "refreshed": len(all_communities),
        "files_updated": files_updated,
        "records_updated": total_updated,
    }
    logger.info(
        f"地理位置刷新完成: {len(all_communities)} 个小区, "
        f"{files_updated} 个文件, {total_updated} 条记录更新"
    )
    return stats


# ============================================================
# 数据聚合
# ============================================================

def merge_all_partials(fmt='both'):
    """
    聚合所有 partial 断点文件，去重后输出合并 JSON/CSV。

    同时保存一份 lianjia_merged_latest.json 供前端和后续流程使用。

    Args:
        fmt: 输出格式 (csv/json/both)

    Returns:
        Path or None: 合并 JSON 的路径
    """
    all_listings = []
    partial_files = sorted(OUTPUT_DIR.glob('lianjia_*.partial.json'))

    if not partial_files:
        logger.warning("未找到任何 partial 文件")
        return None

    for pf in partial_files:
        try:
            data = json.loads(pf.read_text(encoding='utf-8'))
            records = data.get('data', [])
            completed = data.get('completed', False)
            status = "完成" if completed else "未完成"
            logger.info(f"  {pf.name}: {len(records)} 条 [{status}]")
            all_listings.extend(records)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"  {pf.name}: 读取失败 ({e})")

    if not all_listings:
        logger.warning("所有 partial 文件均为空")
        return None

    logger.info(f"读取总计: {len(all_listings)} 条")

    all_listings = deduplicate(all_listings)
    logger.info(f"去重后: {len(all_listings)} 条")

    # 补全单价和经纬度
    for item in all_listings:
        add_unit_price(item)
    enrich_with_geo(all_listings)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    OUTPUT_DIR.mkdir(exist_ok=True)

    latest_json = None

    # 按区域分文件
    actual_regions = sorted({l.get('region', '') for l in all_listings
                             if l.get('region')})
    for slug in actual_regions:
        region_data = [l for l in all_listings if l.get('region') == slug]
        if not region_data:
            continue
        if fmt in ('csv', 'both'):
            save_to_csv(region_data,
                        OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.json"
            save_to_json(region_data, p)
            if not latest_json:
                latest_json = p

    # 合并文件 (all)
    if fmt in ('csv', 'both'):
        save_to_csv(all_listings,
                    OUTPUT_DIR / f"lianjia_all_{timestamp}.csv")
    if fmt in ('json', 'both'):
        p = OUTPUT_DIR / f"lianjia_all_{timestamp}.json"
        save_to_json(all_listings, p)
        latest_json = p

    # always 写一份 latest 快捷引用
    latest_path = OUTPUT_DIR / "lianjia_merged_latest.json"
    save_to_json(all_listings, latest_path)

    # 统计
    region_stats = {}
    for item in all_listings:
        r = item.get('region', 'unknown')
        region_stats[r] = region_stats.get(r, 0) + 1
    logger.info(f"\n聚合统计 ({len(all_listings)} 条):")
    for r in sorted(region_stats, key=region_stats.get, reverse=True)[:15]:
        logger.info(f"  {r}: {region_stats[r]} 条")
    if len(region_stats) > 15:
        logger.info(f"  ... 共 {len(region_stats)} 个区域")

    return latest_json

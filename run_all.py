#!/usr/bin/env python3
"""
一键运行: 爬取 + 分析 + 生成地图

将 lianjia_scraper.py 和 community_geo_map.py 串联为一个流程，
支持参数透传，可选择跳过爬取或地图步骤。

使用方法:
    # 完整流程: 爬取 + 地图
    python3.10 run_all.py --areas all --workplace 张江国创

    # 仅生成地图 (使用已有数据)
    python3.10 run_all.py --skip-scrape --workplace 金桥

    # 仅爬取 + 分析 (不生成地图)
    python3.10 run_all.py --areas zhangjiang --skip-map

    # 指定数据文件生成地图
    python3.10 run_all.py --skip-scrape --data output/lianjia_all_xxx.json --workplace 张江
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from lianjia_scraper import (
    REGIONS,
    ALL_REGIONS,
    OUTPUT_DIR,
    scrape_with_browser,
    save_results,
    analyze_listings,
    setup_logging,
)
from community_geo_map import (
    build_community_stats,
    generate_static_map,
    generate_html_map,
    print_distance_report,
    get_workplace,
    load_data,
    find_latest_data,
    _geocoder,
)


def parse_args():
    """解析合并参数."""
    parser = argparse.ArgumentParser(
        description='链家租房 — 一键爬取 + 分析 + 生成地图',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ---- 爬虫参数 ----
    scrape_group = parser.add_argument_group('爬虫参数')
    scrape_group.add_argument('--areas', type=str, default='all',
                              help='区域: all 或 zhangjiang,jinqiao,tangzhen,chuansha,changning')
    scrape_group.add_argument('--max-pages', type=int, default=100,
                              help='每区域最大页数 (默认 100)')
    scrape_group.add_argument('--mode', choices=['browser', 'agent'], default='browser',
                              help='爬取模式 (默认 browser)')
    scrape_group.add_argument('--model', default='gpt-4o',
                              help='Agent 模式 LLM (默认 gpt-4o)')
    scrape_group.add_argument('--format', choices=['csv', 'json', 'both'], default='both',
                              help='输出格式 (默认 both)')

    # ---- 地图参数 ----
    map_group = parser.add_argument_group('地图参数')
    map_group.add_argument('--workplace', type=str, default='张江国创',
                           help='工作地点 (中文名/拼音key/经纬度)')
    map_group.add_argument('--workplace-name', type=str, default=None,
                           help='自定义工作地点显示名')
    map_group.add_argument('--max-distance', type=float, default=15,
                           help='最大距离 km (默认 15)')
    map_group.add_argument('--max-labels', type=int, default=200,
                           help='图片标注小区数 (默认 200, 0=全部)')

    # ---- 控制参数 ----
    ctrl_group = parser.add_argument_group('控制参数')
    ctrl_group.add_argument('--skip-scrape', action='store_true',
                            help='跳过爬取，仅生成地图和分析')
    ctrl_group.add_argument('--skip-map', action='store_true',
                            help='跳过地图，仅爬取和分析')
    ctrl_group.add_argument('--data', type=str, default=None,
                            help='指定数据文件 (--skip-scrape 时生效，默认自动查找最新)')

    return parser.parse_args()


def run_map_generation(data_path: Path, workplace: dict,
                       max_distance: float, max_labels: int):
    """
    执行地图生成流程.

    Args:
        data_path: JSON 数据文件路径
        workplace: 工作地点配置
        max_distance: 最大距离 km
        max_labels: 最大标注数
    """
    data = load_data(str(data_path))
    print(f'\n已加载 {len(data)} 条房源数据，开始生成地图...')

    # 聚合小区统计
    community_stats = build_community_stats(data)
    print(f'涉及 {len(community_stats)} 个小区')

    # 控制台报告
    print_distance_report(community_stats, workplace, max_distance)

    # 生成地图
    generate_static_map(community_stats, workplace, max_distance, max_labels)
    generate_html_map(community_stats, workplace, max_distance)

    # 确保地理编码缓存持久化
    _geocoder._save_cache()

    print('\n地图生成完成!')


async def run():
    """主流程."""
    args = parse_args()
    logger = setup_logging(OUTPUT_DIR)

    # ---- Step 1: 爬取 ----
    latest_json = None

    if not args.skip_scrape:
        # 解析区域
        if args.areas == 'all':
            selected = ALL_REGIONS[:]
        else:
            selected = [a.strip() for a in args.areas.split(',')]
        invalid = [a for a in selected if a not in REGIONS]
        if invalid:
            logger.error(f'未知区域: {invalid}，可选: {ALL_REGIONS}')
            sys.exit(1)

        area_names = [REGIONS[a]['name'] for a in selected]
        logger.info('=' * 60)
        logger.info(f'链家租房数据爬虫 | 区域: {", ".join(area_names)} | 模式: {args.mode}')
        logger.info('=' * 60)

        # 爬取
        if args.mode == 'browser':
            listings = await scrape_with_browser(selected, args.max_pages)
        else:
            listings = await scrape_with_agent(selected, args.max_pages, args.model)

        if listings:
            logger.info(f'\n共爬取 {len(listings)} 条房源数据')
            latest_json = save_results(listings, selected, args.format)
            # 分析 + 图表
            analyze_listings(listings)
        else:
            logger.warning('未爬取到任何数据')
    else:
        print('跳过爬取步骤')

    # ---- Step 2: 生成地图 ----
    if not args.skip_map:
        workplace = get_workplace(args.workplace)
        if args.workplace_name:
            workplace['name'] = args.workplace_name

        # 确定数据文件
        if args.data:
            data_path = Path(args.data)
            if not data_path.exists():
                data_path = PROJECT_DIR / args.data
        elif latest_json:
            data_path = latest_json
        else:
            data_path = find_latest_data()

        print(f'\n{"=" * 60}')
        print(f'地图生成 | 工作地点: {workplace["name"]} | 数据: {data_path.name}')
        print(f'{"=" * 60}')

        max_labels = args.max_labels if args.max_labels > 0 else 999999
        run_map_generation(data_path, workplace, args.max_distance, max_labels)
    else:
        print('\n跳过地图生成步骤')

    print('\n全部流程完成!')


if __name__ == '__main__':
    asyncio.run(run())

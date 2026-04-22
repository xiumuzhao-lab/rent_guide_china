#!/usr/bin/env python3.10
"""
链家小区单价地图生成器 (兼容入口)

功能已迁移至 scraper 包。此文件保留向后兼容。

使用方法 (不变):
    python3.10 community_geo_map.py
    python3.10 community_geo_map.py --workplace 金桥
    python3.10 community_geo_map.py --workplace 张江国创 --max-distance 15
"""

import sys
from pathlib import Path

# 确保项目目录在 sys.path 中
PROJECT_DIR = Path(__file__).parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scraper.config import WORKPLACES, OUTPUT_DIR
from scraper.pipeline import get_workplace, find_latest_data, load_data
from scraper.map_generator import (
    build_community_stats,
    generate_static_map,
    generate_html_map,
    print_distance_report,
)
from scraper.geo import get_geocoder
from scraper.utils import setup_logging


def main():
    """兼容旧命令行入口."""
    import argparse

    wp_list = "\n".join(
        f"  {v['name']}  (或 {k})" for k, v in WORKPLACES.items())
    parser = argparse.ArgumentParser(
        description="链家小区单价地图生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
预定义工作地点:
{wp_list}

示例:
  python3.10 %(prog)s
  python3.10 %(prog)s --workplace 张江国创
  python3.10 %(prog)s --workplace 金桥 --max-distance 15
  python3.10 %(prog)s --dry-run
        """,
    )

    parser.add_argument("--workplace", type=str, default="张江国创")
    parser.add_argument("--workplace-name", type=str, default=None)
    parser.add_argument("--data", type=str, default=None)
    parser.add_argument("--max-distance", type=float, default=15)
    parser.add_argument("--max-labels", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-geo", action="store_true")

    args = parser.parse_args()
    setup_logging(OUTPUT_DIR)

    workplace = get_workplace(args.workplace)
    if args.workplace_name:
        workplace["name"] = args.workplace_name

    if args.refresh_geo:
        print("清除地理编码缓存...")
        get_geocoder().clear_cache()

    if args.data:
        data = load_data(args.data)
    else:
        data = load_data(str(find_latest_data()))

    print(f"已加载 {len(data)} 条房源数据")
    community_stats = build_community_stats(data)
    print(f"涉及 {len(community_stats)} 个小区")

    print_distance_report(community_stats, workplace, args.max_distance)

    if not args.dry_run:
        max_labels = (args.max_labels if args.max_labels > 0
                      else len(community_stats))
        generate_static_map(
            community_stats, workplace, args.max_distance, max_labels)
        generate_html_map(community_stats, workplace, args.max_distance)

    get_geocoder()._save_cache()


if __name__ == "__main__":
    main()

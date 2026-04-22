"""
流水线编排模块

全流程: 爬取 → 存储 → 分析 → 地图，各步骤自动重试、补偿式恢复。
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from scraper.config import (
    ALL_REGIONS,
    OUTPUT_DIR,
    PROJECT_DIR,
    REGIONS,
    WORKPLACES,
)
from scraper.utils import (
    deduplicate,
    get_area_url,
    logger,
    notify,
    setup_logging,
)
from scraper.retry import ErrorLog, PipelineStep, error_log
from scraper.scraper_core import (
    scrape_with_agent,
    scrape_with_browser,
)
from scraper.storage import (
    clear_all_partials,
    enrich_with_geo,
    save_results,
)
from scraper.analyzer import analyze_listings
from scraper.map_generator import (
    build_community_stats,
    generate_html_map,
    generate_static_map,
    print_distance_report,
)
from scraper.geo import get_geocoder


# ============================================================
# 辅助函数
# ============================================================

def get_workplace(key: str) -> dict:
    """
    获取工作地点配置，支持拼音key、中文模糊匹配、坐标.

    Args:
        key: 工作地点标识

    Returns:
        dict: 工作地点配置

    Raises:
        SystemExit: 未匹配到工作地点
    """
    if key in WORKPLACES:
        return dict(WORKPLACES[key])

    for wp in WORKPLACES.values():
        if key in wp["name"] or wp["name"].startswith(key):
            return dict(wp)

    if "," in key:
        parts = key.split(",")
        if len(parts) == 2:
            try:
                return {
                    "name": f"自定义 ({key})",
                    "lat": float(parts[0]),
                    "lng": float(parts[1]),
                    "address": "",
                }
            except ValueError:
                pass

    logger.error(f'未匹配工作地点 — "{key}"')
    logger.info("可选:")
    for k, v in WORKPLACES.items():
        logger.info(f"  {v['name']}  (或 {k})")
    logger.info('或使用坐标: --workplace "31.22,121.54"')
    sys.exit(1)


def find_latest_data() -> Path:
    """
    在 output/ 下查找最新爬取数据.

    Returns:
        Path: 最新数据文件路径

    Raises:
        SystemExit: 未找到数据文件
    """
    output_dir = OUTPUT_DIR
    if not output_dir.exists():
        logger.error(f"output 目录不存在 — {output_dir}")
        logger.info("请先运行: python -m scraper.pipeline --areas all")
        sys.exit(1)

    for pattern in ["lianjia_all_*.json", "lianjia_*_*.json"]:
        files = sorted(output_dir.glob(pattern), reverse=True)
        if files:
            return files[0]

    logger.error("未找到数据文件，请先运行爬虫")
    sys.exit(1)


def load_data(filepath: str) -> list:
    """
    加载 JSON 或 CSV 数据文件.

    Args:
        filepath: 文件路径

    Returns:
        list: 数据列表

    Raises:
        SystemExit: 文件不存在或格式不支持
    """
    import json
    import csv

    path = Path(filepath)
    if not path.exists():
        path = PROJECT_DIR / filepath
    if not path.exists():
        logger.error(f"文件不存在 — {filepath}")
        sys.exit(1)

    logger.info(f"加载数据: {path}")
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix == ".json":
            return json.load(f)
        elif path.suffix == ".csv":
            return list(csv.DictReader(f))
    logger.error(f"不支持 {path.suffix} 格式")
    sys.exit(1)


# ============================================================
# 流水线步骤函数
# ============================================================

async def _step_scrape(selected_areas, max_pages, mode, model):
    """
    爬取步骤.

    Args:
        selected_areas: 区域列表
        max_pages: 最大页数
        mode: 爬取模式 (browser/agent)
        model: Agent 模式 LLM

    Returns:
        list: 爬取结果
    """
    if mode == 'browser':
        return await scrape_with_browser(selected_areas, max_pages)
    else:
        return await scrape_with_agent(selected_areas, max_pages, model)


async def _step_save(listings, selected_areas, fmt):
    """
    保存步骤.

    Args:
        listings: 房源数据
        selected_areas: 区域列表
        fmt: 输出格式

    Returns:
        Path or None: 保存的 JSON 文件路径
    """
    if not listings:
        logger.warning("未爬取到任何数据，跳过保存")
        return None
    logger.info(f"\n共爬取 {len(listings)} 条房源数据")
    return save_results(listings, selected_areas, fmt)


def _step_analyze(listings):
    """
    分析步骤.

    Args:
        list: 房源数据
    """
    if not listings:
        return
    analyze_listings(listings)


def _step_map(data_path, workplace, max_distance, max_labels):
    """
    地图生成步骤.

    Args:
        data_path: 数据文件路径
        workplace: 工作地点配置
        max_distance: 最大距离
        max_labels: 最大标注数
    """
    if not data_path:
        logger.warning("无数据文件，跳过地图生成")
        return

    data = load_data(str(data_path))
    logger.info(f"已加载 {len(data)} 条房源数据，开始生成地图...")

    community_stats = build_community_stats(data)
    logger.info(f"涉及 {len(community_stats)} 个小区")

    print_distance_report(community_stats, workplace, max_distance)
    generate_static_map(community_stats, workplace, max_distance, max_labels)
    generate_html_map(community_stats, workplace, max_distance)

    get_geocoder()._save_cache()
    logger.info("\n地图生成完成!")


# ============================================================
# 主流水线
# ============================================================

async def run_pipeline(args):
    """
    执行完整流水线.

    各步骤自动重试，失败后继续后续步骤（可选步骤）。

    Args:
        args: 解析后的命令行参数
    """
    logger.info("=" * 60)
    logger.info(f"链家租房数据流水线 | 模式: {args.mode}")
    logger.info("=" * 60)

    latest_json = None
    all_listings = []

    # ---- Step 1: 爬取 ----
    if not args.skip_scrape:
        if args.fresh:
            clear_all_partials()

        area_names = [REGIONS[a]['name'] for a in args.selected_areas]
        logger.info(f"区域: {', '.join(area_names)}")

        step_scrape = PipelineStep(
            name="爬取",
            func=lambda: _step_scrape(
                args.selected_areas, args.max_pages, args.mode, args.model),
            max_attempts=3,
            backoff_base=5.0,
        )
        try:
            all_listings = await step_scrape.execute()
        except Exception as e:
            logger.error(f"爬取步骤失败: {e}")
            notify("链家爬虫", f"爬取失败: {e}")
    else:
        logger.info("跳过爬取步骤")

    # ---- Step 2: 保存 ----
    if not args.skip_scrape and all_listings:
        step_save = PipelineStep(
            name="保存",
            func=lambda: _step_save(
                all_listings, args.selected_areas, args.format),
            max_attempts=3,
            backoff_base=2.0,
        )
        try:
            latest_json = await step_save.execute()
        except Exception as e:
            logger.error(f"保存步骤失败: {e}")
            # 尝试直接保存为简单 JSON
            try:
                import json as json_mod
                from datetime import datetime
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                fallback = OUTPUT_DIR / f"lianjia_fallback_{ts}.json"
                OUTPUT_DIR.mkdir(exist_ok=True)
                fallback.write_text(
                    json_mod.dumps(all_listings, ensure_ascii=False, indent=2),
                    encoding='utf-8')
                latest_json = fallback
                logger.info(f"已保存到备用文件: {fallback}")
            except Exception:
                pass

    # ---- Step 3: 分析 ----
    if all_listings:
        step_analyze = PipelineStep(
            name="分析",
            func=lambda: _step_analyze(all_listings),
            max_attempts=2,
            backoff_base=1.0,
            optional=True,
        )
        try:
            await step_analyze.execute()
        except Exception:
            pass  # 可选步骤，失败不中断

    # ---- Step 4: 地图 ----
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

        logger.info(f"\n{'=' * 60}")
        logger.info(f"地图生成 | 工作地点: {workplace['name']} "
                    f"| 数据: {data_path.name}")
        logger.info(f"{'=' * 60}")

        max_labels = (args.max_labels if args.max_labels > 0
                      else 999999)

        step_map = PipelineStep(
            name="地图",
            func=lambda: _step_map(
                data_path, workplace, args.max_distance, max_labels),
            max_attempts=2,
            backoff_base=1.0,
            optional=True,
        )
        try:
            await step_map.execute()
        except Exception:
            pass  # 可选步骤，失败不中断
    else:
        logger.info("\n跳过地图生成步骤")

    # ---- 完成 ----
    logger.info(error_log.summary())
    notify("链家爬虫", "全部流程完成!")
    logger.info("\n全部流程完成!")


# ============================================================
# CLI 入口
# ============================================================

def parse_args(argv=None):
    """
    解析命令行参数.

    Args:
        argv: 命令行参数列表，None 则使用 sys.argv

    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = argparse.ArgumentParser(
        description='链家租房数据流水线 (爬取 + 分析 + 地图)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m scraper.pipeline --areas all
  python -m scraper.pipeline --areas zhangjiang,jinqiao --max-pages 20
  python -m scraper.pipeline --skip-scrape --workplace 金桥
  python -m scraper.pipeline --analyze output/lianjia_all_xxx.json
        """,
    )

    # 爬虫参数
    scrape_group = parser.add_argument_group('爬虫参数')
    scrape_group.add_argument('--mode', choices=['browser', 'agent'],
                              default='browser', help='爬取模式')
    scrape_group.add_argument('--areas', type=str, default='all',
                              help='区域: all 或逗号分隔')
    scrape_group.add_argument('--max-pages', type=int, default=100,
                              help='每区域最大页数')
    scrape_group.add_argument('--model', default='gpt-4o',
                              help='Agent 模式 LLM')
    scrape_group.add_argument('--format', choices=['csv', 'json', 'both'],
                              default='both', help='输出格式')

    # 地图参数
    map_group = parser.add_argument_group('地图参数')
    map_group.add_argument('--workplace', type=str, default='张江国创',
                           help='工作地点')
    map_group.add_argument('--workplace-name', type=str, default=None,
                           help='自定义工作地点显示名')
    map_group.add_argument('--max-distance', type=float, default=15,
                           help='最大距离 km')
    map_group.add_argument('--max-labels', type=int, default=200,
                           help='图片标注小区数 (0=全部)')

    # 控制参数
    ctrl_group = parser.add_argument_group('控制参数')
    ctrl_group.add_argument('--skip-scrape', action='store_true',
                            help='跳过爬取')
    ctrl_group.add_argument('--fresh', action='store_true',
                            help='清除所有断点数据，从头爬取')
    ctrl_group.add_argument('--skip-map', action='store_true',
                            help='跳过地图')
    ctrl_group.add_argument('--data', type=str, default=None,
                            help='指定数据文件')
    ctrl_group.add_argument('--analyze', type=str, default=None,
                            help='仅分析: 指定 JSON 文件路径')

    args = parser.parse_args(argv)

    # 解析区域
    if args.analyze:
        args.skip_scrape = True
        args.skip_map = True
        args.data = args.analyze

    if args.areas == 'all':
        args.selected_areas = ALL_REGIONS[:]
    else:
        args.selected_areas = [a.strip() for a in args.areas.split(',')]

    # 动态注册未知区域 (slug 作为显示名)
    for slug in args.selected_areas:
        if slug not in REGIONS:
            REGIONS[slug] = {'name': slug, 'slug': slug}

    return args


async def main(argv=None):
    """
    主入口函数.

    Args:
        argv: 命令行参数列表
    """
    args = parse_args(argv)
    setup_logging(OUTPUT_DIR)

    await run_pipeline(args)


if __name__ == '__main__':
    asyncio.run(main())

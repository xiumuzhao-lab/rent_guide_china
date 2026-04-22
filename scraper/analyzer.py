"""
数据分析模块

统计摘要 + matplotlib 图表生成。
"""

import logging
from collections import Counter
from pathlib import Path

from scraper.config import OUTPUT_DIR, REGIONS

logger = logging.getLogger('lianjia')


def analyze_listings(data: list):
    """
    生成统计摘要和图表.

    Args:
        data: 房源数据列表
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = [
        'Arial Unicode MS', 'PingFang SC', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    charts_dir = OUTPUT_DIR / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 预处理数值
    for item in data:
        try:
            item['_price'] = (
                int(item['price'])
                if str(item.get('price', '')).isdigit() else None)
        except (ValueError, TypeError):
            item['_price'] = None
        try:
            item['_area'] = (
                float(item['area']) if item.get('area') else None)
        except (ValueError, TypeError):
            item['_area'] = None

    regions = sorted(set(item.get('region', '') for item in data))
    region_names = {r: REGIONS.get(r, {}).get('name', r) for r in regions}
    colors = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f']
    region_colors = {r: colors[i % len(colors)] for i, r in enumerate(regions)}

    _chart_price_boxplot(data, regions, region_names, region_colors, charts_dir)
    _chart_price_histogram(data, charts_dir)
    _chart_rooms_by_region(data, regions, region_names, region_colors, charts_dir)
    _chart_avg_area(data, regions, region_names, region_colors, charts_dir)
    _chart_top_communities(data, charts_dir)
    _chart_rent_type_pie(data, charts_dir)
    _chart_price_vs_area(data, regions, region_names, region_colors, charts_dir)
    _chart_direction_by_region(data, regions, region_names, region_colors,
                               charts_dir)

    _print_summary(data, regions, region_names)
    logger.info(f"\n图表已保存到: {charts_dir}/")


def _chart_price_boxplot(data, regions, region_names, region_colors, charts_dir):
    """各区域价格分布 (箱线图)."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    price_data = []
    labels = []
    for r in regions:
        prices = [item['_price'] for item in data
                  if item.get('region') == r and item['_price']]
        prices = [p for p in prices if p <= 30000]
        if prices:
            price_data.append(prices)
            labels.append(region_names[r])
    if price_data:
        bp = ax.boxplot(price_data, tick_labels=labels, patch_artist=True)
        for patch, r in zip(bp['boxes'], regions):
            patch.set_facecolor(region_colors.get(r, '#4e79a7'))
        ax.set_title('各区域月租金分布 (≤3万)', fontsize=14)
        ax.set_ylabel('月租金 (元/月)')
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '1_price_by_region.png', dpi=150)
    plt.close(fig)


def _chart_price_histogram(data, charts_dir):
    """价格直方图."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    all_prices = [item['_price'] for item in data
                  if item['_price'] and item['_price'] <= 30000]
    if all_prices:
        ax.hist(all_prices, bins=30, color='#4e79a7', edgecolor='white',
                alpha=0.8)
        ax.set_title('整体价格分布', fontsize=14)
        ax.set_xlabel('月租金 (元/月)')
        ax.set_ylabel('房源数量')
        avg_price = sum(all_prices) / len(all_prices)
        ax.axvline(avg_price, color='red', linestyle='--',
                   label=f'均价 {avg_price:,.0f}')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '2_price_histogram.png', dpi=150)
    plt.close(fig)


def _chart_rooms_by_region(data, regions, region_names, region_colors, charts_dir):
    """各区域户型分布."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    all_rooms = Counter(item.get('rooms', '') for item in data
                        if item.get('rooms'))
    top_rooms = [r for r, _ in all_rooms.most_common(8)]
    x = range(len(top_rooms))
    width = 0.15
    for i, r in enumerate(regions):
        r_data = [item for item in data if item.get('region') == r]
        counts = [sum(1 for item in r_data if item.get('rooms') == room)
                  for room in top_rooms]
        ax.bar([xi + i * width for xi in x], counts, width,
               label=region_names[r], color=region_colors[r], alpha=0.85)
    ax.set_title('各区域户型分布', fontsize=14)
    ax.set_xlabel('户型')
    ax.set_ylabel('房源数量')
    ax.set_xticks([xi + width * (len(regions) - 1) / 2 for xi in x])
    ax.set_xticklabels(top_rooms)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '3_rooms_by_region.png', dpi=150)
    plt.close(fig)


def _chart_avg_area(data, regions, region_names, region_colors, charts_dir):
    """各区域平均面积."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    avg_areas = {}
    for r in regions:
        areas = [item['_area'] for item in data
                 if item.get('region') == r and item['_area']]
        if areas:
            avg_areas[region_names[r]] = sum(areas) / len(areas)
    if avg_areas:
        bars = ax.bar(
            avg_areas.keys(), avg_areas.values(),
            color=[region_colors[r] for r in regions
                   if region_names[r] in avg_areas])
        ax.set_title('各区域平均面积', fontsize=14)
        ax.set_ylabel('平均面积 (㎡)')
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1,
                    f'{bar.get_height():.0f}', ha='center', fontsize=11)
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '4_avg_area_by_region.png', dpi=150)
    plt.close(fig)


def _chart_top_communities(data, charts_dir):
    """热门小区 TOP15."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7))
    comm_counter = Counter(
        item.get('community', '') for item in data if item.get('community'))
    top15 = comm_counter.most_common(15)
    if top15:
        names = [c[:20] + '...' if len(c) > 20 else c
                 for c, _ in reversed(top15)]
        counts = [n for _, n in reversed(top15)]
        ax.barh(names, counts, color='#59a14f', alpha=0.85)
        ax.set_title('热门小区 TOP 15', fontsize=14)
        ax.set_xlabel('房源数量')
        for i, v in enumerate(counts):
            ax.text(v + 0.3, i, str(v), va='center', fontsize=10)
        ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '5_top_communities.png', dpi=150)
    plt.close(fig)


def _chart_rent_type_pie(data, charts_dir):
    """租赁类型占比."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 7))
    type_counter = Counter(
        item.get('rent_type', '') for item in data if item.get('rent_type'))
    if type_counter:
        labels_pie = list(type_counter.keys())
        sizes = list(type_counter.values())
        ax.pie(sizes, labels=labels_pie, autopct='%1.1f%%', startangle=90,
               colors=['#4e79a7', '#f28e2b', '#e15759', '#76b7b2'])
        ax.set_title('租赁类型占比', fontsize=14)
    fig.tight_layout()
    fig.savefig(charts_dir / '6_rent_type_pie.png', dpi=150)
    plt.close(fig)


def _chart_price_vs_area(data, regions, region_names, region_colors, charts_dir):
    """价格 vs 面积散点图."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7))
    for r in regions:
        pts = [(item['_area'], item['_price'])
               for item in data
               if item.get('region') == r and item['_area'] and item['_price']]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, alpha=0.5, s=20,
                       label=region_names[r], color=region_colors[r])
    ax.set_title('价格 vs 面积', fontsize=14)
    ax.set_xlabel('面积 (㎡)')
    ax.set_ylabel('月租金 (元/月)')
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '7_price_vs_area.png', dpi=150)
    plt.close(fig)


def _chart_direction_by_region(data, regions, region_names, region_colors,
                               charts_dir):
    """各区域朝向分布."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))
    all_dirs = Counter(
        item.get('direction', '') for item in data if item.get('direction'))
    top_dirs = [d for d, _ in all_dirs.most_common(8)]
    x = range(len(top_dirs))
    width = 0.15
    for i, r in enumerate(regions):
        r_data = [item for item in data if item.get('region') == r]
        counts = [sum(1 for item in r_data if item.get('direction') == d)
                  for d in top_dirs]
        ax.bar([xi + i * width for xi in x], counts, width,
               label=region_names[r], color=region_colors[r], alpha=0.85)
    ax.set_title('各区域朝向分布', fontsize=14)
    ax.set_xlabel('朝向')
    ax.set_ylabel('房源数量')
    ax.set_xticks([xi + width * (len(regions) - 1) / 2 for xi in x])
    ax.set_xticklabels(top_dirs)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '8_direction_by_region.png', dpi=150)
    plt.close(fig)


def _print_summary(data, regions, region_names):
    """打印统计摘要到控制台和日志."""
    total = len(data)
    logger.info(f"\n{'=' * 60}")
    logger.info(f"数据分析报告 | 总计 {total} 条房源")
    logger.info(f"{'=' * 60}")

    all_prices = []
    all_areas = []

    for r in regions:
        rdata = [d for d in data if d.get('region') == r]
        prices = [d['_price'] for d in rdata if d.get('_price')]
        areas = [d['_area'] for d in rdata if d.get('_area')]
        all_prices.extend(prices)
        all_areas.extend(areas)

        logger.info(f"\n--- {region_names[r]} ({len(rdata)} 条) ---")
        if prices:
            logger.info(
                f"  价格: {min(prices):,} ~ {max(prices):,} 元/月 | "
                f"均价 {sum(prices) / len(prices):,.0f} | "
                f"中位数 {sorted(prices)[len(prices) // 2]:,}")
        if areas:
            logger.info(
                f"  面积: {min(areas):.0f} ~ {max(areas):.0f} ㎡ | "
                f"均面积 {sum(areas) / len(areas):.1f} ㎡")
        rooms = Counter(d.get('rooms', '') for d in rdata if d.get('rooms'))
        if rooms:
            top3 = rooms.most_common(3)
            logger.info(
                f"  户型: {' | '.join(f'{r}({n})' for r, n in top3)}")
        comms = Counter(
            d.get('community', '') for d in rdata if d.get('community'))
        if comms:
            top5 = comms.most_common(5)
            logger.info(
                f"  热门小区: {', '.join(f'{c}({n})' for c, n in top5)}")

    logger.info(f"\n--- 总览 ---")
    if all_prices:
        logger.info(
            f"  价格: {min(all_prices):,} ~ {max(all_prices):,} 元/月 | "
            f"均价 {sum(all_prices) / len(all_prices):,.0f}")
    if all_areas:
        logger.info(
            f"  面积: {min(all_areas):.0f} ~ {max(all_areas):.0f} ㎡ | "
            f"均面积 {sum(all_areas) / len(all_areas):.1f} ㎡")
    comms = Counter(
        d.get('community', '') for d in data if d.get('community'))
    logger.info(f"  涉及小区: {len(comms)} 个")

"""
地图生成模块

静态 PNG 地图 + HTML 交互地图 + 距离报告。
"""

import logging
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scraper.config import (
    DEFAULT_DISTANCE_RINGS,
    DEFAULT_MAX_DISTANCE,
    DEFAULT_MAX_LABELS,
    IMAGE_DPI,
    IMAGE_HEIGHT_INCHES,
    IMAGE_WIDTH_INCHES,
    LABEL_FONT_SIZE,
    OUTPUT_DIR,
    REGIONS,
    RING_COLORS,
    RING_LABELS,
)
from scraper.geo import (
    geocode_community,
    get_geocoder,
    haversine,
    km_to_deg_lat,
    km_to_deg_lng,
)

logger = logging.getLogger('lianjia')

try:
    from adjustText import adjust_text
    HAS_ADJUST_TEXT = True
except ImportError:
    HAS_ADJUST_TEXT = False


def build_community_stats(data):
    """
    按小区聚合: 数量、均价、单价等.

    Args:
        data: 房源数据列表

    Returns:
        dict: { 小区名: { count, avg_price, min_price, max_price, ... } }
    """
    grouped = defaultdict(list)
    for item in data:
        community = item.get("community", "").strip()
        if not community:
            continue
        grouped[community].append(item)

    stats = {}
    for name, items in grouped.items():
        prices, areas = [], []
        for it in items:
            try:
                p = (int(it["price"])
                     if str(it.get("price", "")).isdigit() else None)
                if p:
                    prices.append(p)
            except (ValueError, TypeError):
                pass
            try:
                a = float(it["area"]) if it.get("area") else None
                if a:
                    areas.append(a)
            except (ValueError, TypeError):
                pass

        if not prices:
            continue

        avg_price = sum(prices) / len(prices)
        avg_area = sum(areas) / len(areas) if areas else 0

        stats[name] = {
            "count": len(items),
            "avg_price": round(avg_price),
            "min_price": min(prices),
            "max_price": max(prices),
            "avg_area": round(avg_area, 1),
            "avg_unit_price": (round(avg_price / avg_area, 1)
                               if avg_area > 0 else 0),
            "region": items[0].get("region", ""),
        }
    return stats


def get_ring_color(dist_km, rings=None):
    """
    根据距离获取距离环颜色.

    Args:
        dist_km: 距离 (km)
        rings: 距离环列表

    Returns:
        str: 颜色十六进制值
    """
    if rings is None:
        rings = DEFAULT_DISTANCE_RINGS
    for r in rings:
        if dist_km <= r:
            return RING_COLORS.get(r, "#95a5a6")
    return "#95a5a6"


def generate_static_map(community_stats, workplace,
                        max_distance=DEFAULT_MAX_DISTANCE,
                        max_labels=DEFAULT_MAX_LABELS):
    """
    生成高清可放大 PNG 图片.

    Args:
        community_stats: 小区统计字典
        workplace: 工作地点配置
        max_distance: 最大距离 (km)
        max_labels: 最大标注小区数

    Returns:
        str or None: 生成的图片路径
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import Normalize

    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS", "PingFang SC", "Heiti SC", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False

    rings = [r for r in DEFAULT_DISTANCE_RINGS if r <= max_distance]
    wp_lat = workplace["lat"]
    wp_lng = workplace["lng"]
    wp_name = workplace["name"]

    # 批量地理编码
    geocoder = get_geocoder()
    community_regions = {
        name: stat.get("region", "") for name, stat in community_stats.items()
    }
    geo_coords = geocoder.batch_geocode(community_regions)

    plot_data = []
    for name, stat in community_stats.items():
        coords = geo_coords.get(name)
        if not coords:
            continue
        lat, lng = coords
        dist = haversine(wp_lat, wp_lng, lat, lng)
        if dist <= max_distance:
            plot_data.append((name, lat, lng, dist, stat))

    plot_data.sort(key=lambda x: x[4]["count"])

    if not plot_data:
        logger.error("范围内无小区数据")
        return None

    unit_prices = [s["avg_unit_price"] for _, _, _, _, s in plot_data]
    vmin, vmax = min(unit_prices), max(unit_prices)
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.cm.RdYlGn_r

    # 自动计算显示边界
    all_lats = [lat for _, lat, _, _, _ in plot_data]
    all_lngs = [lng for _, _, lng, _, _ in plot_data]
    lat_min = min(min(all_lats), wp_lat)
    lat_max = max(max(all_lats), wp_lat)
    lng_min = min(min(all_lngs), wp_lng)
    lng_max = max(max(all_lngs), wp_lng)

    lat_span = lat_max - lat_min
    lng_span = lng_max - lng_min
    for r_km in reversed(rings):
        r_lat = km_to_deg_lat(r_km)
        r_lng = km_to_deg_lng(r_km, wp_lat)
        if (lat_span < r_lat * 1.2 and lng_span < r_lng * 1.2):
            lat_min = min(lat_min, wp_lat - r_lat)
            lat_max = max(lat_max, wp_lat + r_lat)
            lng_min = min(lng_min, wp_lng - r_lng)
            lng_max = max(lng_max, wp_lng + r_lng)
            break

    pad_lat = (lat_max - lat_min) * 0.08
    pad_lng = (lng_max - lng_min) * 0.08
    lat_min -= pad_lat
    lat_max += pad_lat
    lng_min -= pad_lng
    lng_max += pad_lng

    cos_lat = math.cos(math.radians(wp_lat))
    aspect = 1.0 / cos_lat
    data_width = (lng_max - lng_min) * aspect
    data_height = lat_max - lat_min
    img_ratio = IMAGE_WIDTH_INCHES / IMAGE_HEIGHT_INCHES
    data_ratio = data_width / data_height
    if data_ratio < img_ratio:
        extra = (data_height * img_ratio - data_width) / (2 * aspect)
        lng_min -= extra
        lng_max += extra
    else:
        extra = (data_width / img_ratio - data_height) / 2
        lat_min -= extra
        lat_max += extra

    fig, ax = plt.subplots(
        figsize=(IMAGE_WIDTH_INCHES, IMAGE_HEIGHT_INCHES), dpi=IMAGE_DPI)
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#f0f0f0")

    # 距离环
    for r_km in rings:
        r_lat = km_to_deg_lat(r_km)
        r_lng = km_to_deg_lng(r_km, wp_lat)
        circle = mpatches.Ellipse(
            (wp_lng, wp_lat), width=r_lng * 2, height=r_lat * 2,
            fill=False, edgecolor=RING_COLORS.get(r_km, "#95a5a6"),
            linewidth=1.0, linestyle="--", alpha=0.5, zorder=1)
        ax.add_patch(circle)

        label_angle = math.radians(40)
        lx = wp_lng + r_lng * math.cos(label_angle)
        ly = wp_lat + r_lat * math.sin(label_angle)
        if lng_min < lx < lng_max and lat_min < ly < lat_max:
            ax.text(lx, ly, f"{r_km}km", fontsize=7,
                    color=RING_COLORS.get(r_km, "#95a5a6"), alpha=0.8,
                    ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white",
                              ec="none", alpha=0.8),
                    zorder=2)

    # 工作地点标记
    ax.plot(wp_lng, wp_lat, marker="*", color="red", markersize=22,
            markeredgecolor="darkred", markeredgewidth=1.5, zorder=10)
    ax.annotate(wp_name, (wp_lng, wp_lat), textcoords="offset points",
                xytext=(18, 18), fontsize=11, fontweight="bold",
                color="darkred",
                bbox=dict(boxstyle="round,pad=0.3", fc="white",
                          ec="red", alpha=0.9),
                zorder=11)

    # 小区散点
    scatter_lngs, scatter_lats, scatter_colors, scatter_sizes = [], [], [], []
    for _name, lat, lng, _dist, stat in plot_data:
        scatter_lats.append(lat)
        scatter_lngs.append(lng)
        scatter_colors.append(cmap(norm(stat["avg_unit_price"])))
        scatter_sizes.append(max(12, min(90, 8 + stat["count"] * 5)))

    ax.scatter(scatter_lngs, scatter_lats, c=scatter_colors,
               s=scatter_sizes, alpha=0.75, edgecolors="white",
               linewidths=0.4, zorder=5)

    # 标签
    labeled = sorted(plot_data, key=lambda x: x[4]["count"],
                     reverse=True)[:max_labels]
    texts = []
    for name, lat, lng, dist, stat in labeled:
        display_name = name if len(name) <= 6 else name[:6] + ".."
        label = f"{display_name} {stat['avg_unit_price']}元/㎡"
        t = ax.text(lng, lat, label, fontsize=LABEL_FONT_SIZE,
                    ha="center", va="bottom", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white",
                              ec="gray", alpha=0.85, linewidth=0.3))
        texts.append(t)

    if HAS_ADJUST_TEXT and texts:
        logger.info(f"  正在调整 {len(texts)} 个标签位置 (防重叠)...")
        adjust_text(texts, x=scatter_lngs, y=scatter_lats,
                    avoid_self=True, force_text=(0.5, 0.8),
                    force_points=(0.3, 0.3), force_objects=(0.2, 0.2),
                    lim=500,
                    arrowprops=dict(arrowstyle="-", color="gray",
                                    lw=0.3, alpha=0.4),
                    autoalign="xy",
                    only_move={"points": "xy", "text": "xy"})
    elif texts:
        logger.info("  提示: pip install adjustText 可获得更好的标签防重叠效果")

    # 色阶条
    from matplotlib.cm import ScalarMappable
    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, aspect=30, pad=0.02)
    cbar.set_label("平均单价 (元/㎡/月)", fontsize=9)
    cbar.ax.tick_params(labelsize=7)

    # 图例
    legend_handles = []
    for r_km in rings:
        legend_handles.append(mpatches.Patch(
            edgecolor=RING_COLORS.get(r_km, "#95a5a6"), facecolor="none",
            linestyle="--", label=f"{r_km}km"))
    legend_handles.append(plt.Line2D(
        [0], [0], marker="*", color="w", markerfacecolor="red",
        markersize=12, label=wp_name))
    for cnt, label in [(3, "3套"), (10, "10套"), (20, "20套+")]:
        sz = math.sqrt(max(12, 8 + cnt * 5))
        legend_handles.append(plt.Line2D(
            [0], [0], marker="o", color="w", markerfacecolor="gray",
            markersize=sz, label=label))
    ax.legend(handles=legend_handles, loc="upper left", fontsize=7,
              framealpha=0.9, title="图例", title_fontsize=8)

    # 标题
    geo_source = ("腾讯位置服务" if geocoder.has_api()
                  else "哈希散布(近似)")
    ax.set_title(
        f"{wp_name} 周边 {max_distance:.0f}km 租房单价地图\n"
        f"共 {len(plot_data)} 个小区 | 标注 {len(labeled)} 个 | "
        f"单价 {vmin:.0f}~{vmax:.0f} 元/㎡/月 | 坐标来源: {geo_source}",
        fontsize=13, fontweight="bold", pad=15)
    ax.set_xlabel("经度", fontsize=9)
    ax.set_ylabel("纬度", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.set_xlim(lng_min, lng_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(aspect)
    ax.grid(True, alpha=0.2, linewidth=0.5)

    # 保存
    output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = wp_name.replace(" ", "_")
    filepath = output_dir / f"community_map_{safe_name}_{timestamp}.png"
    fig.savefig(filepath, dpi=IMAGE_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    px_w = int(IMAGE_WIDTH_INCHES * IMAGE_DPI)
    px_h = int(IMAGE_HEIGHT_INCHES * IMAGE_DPI)
    logger.info(f"\n图片已生成: {filepath}")
    logger.info(f"  分辨率: {px_w} x {px_h} 像素")
    logger.info(f"  标注: {len(labeled)}/{len(plot_data)} 个小区")
    logger.info(f"  单价范围: {vmin:.0f} ~ {vmax:.0f} 元/㎡/月")

    return str(filepath)


def generate_html_map(community_stats, workplace,
                      max_distance=DEFAULT_MAX_DISTANCE):
    """
    生成交互式 HTML 地图 (folium).

    Args:
        community_stats: 小区统计字典
        workplace: 工作地点配置
        max_distance: 最大距离 (km)
    """
    try:
        import folium
    except ImportError:
        logger.info("跳过 HTML 地图 (需 pip install folium)")
        return

    rings = DEFAULT_DISTANCE_RINGS
    wp_lat, wp_lng = workplace["lat"], workplace["lng"]
    wp_name = workplace["name"]

    m = folium.Map(location=[wp_lat, wp_lng], zoom_start=12,
                   tiles="OpenStreetMap")

    folium.Marker(
        location=[wp_lat, wp_lng],
        popup=f"<b>{wp_name}</b><br>{workplace.get('address', '')}",
        tooltip=wp_name,
        icon=folium.Icon(color="red", icon="briefcase", prefix="fa"),
    ).add_to(m)

    for r_km in rings:
        if r_km > max_distance:
            break
        folium.Circle(
            location=[wp_lat, wp_lng], radius=r_km * 1000,
            color=RING_COLORS.get(r_km, "#95a5a6"), fill=False,
            weight=1.5, opacity=0.6, dash_array="5,5",
        ).add_to(m)

    for name, stat in community_stats.items():
        coords = geocode_community(name, stat.get("region", ""))
        if not coords:
            continue
        lat, lng = coords
        dist = haversine(wp_lat, wp_lng, lat, lng)
        if dist > max_distance:
            continue
        color = get_ring_color(dist, rings)
        radius = max(4, min(15, 3 + stat["count"]))
        popup = (
            f"<b>{name}</b><br>距 {wp_name}: {dist:.1f}km<br>"
            f"房源: {stat['count']}套 | 均{stat['avg_price']:,}元/月<br>"
            f"单价: {stat['avg_unit_price']}元/㎡/月 | "
            f"均面积: {stat['avg_area']}㎡"
        )
        folium.CircleMarker(
            location=[lat, lng], radius=radius,
            popup=folium.Popup(popup, max_width=300),
            tooltip=f"{name} ({dist:.1f}km)",
            color=color, fill=True, fill_color=color,
            fill_opacity=0.6, weight=1,
        ).add_to(m)

    output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"community_map_{wp_name}_{timestamp}.html"
    m.save(str(filepath))
    logger.info(f"HTML 地图: {filepath}")


def print_distance_report(community_stats, workplace, max_distance):
    """
    打印按距离分层的小区统计.

    Args:
        community_stats: 小区统计字典
        workplace: 工作地点配置
        max_distance: 最大距离 (km)
    """
    wp_lat, wp_lng = workplace["lat"], workplace["lng"]
    wp_name = workplace["name"]

    logger.info(f"\n{'=' * 70}")
    logger.info(f"小区通勤距离报告 — 工作地点: {wp_name}")
    logger.info(f"{'=' * 70}")

    results = []
    for name, stat in community_stats.items():
        coords = geocode_community(name, stat.get("region", ""))
        if not coords:
            continue
        lat, lng = coords
        dist = haversine(wp_lat, wp_lng, lat, lng)
        results.append((name, dist, stat))
    results.sort(key=lambda x: x[1])

    prev = 0
    for ring_km in DEFAULT_DISTANCE_RINGS:
        if ring_km > max_distance:
            break
        group = [(n, d, s) for n, d, s in results if prev < d <= ring_km]
        if group:
            label = RING_LABELS.get((prev, ring_km), f"{prev}-{ring_km}km")
            print(f"\n--- {label} ({len(group)} 个小区) ---")
            print(f"{'小区名':<25} {'距离':>6} {'套数':>4} "
                  f"{'均价':>8} {'单价':>8}")
            print("-" * 70)
            for name, dist, stat in sorted(
                    group, key=lambda x: x[2]["avg_unit_price"]):
                dn = name[:22] + "..." if len(name) > 22 else name
                print(f"{dn:<25} {dist:>5.1f}km {stat['count']:>4} "
                      f"{stat['avg_price']:>7,}元 "
                      f"{stat['avg_unit_price']:>7.1f}元/㎡")
        prev = ring_km

    outside = [(n, d, s) for n, d, s in results if d > max_distance]
    if outside:
        print(f"\n--- 超出 {max_distance}km ({len(outside)} 个小区) ---")

    in_range = [(n, d, s) for n, d, s in results if d <= max_distance]
    if in_range:
        prices = [s["avg_price"] for _, _, s in in_range]
        units = [s["avg_unit_price"] for _, _, s in in_range]
        print(f"\n--- 汇总 ({len(in_range)} 个小区在 "
              f"{max_distance:.0f}km 内) ---")
        print(f"  平均月租金: {sum(prices) // len(prices):,} 元")
        print(f"  平均单价: {sum(units) / len(units):.1f} 元/㎡/月")

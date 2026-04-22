#!/usr/bin/env python3
"""
链家小区单价地图生成器

以指定工作地点为圆心，按通勤距离分层展示各小区月租金单价。
支持中文输入工作地点名称（模糊匹配），输出高清可放大图片。

小区坐标通过腾讯位置服务 WebService API 获取精确经纬度，
结果自动缓存到本地 JSON 文件，同一小区仅调用一次 API。

使用方法:
    python3 community_geo_map.py                              # 默认张江国创中心
    python3 community_geo_map.py --workplace 张江国创          # 中文模糊匹配
    python3 community_geo_map.py --workplace 金桥
    python3 community_geo_map.py --workplace 唐镇 --max-distance 15
    python3 community_geo_map.py --workplace 31.22,121.54 --workplace-name "我的公司"
    python3 community_geo_map.py --max-labels 0               # 标注全部小区
    python3 community_geo_map.py --dry-run                    # 仅打印报告
    python3 community_geo_map.py --refresh-geo                # 强制刷新所有小区坐标

配置说明:
    腾讯位置服务 API 密钥通过以下方式配置（优先级从高到低）：
    1. 环境变量 TENCENT_MAP_KEY / TENCENT_MAP_SK
    2. 脚本同目录下的 .env 文件
    参考 .env.example 获取配置模板。

坐标来源 (WGS-84):
    - 张江国创中心: 百度地图拾取, 丹桂路899号 (31.2033, 121.5905)
    - 金桥开发区: maps4gis.com (31.2475, 121.6282)
    - 唐镇: Tageo + 百度百科交叉验证 (31.2150, 121.6550)
    - 川沙: 百度地图拾取 (31.1900, 121.7000)

依赖:
    pip install matplotlib folium
    可选: pip install adjustText  (标签防重叠效果更好)
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# ============================================================
# 配置区域 — 可直接修改此处的值
# ============================================================

SCRIPT_DIR = Path(__file__).parent

# ---------- 工作地点配置 ----------
# name: 显示名, lat: 纬度, lng: 经度 (WGS-84)
# 新增工作地点只需在此添加一条记录，命令行即可用中文名引用
WORKPLACES = {
    "zhangjiang": {
        "name": "张江国创中心",
        "lat": 31.2033,
        "lng": 121.5905,
        "address": "浦东新区丹桂路899号",
    },
    "zhangjiang_2": {
        "name": "张江国创二期",
        "lat": 31.219406,
        "lng": 121.627225,
        "address": "浦东新区张江国创中心二期",
    },
    "jinqiao": {
        "name": "金桥开发区",
        "lat": 31.2475,
        "lng": 121.6282,
        "address": "浦东新区金桥经济技术开发区",
    },
    "tangzhen": {
        "name": "唐镇",
        "lat": 31.2150,
        "lng": 121.6550,
        "address": "浦东新区唐镇中心",
    },
    "chuansha": {
        "name": "川沙",
        "lat": 31.1900,
        "lng": 121.7000,
        "address": "浦东新区川沙新镇",
    },
}

DEFAULT_WORKPLACE = "张江国创"
DEFAULT_MAX_DISTANCE = 15
DEFAULT_DISTANCE_RINGS = [3, 5, 8, 10, 15]
DEFAULT_MAX_LABELS = 200

# ---------- 区域中心坐标 & 散布半径 ----------
REGION_CENTERS = {
    "zhangjiang": (31.2033, 121.5905),
    "jinqiao": (31.2475, 121.6282),
    "tangzhen": (31.2150, 121.6550),
    "chuansha": (31.1900, 121.7000),
    "changning": (31.2200, 121.4250),
}

# 每个区域小区坐标的散布半径 (km) — 仅作为哈希散布的备用
REGION_SPREAD_KM = {
    "zhangjiang": 4.0,
    "jinqiao": 4.5,
    "tangzhen": 4.0,
    "chuansha": 4.5,
    "changning": 5.0,
}

# ---------- 距离环颜色 & 标签 ----------
RING_COLORS = {
    3: "#2ecc71",
    5: "#27ae60",
    8: "#f39c12",
    10: "#e67e22",
    15: "#e74c3c",
    20: "#c0392b",
}

RING_LABELS = {
    (0, 3): "0-3km 步行可达",
    (3, 5): "3-5km 骑行/短途",
    (5, 8): "5-8km 短途公交",
    (8, 10): "8-10km 公交",
    (10, 15): "10-15km 需地铁",
}

# ---------- 图片输出配置 ----------
IMAGE_DPI = 200
IMAGE_WIDTH_INCHES = 28
IMAGE_HEIGHT_INCHES = 22
LABEL_FONT_SIZE = 5.5

# ---------- 地理编码缓存文件 ----------
GEO_CACHE_FILE = SCRIPT_DIR / "output" / "community_geo_cache.json"

# ---------- 腾讯位置服务 API ----------
TENCENT_GEOCODER_URL = "https://apis.map.qq.com/ws/geocoder/v1"
TENCENT_GEO_BATCH_INTERVAL = 0.15  # 两次 API 调用之间的间隔 (秒)


# ============================================================
# 腾讯位置服务配置加载
# ============================================================


def _load_tencent_config():
    """
    加载腾讯位置服务 API 密钥。

    优先级: 环境变量 > .env 文件
    返回 (key, sk)，未配置时返回 (None, None)。
    """
    key = os.environ.get("TENCENT_MAP_KEY")
    sk = os.environ.get("TENCENT_MAP_SK")

    if key and sk:
        return key, sk

    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "TENCENT_MAP_KEY" and not key:
                key = v
            elif k == "TENCENT_MAP_SK" and not sk:
                sk = v

    return key, sk


# ============================================================
# 地理编码: 腾讯位置服务 API + 本地缓存
# ============================================================


class GeoCoder:
    """
    小区地理编码器。

    - 优先从本地 JSON 缓存读取坐标
    - 缓存未命中时调用腾讯位置服务 API
    - 同一小区只调用一次 API，结果持久化到缓存文件
    - 未配置 API 密钥时回退到哈希散布算法
    """

    def __init__(self):
        self._cache = {}
        self._cache_dirty = False
        self._api_key, self._api_sk = _load_tencent_config()
        self._load_cache()

    def _load_cache(self):
        """从磁盘加载缓存。"""
        if GEO_CACHE_FILE.exists():
            try:
                self._cache = json.loads(GEO_CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self):
        """将缓存写入磁盘。"""
        if not self._cache_dirty:
            return
        GEO_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GEO_CACHE_FILE.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache_dirty = False

    def _calc_sig(self, uri, params):
        """
        计算腾讯位置服务 API 签名。

        算法: sig = MD5(basicString + SK)
        basicString = uri + "?" + 按参数名字典序排列的原始键值对 (不做 URL 编码)
        """
        sorted_params = "&".join(
            f"{k}={params[k]}" for k in sorted(params.keys())
        )
        basic_string = f"{uri}?{sorted_params}"
        return hashlib.md5((basic_string + self._api_sk).encode("utf-8")).hexdigest()

    def _api_geocode(self, address):
        """
        调用腾讯位置服务地理编码 API。

        返回 (lat, lng) 或 None。
        """
        if not self._api_key:
            return None

        uri = "/ws/geocoder/v1"
        params = {
            "address": address,
            "key": self._api_key,
            "output": "json",
        }
        sig = self._calc_sig(uri, params)

        # 构建 URL: 参数值需 URL 编码，sig 参数不参与编码
        encoded_params = "&".join(
            f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items())
        )
        url = f"https://apis.map.qq.com{uri}?{encoded_params}&sig={sig}"

        import ssl
        import urllib.request

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == 0:
                loc = data.get("result", {}).get("location", {})
                lat = loc.get("lat")
                lng = loc.get("lng")
                if lat and lng:
                    return (lat, lng)
        except Exception as e:
            print(f"  地理编码 API 调用失败 ({address}): {e}")

        return None

    def _hash_geocode(self, name, region=""):
        """备用: 确定性哈希散布算法 (无 API 时使用)。"""
        center_lat, center_lng = REGION_CENTERS.get(region, (31.21, 121.60))
        spread = REGION_SPREAD_KM.get(region, 3.0)

        h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:12], 16)
        n = h % 100000

        golden_angle = 2.39996322
        angle = n * golden_angle
        r = math.sqrt((n % 10000) / 10000.0) * spread

        lat = center_lat + r * math.cos(angle) / 111.0
        lng = center_lng + r * math.sin(angle) / (
            111.0 * math.cos(math.radians(center_lat))
        )
        return (lat, lng)

    def geocode(self, name, region=""):
        """
        获取小区坐标。

        查找顺序: 内存缓存 → API 调用 → 哈希散布备用。
        同一 name 只调用一次 API，后续从缓存读取。
        """
        cache_key = name
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            return (entry["lat"], entry["lng"])

        # 尝试 API
        coords = self._api_geocode(f"上海{name}")
        if coords:
            self._cache[cache_key] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": "tencent",
            }
            self._cache_dirty = True
            return coords

        # 回退到哈希散布
        coords = self._hash_geocode(name, region)
        self._cache[cache_key] = {
            "lat": coords[0],
            "lng": coords[1],
            "source": "hash",
        }
        self._cache_dirty = True
        return coords

    def batch_geocode(self, community_regions):
        """
        批量地理编码: 对去重后的小区名逐一调用。

        Args:
            community_regions: dict { community_name: region }

        Returns:
            dict { community_name: (lat, lng) }
        """
        results = {}
        to_fetch = []

        # 第一轮: 从缓存命中
        for name, region in community_regions.items():
            if name in self._cache:
                entry = self._cache[name]
                results[name] = (entry["lat"], entry["lng"])
            else:
                to_fetch.append((name, region))

        if not to_fetch:
            return results

        api_mode = "API" if self._api_key else "哈希散布(未配置API密钥)"
        print(f"  地理编码: 缓存命中 {len(results)}/{len(community_regions)}, "
              f"待处理 {len(to_fetch)} ({api_mode})")

        # 第二轮: API 调用（带限速）
        for i, (name, region) in enumerate(to_fetch):
            coords = self.geocode(name, region)
            results[name] = coords
            if i < len(to_fetch) - 1 and self._api_key:
                time.sleep(TENCENT_GEO_BATCH_INTERVAL)
            if (i + 1) % 20 == 0:
                print(f"    进度: {i + 1}/{len(to_fetch)}")
                self._save_cache()

        self._save_cache()
        return results

    def clear_cache(self):
        """清空缓存。"""
        self._cache = {}
        self._cache_dirty = False
        if GEO_CACHE_FILE.exists():
            GEO_CACHE_FILE.unlink()

    def has_api(self):
        """是否配置了腾讯位置服务 API。"""
        return bool(self._api_key)


# 全局单例
_geocoder = GeoCoder()


def geocode_community(name, region=""):
    """获取小区坐标 (兼容旧接口)。"""
    return _geocoder.geocode(name, region)


# ============================================================
# 工具函数
# ============================================================


def haversine(lat1, lon1, lat2, lon2):
    """Haversine 公式计算两点间距离 (km)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def km_to_deg_lat(km):
    """km → 纬度差 (1° ≈ 111km)."""
    return km / 111.0


def km_to_deg_lng(km, lat):
    """km → 经度差 (含纬度修正)."""
    return km / (111.0 * math.cos(math.radians(lat)))


def load_data(filepath):
    """加载 JSON 或 CSV 数据文件."""
    path = Path(filepath)
    if not path.exists():
        path = SCRIPT_DIR / filepath
    if not path.exists():
        print(f"错误: 文件不存在 — {filepath}")
        sys.exit(1)

    print(f"加载数据: {path}")
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix == ".json":
            return json.load(f)
        elif path.suffix == ".csv":
            import csv

            return list(csv.DictReader(f))
        print(f"错误: 不支持 {path.suffix} 格式")
        sys.exit(1)


def find_latest_data():
    """在 output/ 下查找最新爬取数据."""
    output_dir = SCRIPT_DIR / "output"
    if not output_dir.exists():
        print(f"错误: output 目录不存在 — {output_dir}")
        print("请先运行: python lianjia_scraper.py --areas all")
        sys.exit(1)

    for pattern in ["lianjia_all_*.json", "lianjia_*_*.json"]:
        files = sorted(output_dir.glob(pattern), reverse=True)
        if files:
            return files[0]

    print("错误: 未找到数据文件，请先运行爬虫")
    sys.exit(1)


def get_workplace(key):
    """
    获取工作地点配置，支持:
      - 拼音 key: zhangjiang, jinqiao, tangzhen, chuansha
      - 中文模糊匹配: "张江" → 张江国创中心, "金桥" → 金桥开发区
      - 坐标: "31.22,121.54"
    """
    # 1. 精确匹配 key
    if key in WORKPLACES:
        return dict(WORKPLACES[key])

    # 2. 中文模糊匹配: 输入是名称的子串，或名称以输入开头
    for wp in WORKPLACES.values():
        if key in wp["name"] or wp["name"].startswith(key):
            return dict(wp)

    # 3. 坐标格式 "lat,lng"
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

    # 4. 未匹配
    print(f'错误: 未匹配工作地点 — "{key}"')
    print("可选:")
    for k, v in WORKPLACES.items():
        print(f"  {v['name']}  (或 {k})")
    print('或使用坐标: --workplace "31.22,121.54"')
    sys.exit(1)


# ============================================================
# 数据聚合
# ============================================================


def build_community_stats(data):
    """按小区聚合: 数量、均价、单价等."""
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
                p = int(it["price"]) if str(it.get("price", "")).isdigit() else None
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
            "avg_unit_price": round(avg_price / avg_area, 1) if avg_area > 0 else 0,
            "region": items[0].get("region", ""),
        }
    return stats


def get_ring_color(dist_km, rings=None):
    """根据距离获取距离环颜色."""
    if rings is None:
        rings = DEFAULT_DISTANCE_RINGS
    for r in rings:
        if dist_km <= r:
            return RING_COLORS.get(r, "#95a5a6")
    return "#95a5a6"


# ============================================================
# 静态图片生成（核心功能）
# ============================================================

try:
    from adjustText import adjust_text

    HAS_ADJUST_TEXT = True
except ImportError:
    HAS_ADJUST_TEXT = False


def generate_static_map(
    community_stats,
    workplace,
    max_distance=DEFAULT_MAX_DISTANCE,
    max_labels=DEFAULT_MAX_LABELS,
):
    """
    生成高清可放大 PNG 图片.

    特性:
      - 以工作地点为圆心，同心圆显示距离环
      - 圆点表示小区，颜色映射单价（绿=便宜, 红=贵）
      - 圆点大小按房源数量缩放
      - 标注小区名 + 单价（adjustText 自动防重叠）
      - 自动裁剪到有数据的区域，不留空白
      - 高分辨率输出，可放大查看细节
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.colors import Normalize

    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS",
        "PingFang SC",
        "Heiti SC",
        "SimHei",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    rings = [r for r in DEFAULT_DISTANCE_RINGS if r <= max_distance]
    wp_lat = workplace["lat"]
    wp_lng = workplace["lng"]
    wp_name = workplace["name"]

    # ---- 批量地理编码 ----
    community_regions = {
        name: stat.get("region", "") for name, stat in community_stats.items()
    }
    geo_coords = _geocoder.batch_geocode(community_regions)

    # ---- 准备数据 ----
    plot_data = []
    for name, stat in community_stats.items():
        lat, lng = geo_coords.get(name, geocode_community(name, stat.get("region", "")))
        dist = haversine(wp_lat, wp_lng, lat, lng)
        if dist <= max_distance:
            plot_data.append((name, lat, lng, dist, stat))

    # 按房源数升序排列，多的后画（覆盖少的，保证大数据点在上层）
    plot_data.sort(key=lambda x: x[4]["count"])

    if not plot_data:
        print("错误: 范围内无小区数据")
        return

    # ---- 颜色映射 ----
    unit_prices = [s["avg_unit_price"] for _, _, _, _, s in plot_data]
    vmin, vmax = min(unit_prices), max(unit_prices)
    norm = Normalize(vmin=vmin, vmax=vmax)
    cmap = plt.cm.RdYlGn_r  # 红=贵, 绿=便宜

    # ---- 自动计算显示边界（按实际数据范围裁剪，不留空白） ----
    all_lats = [lat for _, lat, _, _, _ in plot_data]
    all_lngs = [lng for _, _, lng, _, _ in plot_data]
    data_lat_min, data_lat_max = min(all_lats), max(all_lats)
    data_lng_min, data_lng_max = min(all_lngs), max(all_lngs)

    # 确保工作地点在视野内
    lat_min = min(data_lat_min, wp_lat)
    lat_max = max(data_lat_max, wp_lat)
    lng_min = min(data_lng_min, wp_lng)
    lng_max = max(data_lng_max, wp_lng)

    # 确保最大距离环至少部分可见（如果数据很集中，扩展到最近的环）
    lat_span = lat_max - lat_min
    lng_span = lng_max - lng_min
    for r_km in reversed(rings):
        r_lat = km_to_deg_lat(r_km)
        r_lng = km_to_deg_lng(r_km, wp_lat)
        ring_span_lat = r_lat * 2
        ring_span_lng = r_lng * 2
        # 只在数据跨度不到此环直径的 60% 时扩展
        if lat_span < ring_span_lat * 0.6 and lng_span < ring_span_lng * 0.6:
            lat_min = min(lat_min, wp_lat - r_lat)
            lat_max = max(lat_max, wp_lat + r_lat)
            lng_min = min(lng_min, wp_lng - r_lng)
            lng_max = max(lng_max, wp_lng + r_lng)
            break

    # 加 8% 留白
    pad_lat = (lat_max - lat_min) * 0.08
    pad_lng = (lng_max - lng_min) * 0.08
    lat_min -= pad_lat
    lat_max += pad_lat
    lng_min -= pad_lng
    lng_max += pad_lng

    # 保持经纬度等比例（1km 在屏幕上纵横向等长）
    cos_lat = math.cos(math.radians(wp_lat))
    aspect = 1.0 / cos_lat  # lng/lat 显示比例修正

    data_width = (lng_max - lng_min) * aspect
    data_height = lat_max - lat_min
    # 保证宽高比与图像一致，短边扩展
    img_ratio = IMAGE_WIDTH_INCHES / IMAGE_HEIGHT_INCHES
    data_ratio = data_width / data_height
    if data_ratio < img_ratio:
        # 数据偏窄 → 扩展经度
        extra = (data_height * img_ratio - data_width) / (2 * aspect)
        lng_min -= extra
        lng_max += extra
    else:
        # 数据偏矮 → 扩展纬度
        extra = (data_width / img_ratio - data_height) / 2
        lat_min -= extra
        lat_max += extra

    # ---- 创建图形 ----
    fig, ax = plt.subplots(
        figsize=(IMAGE_WIDTH_INCHES, IMAGE_HEIGHT_INCHES), dpi=IMAGE_DPI
    )
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#f0f0f0")

    # ---- 距离环（只画在数据范围内的部分） ----
    for r_km in rings:
        r_lat = km_to_deg_lat(r_km)
        r_lng = km_to_deg_lng(r_km, wp_lat)
        circle = mpatches.Ellipse(
            (wp_lng, wp_lat),
            width=r_lng * 2,
            height=r_lat * 2,
            fill=False,
            edgecolor=RING_COLORS.get(r_km, "#95a5a6"),
            linewidth=1.0,
            linestyle="--",
            alpha=0.5,
            zorder=1,
        )
        ax.add_patch(circle)

        # 环上标注距离（放在右上 45° 方向，但确保在视野内）
        label_angle = math.radians(40)
        lx = wp_lng + r_lng * math.cos(label_angle)
        ly = wp_lat + r_lat * math.sin(label_angle)
        if lng_min < lx < lng_max and lat_min < ly < lat_max:
            ax.text(
                lx,
                ly,
                f"{r_km}km",
                fontsize=7,
                color=RING_COLORS.get(r_km, "#95a5a6"),
                alpha=0.8,
                ha="center",
                va="center",
                bbox=dict(
                    boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8
                ),
                zorder=2,
            )

    # ---- 工作地点标记 ----
    ax.plot(
        wp_lng,
        wp_lat,
        marker="*",
        color="red",
        markersize=22,
        markeredgecolor="darkred",
        markeredgewidth=1.5,
        zorder=10,
    )
    ax.annotate(
        wp_name,
        (wp_lng, wp_lat),
        textcoords="offset points",
        xytext=(18, 18),
        fontsize=11,
        fontweight="bold",
        color="darkred",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="red", alpha=0.9),
        zorder=11,
    )

    # ---- 小区散点（点稍小以减少遮挡） ----
    scatter_lngs, scatter_lats, scatter_colors, scatter_sizes = [], [], [], []
    for _name, lat, lng, _dist, stat in plot_data:
        scatter_lats.append(lat)
        scatter_lngs.append(lng)
        scatter_colors.append(cmap(norm(stat["avg_unit_price"])))
        scatter_sizes.append(max(12, min(90, 8 + stat["count"] * 5)))

    ax.scatter(
        scatter_lngs,
        scatter_lats,
        c=scatter_colors,
        s=scatter_sizes,
        alpha=0.75,
        edgecolors="white",
        linewidths=0.4,
        zorder=5,
    )

    # ---- 标签（按房源数取 top N，多的优先标注） ----
    labeled = sorted(plot_data, key=lambda x: x[4]["count"], reverse=True)[
        :max_labels
    ]
    texts = []
    for name, lat, lng, dist, stat in labeled:
        # 小区名超过10个字截断
        display_name = name if len(name) <= 6 else name[:6] + ".."
        label = f"{display_name} {stat['avg_unit_price']}元/㎡"
        t = ax.text(
            lng,
            lat,
            label,
            fontsize=LABEL_FONT_SIZE,
            ha="center",
            va="bottom",
            zorder=8,
            bbox=dict(
                boxstyle="round,pad=0.15",
                fc="white",
                ec="gray",
                alpha=0.85,
                linewidth=0.3,
            ),
        )
        texts.append(t)

    # adjustText 防重叠
    if HAS_ADJUST_TEXT and texts:
        print(f"  正在调整 {len(texts)} 个标签位置 (防重叠)...")
        adjust_text(
            texts,
            x=scatter_lngs,
            y=scatter_lats,
            avoid_self=True,
            force_text=(0.5, 0.8),
            force_points=(0.3, 0.3),
            force_objects=(0.2, 0.2),
            lim=500,
            arrowprops=dict(arrowstyle="-", color="gray", lw=0.3, alpha=0.4),
            autoalign="xy",
            only_move={"points": "xy", "text": "xy"},
        )
    elif texts:
        print(f"  提示: pip install adjustText 可获得更好的标签防重叠效果")

    # ---- 色阶条 ----
    from matplotlib.cm import ScalarMappable

    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, aspect=30, pad=0.02)
    cbar.set_label("平均单价 (元/㎡/月)", fontsize=9)
    cbar.ax.tick_params(labelsize=7)

    # ---- 图例 ----
    legend_handles = []
    for r_km in rings:
        legend_handles.append(
            mpatches.Patch(
                edgecolor=RING_COLORS.get(r_km, "#95a5a6"),
                facecolor="none",
                linestyle="--",
                label=f"{r_km}km",
            )
        )
    legend_handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="*",
            color="w",
            markerfacecolor="red",
            markersize=12,
            label=wp_name,
        )
    )
    for cnt, label in [(3, "3套"), (10, "10套"), (20, "20套+")]:
        sz = math.sqrt(max(12, 8 + cnt * 5))
        legend_handles.append(
            plt.Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gray",
                markersize=sz,
                label=label,
            )
        )
    ax.legend(
        handles=legend_handles,
        loc="upper left",
        fontsize=7,
        framealpha=0.9,
        title="图例",
        title_fontsize=8,
    )

    # ---- 标题 & 轴 ----
    geo_source = "腾讯位置服务" if _geocoder.has_api() else "哈希散布(近似)"
    ax.set_title(
        f"{wp_name} 周边 {max_distance:.0f}km 租房单价地图\n"
        f"共 {len(plot_data)} 个小区 | 标注 {len(labeled)} 个 | "
        f"单价 {vmin:.0f}~{vmax:.0f} 元/㎡/月 | 坐标来源: {geo_source}",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("经度", fontsize=9)
    ax.set_ylabel("纬度", fontsize=9)
    ax.tick_params(labelsize=7)

    # 设置裁剪后的显示范围
    ax.set_xlim(lng_min, lng_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect(aspect)
    ax.grid(True, alpha=0.2, linewidth=0.5)

    # ---- 保存 ----
    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = wp_name.replace(" ", "_")
    filepath = output_dir / f"community_map_{safe_name}_{timestamp}.png"
    fig.savefig(
        filepath,
        dpi=IMAGE_DPI,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)

    px_w = int(IMAGE_WIDTH_INCHES * IMAGE_DPI)
    px_h = int(IMAGE_HEIGHT_INCHES * IMAGE_DPI)
    print(f"\n图片已生成: {filepath}")
    print(
        f"  分辨率: {px_w} x {px_h} 像素 "
        f"({IMAGE_WIDTH_INCHES}x{IMAGE_HEIGHT_INCHES} @ {IMAGE_DPI}DPI)"
    )
    print(f"  标注: {len(labeled)}/{len(plot_data)} 个小区")
    print(f"  单价范围: {vmin:.0f} ~ {vmax:.0f} 元/㎡/月")

    return str(filepath)


# ============================================================
# HTML 交互地图（补充输出）
# ============================================================


def generate_html_map(community_stats, workplace, max_distance=DEFAULT_MAX_DISTANCE):
    """生成交互式 HTML 地图 (folium), 需 pip install folium."""
    try:
        import folium
    except ImportError:
        print("跳过 HTML 地图 (需 pip install folium)")
        return

    rings = DEFAULT_DISTANCE_RINGS
    wp_lat, wp_lng = workplace["lat"], workplace["lng"]
    wp_name = workplace["name"]

    m = folium.Map(location=[wp_lat, wp_lng], zoom_start=12, tiles="OpenStreetMap")

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
            location=[wp_lat, wp_lng],
            radius=r_km * 1000,
            color=RING_COLORS.get(r_km, "#95a5a6"),
            fill=False,
            weight=1.5,
            opacity=0.6,
            dash_array="5,5",
        ).add_to(m)

    for name, stat in community_stats.items():
        lat, lng = geocode_community(name, stat.get("region", ""))
        dist = haversine(wp_lat, wp_lng, lat, lng)
        if dist > max_distance:
            continue
        color = get_ring_color(dist, rings)
        radius = max(4, min(15, 3 + stat["count"]))
        popup = (
            f"<b>{name}</b><br>距 {wp_name}: {dist:.1f}km<br>"
            f"房源: {stat['count']}套 | 均{stat['avg_price']:,}元/月<br>"
            f"单价: {stat['avg_unit_price']}元/㎡/月 | 均面积: {stat['avg_area']}㎡"
        )
        folium.CircleMarker(
            location=[lat, lng],
            radius=radius,
            popup=folium.Popup(popup, max_width=300),
            tooltip=f"{name} ({dist:.1f}km)",
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            weight=1,
        ).add_to(m)

    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"community_map_{wp_name}_{timestamp}.html"
    m.save(str(filepath))
    print(f"HTML 地图: {filepath}")


# ============================================================
# 控制台报告
# ============================================================


def print_distance_report(community_stats, workplace, max_distance):
    """打印按距离分层的小区统计."""
    wp_lat, wp_lng = workplace["lat"], workplace["lng"]
    wp_name = workplace["name"]

    print(f"\n{'=' * 70}")
    print(f"小区通勤距离报告 — 工作地点: {wp_name}")
    print(f"{'=' * 70}")

    results = []
    for name, stat in community_stats.items():
        lat, lng = geocode_community(name, stat.get("region", ""))
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
            print(f"{'小区名':<25} {'距离':>6} {'套数':>4} {'均价':>8} {'单价':>8}")
            print("-" * 70)
            for name, dist, stat in sorted(
                group, key=lambda x: x[2]["avg_unit_price"]
            ):
                dn = name[:22] + "..." if len(name) > 22 else name
                print(
                    f"{dn:<25} {dist:>5.1f}km {stat['count']:>4} "
                    f"{stat['avg_price']:>7,}元 {stat['avg_unit_price']:>7.1f}元/㎡"
                )
        prev = ring_km

    outside = [(n, d, s) for n, d, s in results if d > max_distance]
    if outside:
        print(f"\n--- 超出 {max_distance}km ({len(outside)} 个小区) ---")

    in_range = [(n, d, s) for n, d, s in results if d <= max_distance]
    if in_range:
        prices = [s["avg_price"] for _, _, s in in_range]
        units = [s["avg_unit_price"] for _, _, s in in_range]
        print(f"\n--- 汇总 ({len(in_range)} 个小区在 {max_distance:.0f}km 内) ---")
        print(f"  平均月租金: {sum(prices) // len(prices):,} 元")
        print(f"  平均单价: {sum(units) / len(units):.1f} 元/㎡/月")


# ============================================================
# 主函数
# ============================================================


def main():
    wp_list = "\n".join(f"  {v['name']}  (或 {k})" for k, v in WORKPLACES.items())
    parser = argparse.ArgumentParser(
        description="链家小区单价地图生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
预定义工作地点 (支持中文名模糊匹配):
{wp_list}

示例:
  python %(prog)s                              # 默认张江
  python %(prog)s --workplace 张江国创
  python %(prog)s --workplace 金桥 --max-distance 15
  python %(prog)s --workplace "31.22,121.54" --workplace-name "我的公司"
  python %(prog)s --max-labels 0               # 标注全部小区
  python %(prog)s --dry-run
  python %(prog)s --refresh-geo                # 强制刷新小区坐标
        """,
    )

    parser.add_argument(
        "--workplace",
        type=str,
        default=DEFAULT_WORKPLACE,
        help="工作地点 (中文名/拼音key/经纬度)",
    )
    parser.add_argument("--workplace-name", type=str, default=None, help="自定义显示名")
    parser.add_argument("--data", type=str, default=None, help="数据文件路径 (默认自动查找)")
    parser.add_argument(
        "--max-distance",
        type=float,
        default=DEFAULT_MAX_DISTANCE,
        help=f"最大距离 km (默认 {DEFAULT_MAX_DISTANCE})",
    )
    parser.add_argument(
        "--max-labels",
        type=int,
        default=DEFAULT_MAX_LABELS,
        help=f"图片标注小区数 (默认 {DEFAULT_MAX_LABELS}, 0=全部)",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印报告")
    parser.add_argument(
        "--refresh-geo",
        action="store_true",
        help="强制刷新所有小区坐标 (清除缓存)",
    )

    args = parser.parse_args()

    # 获取工作地点（支持中文模糊匹配）
    workplace = get_workplace(args.workplace)
    if args.workplace_name:
        workplace["name"] = args.workplace_name

    # 强制刷新坐标缓存
    if args.refresh_geo:
        print("清除地理编码缓存...")
        _geocoder.clear_cache()

    # 加载数据
    if args.data:
        data = load_data(args.data)
    else:
        data = load_data(str(find_latest_data()))

    print(f"已加载 {len(data)} 条房源数据")

    community_stats = build_community_stats(data)
    print(f"涉及 {len(community_stats)} 个小区")

    # 控制台报告
    print_distance_report(community_stats, workplace, args.max_distance)

    # 生成地图
    if not args.dry_run:
        max_labels = args.max_labels if args.max_labels > 0 else len(community_stats)
        generate_static_map(
            community_stats, workplace, args.max_distance, max_labels
        )
        generate_html_map(community_stats, workplace, args.max_distance)

    # 确保地理编码缓存持久化
    _geocoder._save_cache()


if __name__ == "__main__":
    main()

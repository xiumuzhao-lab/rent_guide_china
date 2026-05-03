"""
配置常量模块

集中管理爬虫、地图、存储等所有配置项。
"""

from datetime import datetime
from pathlib import Path

# ============================================================
# 项目路径
# ============================================================

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"
USER_DATA_DIR = PROJECT_DIR / ".browser_data"
ERROR_LOG_FILE = OUTPUT_DIR / "error.log"

# ============================================================
# 城市配置
# ============================================================

# 当前城市 (可通过 --city 参数覆盖)
CITY = 'shanghai'

# 城市中文名
CITY_NAMES = {
    'shanghai': '上海',
    'beijing': '北京',
    'guangzhou': '广州',
    'shenzhen': '深圳',
    'hangzhou': '杭州',
    'chengdu': '成都',
    'nanjing': '南京',
}

# 城市对应的链家 URL 前缀
CITY_URL_PREFIX = {
    'shanghai': 'sh',
    'beijing': 'bj',
    'guangzhou': 'gz',
    'shenzhen': 'sz',
    'hangzhou': 'hz',
    'chengdu': 'cd',
    'nanjing': 'nj',
}


def get_city_dir(city: str = None) -> Path:
    """
    获取城市根目录.

    Args:
        city: 城市标识，None 则使用全局 CITY

    Returns:
        Path: output/{city}/
    """
    city = city or CITY
    return OUTPUT_DIR / city


def get_output_dir(city: str = None, month: str = None) -> Path:
    """
    获取当前月份的输出目录.

    Args:
        city: 城市标识，None 则使用全局 CITY
        month: 月份字符串 (如 '2026-05')，None 则使用当前月份

    Returns:
        Path: output/{city}/{YYYY-MM}/
    """
    city = city or CITY
    if month is None:
        month = datetime.now().strftime('%Y-%m')
    return OUTPUT_DIR / city / month


def get_geo_cache_file(city: str = None) -> Path:
    """
    获取城市的地理编码缓存文件路径.

    Args:
        city: 城市标识，None 则使用全局 CITY

    Returns:
        Path: 缓存文件路径 (output/{city}/community_geo_cache.json)
    """
    city = city or CITY
    return get_city_dir(city) / "community_geo_cache.json"


# ============================================================
# 爬虫配置
# ============================================================

REGIONS = {
    'pudong':     {'name': '浦东', 'slug': 'pudong'},
    'zhangjiang': {'name': '张江', 'slug': 'zhangjiang'},
    'jinqiao':    {'name': '金桥', 'slug': 'jinqiao'},
    'tangzhen':   {'name': '唐镇', 'slug': 'tangzhen'},
    'chuansha':   {'name': '川沙', 'slug': 'chuansha'},
    'changning':  {'name': '长宁', 'slug': 'changning'},
}
ALL_REGIONS = list(REGIONS.keys())
DEFAULT_MAX_PAGES = 100

CSV_FIELDS = [
    "region", "title", "rent_type", "community", "location", "area", "rooms",
    "direction", "floor", "price", "unit_price", "tags", "source", "url",
    "scraped_at", "lat", "lng",
]

# 每 N 条数据自动保存一次中间结果
SAVE_INTERVAL = 100

# 无新数据超时 (秒): 超过此时间未产出新数据则中止排查
STALE_DATA_TIMEOUT = 90

# ============================================================
# 工作地点配置
# ============================================================

WORKPLACES = {
    "zhangjiang": {
        "name": "张江国创中心",
        "lat": 31.2214,
        "lng": 121.6282,
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

# ============================================================
# 区域中心坐标 & 散布半径
# ============================================================

REGION_CENTERS = {
    "zhangjiang": (31.2214, 121.6282),
    "jinqiao": (31.2475, 121.6282),
    "tangzhen": (31.2150, 121.6550),
    "chuansha": (31.1900, 121.7000),
    "changning": (31.2200, 121.4250),
}

REGION_SPREAD_KM = {
    "zhangjiang": 4.0,
    "jinqiao": 4.5,
    "tangzhen": 4.0,
    "chuansha": 4.5,
    "changning": 5.0,
}

# ============================================================
# 距离环颜色 & 标签
# ============================================================

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

# ============================================================
# 图片输出配置
# ============================================================

IMAGE_DPI = 200
IMAGE_WIDTH_INCHES = 28
IMAGE_HEIGHT_INCHES = 22
LABEL_FONT_SIZE = 5.5

# ============================================================
# 腾讯位置服务 API
# ============================================================

TENCENT_GEOCODER_URL = "https://apis.map.qq.com/ws/geocoder/v1"
TENCENT_GEO_BATCH_INTERVAL = 0.05

"""
地理编码模块

腾讯位置服务 API + 本地缓存。
API 未返回结果时标记为 miss，不生成伪坐标。
包含区级坐标校验，自动发现并修正缓存中的错误坐标。
"""

import hashlib
import json
import logging
import math
import os
import time
from pathlib import Path
from urllib.parse import quote

from scraper.config import (
    GEO_CACHE_FILE,
    TENCENT_GEOCODER_URL,
    TENCENT_GEO_BATCH_INTERVAL,
)

logger = logging.getLogger('lianjia')


# 上海各区中心坐标 (近似值, 用于坐标校验)
DISTRICT_CENTERS = {
    '浦东': (31.22, 121.54),
    '松江': (31.03, 121.23),
    '闵行': (31.11, 121.38),
    '徐汇': (31.18, 121.44),
    '长宁': (31.22, 121.42),
    '静安': (31.23, 121.45),
    '黄浦': (31.23, 121.47),
    '普陀': (31.25, 121.40),
    '虹口': (31.26, 121.49),
    '杨浦': (31.27, 121.52),
    '宝山': (31.35, 121.45),
    '嘉定': (31.38, 121.25),
    '金山': (30.74, 121.34),
    '崇明': (31.63, 121.40),
    '奉贤': (30.92, 121.47),
    '青浦': (31.15, 121.12),
}

# 坐标偏离区的最大容忍距离 (km), 根据各区面积和实际坐标分布设定
DISTRICT_TOLERANCE_KM = {d: 25 for d in DISTRICT_CENTERS}
# 小型中心城区: 25km (静安, 黄浦, 长宁) - 默认值
# 中型中心城区: 35km
for d in ('徐汇', '普陀', '虹口', '杨浦'):
    DISTRICT_TOLERANCE_KM[d] = 35
# 中型近郊区: 40km
for d in ('闵行', '松江'):
    DISTRICT_TOLERANCE_KM[d] = 40
# 大型远郊区: 50km
for d in ('宝山', '金山', '嘉定', '青浦', '奉贤'):
    DISTRICT_TOLERANCE_KM[d] = 50
# 浦东: 60km (含临港片区)
DISTRICT_TOLERANCE_KM['浦东'] = 60


def _load_tencent_config():
    """
    加载腾讯位置服务 API 密钥。

    Returns:
        tuple: (key, sk)，未配置时返回 (None, None)
    """
    key = os.environ.get("TENCENT_MAP_KEY")
    sk = os.environ.get("TENCENT_MAP_SK")

    if key and sk:
        return key, sk

    env_file = Path(__file__).parent.parent / ".env"
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


def haversine(lat1, lon1, lat2, lon2):
    """
    Haversine 公式计算两点间距离 (km).

    Args:
        lat1, lon1: 起点纬度、经度
        lat2, lon2: 终点纬度、经度

    Returns:
        float: 距离 (km)
    """
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
    """
    km 转纬度差 (1度 ≈ 111km).

    Args:
        km: 距离 (km)

    Returns:
        float: 纬度差
    """
    return km / 111.0


def km_to_deg_lng(km, lat):
    """
    km 转经度差 (含纬度修正).

    Args:
        km: 距离 (km)
        lat: 纬度

    Returns:
        float: 经度差
    """
    return km / (111.0 * math.cos(math.radians(lat)))


class GeoCoder:
    """
    小区地理编码器。

    - 优先从本地 JSON 缓存读取坐标
    - 缓存未命中时调用腾讯位置服务 API
    - 同一小区只调用一次 API，结果持久化到缓存文件
    - API 未返回结果时标记为 miss，不生成伪坐标
    """

    def __init__(self):
        self._cache = {}
        self._cache_dirty = False
        self._api_key, self._api_sk = _load_tencent_config()
        self._load_cache()

    def _load_cache(self):
        """从磁盘加载缓存."""
        if GEO_CACHE_FILE.exists():
            try:
                self._cache = json.loads(
                    GEO_CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self):
        """将缓存写入磁盘."""
        if not self._cache_dirty:
            return
        GEO_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GEO_CACHE_FILE.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache_dirty = False

    @staticmethod
    def _extract_district(location):
        """
        从 location 字段提取区名.

        Args:
            location: 如 "松江-泗泾-祥泽苑" 或 "浦东-张江-XX"

        Returns:
            str: 区名 (如 "松江")，无法提取时返回空串
        """
        if not location:
            return ''
        parts = location.split('-')
        return parts[0].strip() if parts else ''

    def _validate_coords(self, lat, lng, location):
        """
        校验坐标是否在预期区的合理范围内.

        Args:
            lat: 纬度
            lng: 经度
            location: location 字段 (如 "松江-泗泾-祥泽苑")

        Returns:
            bool: True 表示坐标合理，False 表示坐标异常
        """
        district = self._extract_district(location)
        if not district or district not in DISTRICT_CENTERS:
            return True  # 无区信息，跳过校验
        center_lat, center_lng = DISTRICT_CENTERS[district]
        dist = haversine(lat, lng, center_lat, center_lng)
        tolerance = DISTRICT_TOLERANCE_KM.get(district, 25)
        if dist > tolerance:
            logger.debug(
                f"坐标校验失败: {location} -> ({lat}, {lng}) "
                f"距 {district} 中心 {dist:.0f}km (容忍 {tolerance}km)")
            return False
        return True

    def _calc_sig(self, uri, params):
        """
        计算腾讯位置服务 API 签名.

        Args:
            uri: API URI 路径
            params: 请求参数字典

        Returns:
            str: MD5 签名
        """
        sorted_params = "&".join(
            f"{k}={params[k]}" for k in sorted(params.keys())
        )
        basic_string = f"{uri}?{sorted_params}"
        return hashlib.md5(
            (basic_string + self._api_sk).encode("utf-8")
        ).hexdigest()

    def _api_geocode(self, address):
        """
        调用腾讯位置服务地理编码 API.

        Args:
            address: 地址字符串

        Returns:
            tuple or None: (lat, lng) 或 None
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
            logger.warning(f"地理编码 API 调用失败 ({address}): {e}")

        return None

    @staticmethod
    def _build_address(name, location=""):
        """
        构造精确的查询地址.

        优先使用 location 字段 (如 "浦东-惠南-西门锦绣苑")
        拼接为 "上海市浦东区惠南镇西门锦绣苑"。
        添加行政区划限定词以提高 API 定位精度。

        Args:
            name: 小区名
            location: location 字段 (如 "浦东-惠南-小区名")

        Returns:
            str: 查询地址
        """
        if location:
            parts = [p.strip() for p in location.split("-") if p.strip()]
            if len(parts) >= 2:
                district = parts[0]
                rest = "".join(parts[1:])
                return f"上海市{district}区{rest}"
            return f"上海{location.replace('-', '').replace(' ', '')}"
        return f"上海{name}"

    def geocode(self, name, region="", location=""):
        """
        获取小区坐标。

        查找顺序: 内存缓存 -> API 调用。
        hash 伪坐标和坐标偏离预期区的缓存条目视为未命中，强制重新查询。

        Args:
            name: 小区名
            region: 区域标识
            location: 完整位置 (如 "浦东-惠南-小区名")

        Returns:
            tuple or None: (lat, lng) 或 None (API 未返回结果)
        """
        if name in self._cache:
            entry = self._cache[name]
            # hash 伪坐标不可靠，视为未命中
            if entry.get("source") == "hash":
                del self._cache[name]
                self._cache_dirty = True
                # fall through to API query
            elif entry.get("lat") is None:
                return None
            else:
                # 校验缓存坐标是否在预期区内
                if not self._validate_coords(
                        entry["lat"], entry["lng"], location):
                    logger.info(
                        f"坐标校验失败，重新查询: {name} "
                        f"({entry['lat']}, {entry['lng']})")
                    del self._cache[name]
                    self._cache_dirty = True
                    # fall through to API query
                else:
                    return (entry["lat"], entry["lng"])

        address = self._build_address(name, location)
        coords = self._api_geocode(address)
        if coords:
            # 校验新查询的坐标
            if not self._validate_coords(coords[0], coords[1], location):
                logger.warning(
                    f"API 返回坐标仍偏离预期区: {name} "
                    f"address={address} -> ({coords[0]}, {coords[1]})")
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": "tencent",
            }
            self._cache_dirty = True
            return coords

        # 带区域查不到，尝试只用小区名
        if location:
            coords = self._api_geocode(f"上海{name}")
            if coords:
                self._cache[name] = {
                    "lat": coords[0],
                    "lng": coords[1],
                    "source": "tencent",
                }
                self._cache_dirty = True
                return coords

        # API 未返回结果，缓存为 null，避免重复请求
        logger.debug(f"地理编码无结果: {name}")
        self._cache[name] = {"lat": None, "lng": None, "source": "miss"}
        self._cache_dirty = True
        return None

    def batch_geocode(self, community_info):
        """
        批量地理编码: 对去重后的小区名逐一调用。

        Args:
            community_info: dict { community_name: { region, location } }
                           或兼容旧格式 { community_name: region_str }

        Returns:
            dict { community_name: (lat, lng) or None }
        """
        results = {}
        to_fetch = []

        for name, info in community_info.items():
            if name in self._cache:
                entry = self._cache[name]
                # hash 伪坐标不可靠，视为未命中
                if entry.get("source") == "hash":
                    del self._cache[name]
                    self._cache_dirty = True
                    if isinstance(info, dict):
                        to_fetch.append((name, info.get('region', ''),
                                         info.get('location', '')))
                    else:
                        to_fetch.append((name, info, ''))
                elif entry.get("lat") is not None:
                    results[name] = (entry["lat"], entry["lng"])
                else:
                    results[name] = None
            else:
                if isinstance(info, dict):
                    to_fetch.append((name, info.get('region', ''),
                                     info.get('location', '')))
                else:
                    to_fetch.append((name, info, ''))

        if not to_fetch:
            return results

        api_mode = "API" if self._api_key else "无API密钥"
        logger.info(
            f"地理编码: 缓存命中 {len(results)}/{len(community_info)}, "
            f"待处理 {len(to_fetch)} ({api_mode})"
        )

        for i, (name, region, location) in enumerate(to_fetch):
            coords = self.geocode(name, region, location)
            results[name] = coords
            if i < len(to_fetch) - 1 and self._api_key:
                time.sleep(TENCENT_GEO_BATCH_INTERVAL)
            if (i + 1) % 20 == 0:
                logger.info(f"  进度: {i + 1}/{len(to_fetch)}")
                self._save_cache()

        self._save_cache()
        return results

    def refresh_geo(self, name, region="", location="", force=False):
        """
        重查单个小区坐标。

        force=False 时只重查 source=hash/miss 或坐标偏离预期区的条目；
        force=True 时全部重查 (包括已有腾讯 API 结果的)。

        Args:
            name: 小区名
            region: 区域标识
            location: 完整位置 (如 "松江-泗泾-祥泽苑")
            force: 是否强制重查所有条目

        Returns:
            tuple or None: (lat, lng) 或 None
        """
        entry = self._cache.get(name)
        if entry and not force and entry.get("source") == "tencent":
            # 校验现有坐标是否在预期区内
            if self._validate_coords(entry["lat"], entry["lng"], location):
                return (entry["lat"], entry["lng"])
            logger.info(f"坐标偏离预期区，重查: {name} ({location})")

        # 删除旧缓存，重新查询
        if name in self._cache:
            del self._cache[name]

        address = self._build_address(name, location)
        coords = self._api_geocode(address)
        # 带 location 查不到时，尝试只用小区名
        if not coords:
            coords = self._api_geocode(f"上海{name}")
        if coords:
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": "tencent",
            }
            self._cache_dirty = True
            return coords

        # API 未返回结果
        logger.debug(f"地理编码刷新无结果: {name}")
        self._cache[name] = {"lat": None, "lng": None, "source": "miss"}
        self._cache_dirty = True
        return None

    def batch_refresh(self, community_info, force=False):
        """
        批量刷新地理坐标。

        Args:
            community_info: dict { community_name: region_str }
                           或 { community_name: { region, location } }
            force: 是否强制重查所有条目

        Returns:
            dict: { community_name: (lat, lng) } 更新后的坐标
        """
        results = {}
        to_refresh = []

        for name, info in community_info.items():
            if isinstance(info, dict):
                region = info.get('region', '')
                location = info.get('location', '')
            else:
                region = info
                location = ''
            entry = self._cache.get(name)
            if entry and not force and entry.get("source") == "tencent":
                if self._validate_coords(entry["lat"], entry["lng"],
                                         location):
                    results[name] = (entry["lat"], entry["lng"])
                else:
                    to_refresh.append((name, region, location))
            else:
                to_refresh.append((name, region, location))

        if not to_refresh:
            logger.info(f"地理缓存刷新: {len(results)} 条无需更新")
            return results

        mode = "全部" if force else "非tencent坐标+坐标异常"
        api_mode = "API" if self._api_key else "无API密钥"
        logger.info(
            f"地理缓存刷新 ({mode}): "
            f"{len(results)} 条跳过, {len(to_refresh)} 条待重查 ({api_mode})"
        )

        upgraded = 0
        for i, (name, region, location) in enumerate(to_refresh):
            old_entry = self._cache.get(name)
            old_source = old_entry.get("source", "") if old_entry else ""
            coords = self.refresh_geo(name, region, location, force=True)
            new_entry = self._cache.get(name, {})
            new_source = new_entry.get("source", "")
            if old_source in ("hash", "miss") and new_source == "tencent":
                upgraded += 1
            results[name] = coords
            if i < len(to_refresh) - 1 and self._api_key:
                time.sleep(TENCENT_GEO_BATCH_INTERVAL)
            if (i + 1) % 20 == 0:
                logger.info(f"  进度: {i + 1}/{len(to_refresh)}")
                self._save_cache()

        self._save_cache()
        logger.info(
            f"地理缓存刷新完成: 重查 {len(to_refresh)} 条, "
            f"升级为API坐标 {upgraded} 条"
        )
        return results
        """清空缓存."""
        self._cache = {}
        self._cache_dirty = False
        if GEO_CACHE_FILE.exists():
            GEO_CACHE_FILE.unlink()

    def has_api(self):
        """是否配置了腾讯位置服务 API."""
        return bool(self._api_key)


# 全局单例
_geocoder = GeoCoder()


def get_geocoder():
    """
    获取全局 GeoCoder 单例.

    Returns:
        GeoCoder: 地理编码器实例
    """
    return _geocoder


def geocode_community(name, region=""):
    """
    获取小区坐标 (兼容旧接口).

    Args:
        name: 小区名
        region: 区域标识

    Returns:
        tuple or None: (lat, lng) 或 None
    """
    return _geocoder.geocode(name, region)

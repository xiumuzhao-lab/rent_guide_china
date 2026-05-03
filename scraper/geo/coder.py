"""
地理编码器主类

协调缓存、校验、多 provider 查询。
"""

import logging
import time
from typing import Optional

from scraper.config import CITY, CITY_NAMES, TENCENT_GEO_BATCH_INTERVAL
from scraper.geo.cache import GeoCache
from scraper.geo.address import build_address
from scraper.geo.validation import (
    validate_coords, SH_BOUNDARY, BJ_BOUNDARY,
)
from scraper.geo.providers import create_providers

logger = logging.getLogger('lianjia')

_CITY_BOUNDARIES = {
    'shanghai': SH_BOUNDARY,
    'beijing': BJ_BOUNDARY,
}


class GeoCoder:
    """
    小区地理编码器.

    - 优先从本地 JSON 缓存读取坐标
    - 缓存未命中时按优先级尝试各 provider
    - 同一小区只调用一次 API，结果持久化到缓存文件
    - API 未返回结果时标记为 miss，不生成伪坐标
    """

    def __init__(self, city=None):
        self._city = city or CITY
        self._city_cn = CITY_NAMES.get(self._city, '')
        self._boundary = _CITY_BOUNDARIES.get(self._city)
        self._cache = GeoCache(self._city)
        self._providers = create_providers()
        names = [p.name for p in self._providers]
        logger.info(f"GeoCoder 初始化: city={self._city}, providers={names}")

    def _in_city(self, lat, lng):
        """检查坐标是否在当前城市边界内."""
        b = self._boundary
        if not b:
            return True
        return (b['lat_min'] <= lat <= b['lat_max']
                and b['lng_min'] <= lng <= b['lng_max'])

    def _api_geocode(self, address):
        """
        按优先级尝试各 provider.

        Returns:
            tuple: ((lat, lng), provider_name) 或 (None, None)
        """
        for provider in self._providers:
            if not provider.available:
                continue
            coords = provider.geocode(address)
            if coords:
                return coords, provider.name
        return None, None

    def geocode(self, name, region="", location=""):
        """
        获取小区坐标.

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
            if entry.get("source") == "hash":
                del self._cache[name]
            elif entry.get("lat") is None:
                return None
            else:
                if (self._in_city(entry["lat"], entry["lng"])
                        and validate_coords(entry["lat"], entry["lng"], location)):
                    return (entry["lat"], entry["lng"])
                logger.info(
                    f"坐标校验失败，重新查询: {name} "
                    f"({entry['lat']}, {entry['lng']})")
                del self._cache[name]

        address = build_address(name, location, self._city_cn)
        coords, provider_name = self._api_geocode(address)
        if coords:
            if not validate_coords(coords[0], coords[1], location):
                logger.warning(
                    f"API 返回坐标仍偏离预期区: {name} "
                    f"address={address} -> ({coords[0]}, {coords[1]})")
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": provider_name,
            }
            return coords

        # 带区域查不到，尝试只用城市+小区名
        if location and self._city_cn:
            coords, provider_name = self._api_geocode(
                f"{self._city_cn}{name}")
            if coords:
                self._cache[name] = {
                    "lat": coords[0],
                    "lng": coords[1],
                    "source": provider_name,
                }
                return coords

        logger.debug(f"地理编码无结果: {name}")
        self._cache[name] = {"lat": None, "lng": None, "source": "miss"}
        return None

    def batch_geocode(self, community_info):
        """
        批量地理编码: 对去重后的小区名逐一调用.

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
                if entry.get("source") == "hash":
                    del self._cache[name]
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

        has_api = any(p.available for p in self._providers)
        api_mode = "API" if has_api else "无API密钥"
        logger.info(
            f"地理编码: 缓存命中 {len(results)}/{len(community_info)}, "
            f"待处理 {len(to_fetch)} ({api_mode})"
        )

        for i, (name, region, location) in enumerate(to_fetch):
            coords = self.geocode(name, region, location)
            results[name] = coords
            if i < len(to_fetch) - 1 and has_api:
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
        force=True 时全部重查。

        Args:
            name: 小区名
            region: 区域标识
            location: 完整位置
            force: 是否强制重查

        Returns:
            tuple or None: (lat, lng) 或 None
        """
        entry = self._cache.get(name)
        if entry and not force and entry.get("source") not in ("hash", "miss"):
            if (self._in_city(entry["lat"], entry["lng"])
                    and validate_coords(entry["lat"], entry["lng"], location)):
                return (entry["lat"], entry["lng"])
            logger.info(f"坐标偏离预期区，重查: {name} ({location})")

        if name in self._cache:
            del self._cache[name]

        address = build_address(name, location, self._city_cn)
        coords, provider_name = self._api_geocode(address)
        if not coords and location and self._city_cn:
            coords, provider_name = self._api_geocode(
                f"{self._city_cn}{name}")
        if coords:
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": provider_name,
            }
            return coords

        logger.debug(f"地理编码刷新无结果: {name}")
        self._cache[name] = {"lat": None, "lng": None, "source": "miss"}
        return None

    def batch_refresh(self, community_info, force=False):
        """
        批量刷新地理坐标.

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
            if entry and not force and entry.get("source") not in ("hash", "miss"):
                if validate_coords(entry["lat"], entry["lng"], location):
                    results[name] = (entry["lat"], entry["lng"])
                else:
                    to_refresh.append((name, region, location))
            else:
                to_refresh.append((name, region, location))

        if not to_refresh:
            logger.info(f"地理缓存刷新: {len(results)} 条无需更新")
            return results

        has_api = any(p.available for p in self._providers)
        api_mode = "API" if has_api else "无API密钥"
        mode = "全部" if force else "非API坐标+坐标异常"
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
            if old_source in ("hash", "miss") and new_source not in ("hash", "miss", ""):
                upgraded += 1
            results[name] = coords
            if i < len(to_refresh) - 1 and has_api:
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

    def clear_cache(self):
        """清空缓存."""
        self._cache.clear()

    def _save_cache(self):
        """将缓存写入磁盘."""
        self._cache.save()

    def has_api(self):
        """是否配置了可用的地理编码 API."""
        return any(p.available for p in self._providers)


# ── 全局单例与工厂 ────────────────────────────────────────

_geocoder = GeoCoder()


def get_geocoder(city=None):
    """
    获取 GeoCoder 实例.

    Args:
        city: 城市标识，None 则使用默认全局单例

    Returns:
        GeoCoder: 地理编码器实例
    """
    if city and city != _geocoder._city:
        return GeoCoder(city)
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

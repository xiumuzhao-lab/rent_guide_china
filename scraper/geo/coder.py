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
    validate_coords, SH_BOUNDARY, BJ_BOUNDARY, SZ_BOUNDARY, HZ_BOUNDARY,
)
from scraper.geo.providers import create_providers

logger = logging.getLogger('lianjia')

_CITY_BOUNDARIES = {
    'shanghai': SH_BOUNDARY,
    'beijing': BJ_BOUNDARY,
    'shenzhen': SZ_BOUNDARY,
    'hangzhou': HZ_BOUNDARY,
}


class GeoCoder:
    """
    小区地理编码器.

    - 优先从本地 JSON 缓存读取坐标
    - 缓存未命中时按优先级尝试各 provider
    - 同一小区只调用一次 API，结果持久化到缓存文件
    - API 未返回结果时标记为 miss，不生成伪坐标
    """

    # 同一坐标被超过此数量的小区共用时，视为区中心假坐标
    _DUP_COORD_THRESHOLD = 5

    def __init__(self, city=None):
        self._city = city or CITY
        self._city_cn = CITY_NAMES.get(self._city, '')
        self._boundary = _CITY_BOUNDARIES.get(self._city)
        self._cache = GeoCache(self._city)
        self._providers = create_providers()
        self._coord_usage = self._build_coord_usage()
        names = [p.name for p in self._providers]
        logger.info(f"GeoCoder 初始化: city={self._city}, providers={names}")

    def _in_city(self, lat, lng):
        """检查坐标是否在当前城市边界内."""
        b = self._boundary
        if not b:
            return True
        return (b['lat_min'] <= lat <= b['lat_max']
                and b['lng_min'] <= lng <= b['lng_max'])

    def _build_coord_usage(self):
        """从缓存构建坐标→小区名集合的映射."""
        usage = {}
        for name, entry in self._cache._data.items():
            lat = entry.get('lat')
            lng = entry.get('lng')
            if lat is None or lng is None:
                continue
            key = (round(lat, 6), round(lng, 6))
            usage.setdefault(key, set()).add(name)
        return usage

    def _is_dup_coord(self, lat, lng):
        """检查坐标是否已被过多小区共用（区中心假坐标）."""
        key = (round(lat, 6), round(lng, 6))
        return len(self._coord_usage.get(key, ())) >= self._DUP_COORD_THRESHOLD

    def _record_coord(self, name, lat, lng):
        """记录坐标使用."""
        key = (round(lat, 6), round(lng, 6))
        self._coord_usage.setdefault(key, set()).add(name)

    def _remove_coord(self, name, lat, lng):
        """移除坐标使用记录."""
        if lat is None or lng is None:
            return
        key = (round(lat, 6), round(lng, 6))
        s = self._coord_usage.get(key)
        if s:
            s.discard(name)
            if not s:
                del self._coord_usage[key]

    def _api_geocode(self, address):
        """
        按优先级尝试各 provider.

        Returns:
            tuple: ((lat, lng), provider_name, api_responded) 或 (None, None, bool)
                api_responded: True 表示至少一个 provider 成功响应 (无论是否找到),
                              False 表示所有 provider 都因限速/配额耗尽/网络错误未响应
        """
        any_responded = False
        for provider in self._providers:
            if not provider.available:
                continue
            coords = provider.geocode(address)
            if coords:
                return coords, provider.name, True
            any_responded = True
        return None, None, any_responded

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
                lat, lng = entry["lat"], entry["lng"]
                if (self._in_city(lat, lng)
                        and validate_coords(lat, lng, location)
                        and not self._is_dup_coord(lat, lng)):
                    return (lat, lng)
                reason = "偏离预期区" if not validate_coords(lat, lng, location) else "重复坐标过多"
                logger.info(f"坐标校验失败({reason})，重新查询: {name} ({lat}, {lng})")
                self._remove_coord(name, lat, lng)
                del self._cache[name]

        address = build_address(name, location, self._city_cn)
        coords, provider_name, api_responded = self._api_geocode(address)
        if coords:
            if not validate_coords(coords[0], coords[1], location):
                logger.warning(
                    f"API 返回坐标仍偏离预期区: {name} "
                    f"address={address} -> ({coords[0]}, {coords[1]})")
            if self._is_dup_coord(coords[0], coords[1]):
                logger.warning(
                    f"API 返回坐标已被 {self._DUP_COORD_THRESHOLD}+ 个小区共用，拒绝: "
                    f"{name} -> ({coords[0]}, {coords[1]}) provider={provider_name}")
            else:
                self._cache[name] = {
                    "lat": coords[0],
                    "lng": coords[1],
                    "source": provider_name,
                }
                self._record_coord(name, coords[0], coords[1])
                return coords

        # 带区域查不到，尝试只用城市+小区名
        if location and self._city_cn:
            coords, provider_name, fallback_responded = self._api_geocode(
                f"{self._city_cn}{name}")
            api_responded = api_responded or fallback_responded
            if coords:
                if self._is_dup_coord(coords[0], coords[1]):
                    logger.warning(
                        f"回退查询坐标重复过多，拒绝: {name} -> ({coords[0]}, {coords[1]})")
                else:
                    self._cache[name] = {
                        "lat": coords[0],
                        "lng": coords[1],
                        "source": provider_name,
                    }
                    self._record_coord(name, coords[0], coords[1])
                    return coords

        if not api_responded:
            logger.debug(f"API 未响应 (限速/配额耗尽), 跳过: {name}")
            return None

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
            lat, lng = entry["lat"], entry["lng"]
            if (self._in_city(lat, lng)
                    and validate_coords(lat, lng, location)
                    and not self._is_dup_coord(lat, lng)):
                return (lat, lng)
            reason = "偏离预期区" if not validate_coords(lat, lng, location) else "重复坐标过多"
            logger.info(f"坐标{reason}，重查: {name} ({location})")

        if name in self._cache:
            old = self._cache[name]
            self._remove_coord(name, old.get("lat"), old.get("lng"))
            del self._cache[name]

        address = build_address(name, location, self._city_cn)
        coords, provider_name, api_responded = self._api_geocode(address)
        if not coords and location and self._city_cn:
            coords, provider_name, fallback_responded = self._api_geocode(
                f"{self._city_cn}{name}")
            api_responded = api_responded or fallback_responded
        if coords:
            if self._is_dup_coord(coords[0], coords[1]):
                logger.warning(
                    f"刷新坐标重复过多，拒绝: {name} -> ({coords[0]}, {coords[1]})")
                self._cache[name] = {"lat": None, "lng": None, "source": "miss"}
                return None
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": provider_name,
            }
            self._record_coord(name, coords[0], coords[1])
            return coords

        if not api_responded:
            logger.debug(f"API 未响应 (限速/配额耗尽), 跳过: {name}")
            # 恢复原来的 miss 状态，不做 mark
            return None

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

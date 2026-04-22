"""
地理编码模块

腾讯位置服务 API + 本地缓存 + 哈希散布备用。
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
    REGION_CENTERS,
    REGION_SPREAD_KM,
    TENCENT_GEOCODER_URL,
    TENCENT_GEO_BATCH_INTERVAL,
)

logger = logging.getLogger('lianjia')


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
    - 未配置 API 密钥时回退到哈希散布算法
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

    def _hash_geocode(self, name, region=""):
        """
        备用: 确定性哈希散布算法 (无 API 时使用).

        Args:
            name: 小区名
            region: 区域标识

        Returns:
            tuple: (lat, lng)
        """
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

        查找顺序: 内存缓存 -> API 调用 -> 哈希散布备用。

        Args:
            name: 小区名
            region: 区域标识

        Returns:
            tuple: (lat, lng)
        """
        if name in self._cache:
            entry = self._cache[name]
            return (entry["lat"], entry["lng"])

        coords = self._api_geocode(f"上海{name}")
        if coords:
            self._cache[name] = {
                "lat": coords[0],
                "lng": coords[1],
                "source": "tencent",
            }
            self._cache_dirty = True
            return coords

        coords = self._hash_geocode(name, region)
        self._cache[name] = {
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

        for name, region in community_regions.items():
            if name in self._cache:
                entry = self._cache[name]
                results[name] = (entry["lat"], entry["lng"])
            else:
                to_fetch.append((name, region))

        if not to_fetch:
            return results

        api_mode = ("API" if self._api_key
                    else "哈希散布(未配置API密钥)")
        logger.info(
            f"地理编码: 缓存命中 {len(results)}/{len(community_regions)}, "
            f"待处理 {len(to_fetch)} ({api_mode})"
        )

        for i, (name, region) in enumerate(to_fetch):
            coords = self.geocode(name, region)
            results[name] = coords
            if i < len(to_fetch) - 1 and self._api_key:
                time.sleep(TENCENT_GEO_BATCH_INTERVAL)
            if (i + 1) % 20 == 0:
                logger.info(f"  进度: {i + 1}/{len(to_fetch)}")
                self._save_cache()

        self._save_cache()
        return results

    def clear_cache(self):
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
        tuple: (lat, lng)
    """
    return _geocoder.geocode(name, region)

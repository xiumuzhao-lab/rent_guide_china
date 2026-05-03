"""
天地图 Provider

使用 POI 搜索实现正向地理编码，支持多 key 轮换。
"""

import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from scraper.geo.providers.base import GeoProvider
from scraper.geo.key_manager import KeyManager

logger = logging.getLogger('lianjia')

TIANDITU_SEARCH_URL = "https://api.tianditu.gov.cn/v2/search"

_TIANDITU_MIN_INTERVAL = 0.3


class TiandituProvider(GeoProvider):
    """
    天地图地理编码 Provider.

    使用 POI 搜索接口 (queryType=1) 实现正向地理编码。
    免费额度约 10000 次/天/token。
    """

    def __init__(self, key_manager: KeyManager):
        self._km = key_manager
        self._last_call = 0.0

    @property
    def name(self) -> str:
        return "tianditu"

    @property
    def available(self) -> bool:
        return self._km.has_available_key

    def _rate_limit(self):
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < _TIANDITU_MIN_INTERVAL:
            time.sleep(_TIANDITU_MIN_INTERVAL - elapsed)
        self._last_call = time.time()

    def geocode(self, address: str) -> Optional[tuple]:
        """
        调用天地图 POI 搜索实现正向地理编码.

        Args:
            address: 地址字符串

        Returns:
            (lat, lng) 或 None
        """
        if not self._km.has_keys:
            return None

        tried = set()
        retries_on_429 = 0
        max_429_retries = 3

        while True:
            key_dict = self._km.current_key
            token = key_dict.get('token', '')
            if token in tried:
                break

            self._rate_limit()
            post_str = json.dumps({
                'keyWord': address,
                'level': '18',
                'mapBound': '73.0,3.0,136.0,54.0',
                'queryType': '1',
                'start': '0',
                'count': '1',
            }, ensure_ascii=False)
            params = urllib.parse.urlencode({
                'postStr': post_str,
                'type': 'query',
                'tk': token,
            })
            url = f"{TIANDITU_SEARCH_URL}?{params}"

            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                status = data.get("status", {})
                infocode = status.get("infocode", 0) if isinstance(status, dict) else 0

                if infocode == 1000:
                    pois = data.get("pois") or []
                    if pois:
                        lonlat = pois[0].get("lonlat", "")
                        if lonlat and "," in lonlat:
                            parts = lonlat.split(",")
                            lng = float(parts[0])
                            lat = float(parts[1])
                            return (lat, lng)
                    return None

                # 配额耗尽
                if infocode in (2001, 2002):
                    logger.warning(
                        f"天地图 token 配额耗尽 (infocode={infocode}): "
                        f"{token[:8]}...")
                    self._km.mark_depleted(key_dict)
                    tried.add(token)
                    continue

                logger.debug(
                    f"天地图搜索返回: infocode={infocode}, "
                    f"msg={status.get('cndesc', '') if isinstance(status, dict) else status}")
                return None

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    retries_on_429 += 1
                    if retries_on_429 > max_429_retries:
                        logger.warning(
                            f"天地图限速重试 {max_429_retries} 次仍 429: "
                            f"{address[:20]}")
                        return None
                    wait = _TIANDITU_MIN_INTERVAL * retries_on_429 * 3
                    logger.debug(f"天地图限速 429, 等待 {wait:.1f}s")
                    time.sleep(wait)
                    continue
                if e.code == 403:
                    logger.warning(
                        f"天地图 token 配额耗尽 (403): {token[:8]}...")
                    self._km.mark_depleted(key_dict)
                    tried.add(token)
                    continue
                logger.warning(f"天地图 HTTP 错误 ({address[:20]}): {e}")
                return None

            except Exception as e:
                logger.warning(
                    f"天地图 API 调用失败 ({address[:20]}): {e}")
                return None

        return None

"""
腾讯位置服务 Provider

使用 MD5 签名认证，支持多 key 轮换。
"""

import hashlib
import json
import logging
import ssl
import urllib.request
from typing import Optional
from urllib.parse import quote

from scraper.geo.providers.base import GeoProvider
from scraper.geo.key_manager import KeyManager

logger = logging.getLogger('lianjia')

TENCENT_API_URL = "https://apis.map.qq.com/ws/geocoder/v1"


class TencentProvider(GeoProvider):
    """
    腾讯位置服务地理编码 Provider.

    每个 key+sk 对配额约 10000 次/天。
    """

    def __init__(self, key_manager: KeyManager):
        self._km = key_manager

    @property
    def name(self) -> str:
        return "tencent"

    @property
    def available(self) -> bool:
        return self._km.has_available_key

    def _calc_sig(self, uri, params, sk):
        sorted_params = "&".join(
            f"{k}={params[k]}" for k in sorted(params.keys())
        )
        basic_string = f"{uri}?{sorted_params}"
        return hashlib.md5(
            (basic_string + sk).encode("utf-8")
        ).hexdigest()

    def geocode(self, address: str) -> Optional[tuple]:
        """
        调用腾讯位置服务地理编码 API.

        配额耗尽时自动切换到下一个 key。

        Args:
            address: 地址字符串

        Returns:
            (lat, lng) 或 None
        """
        if not self._km.has_keys:
            return None

        uri = "/ws/geocoder/v1"

        # 尝试所有可用 key
        tried = set()
        while True:
            key_dict = self._km.current_key
            key_id = key_dict.get('key', '')
            if key_id in tried:
                break
            tried.add(key_id)

            params = {
                "address": address,
                "key": key_dict['key'],
                "output": "json",
            }
            sk = key_dict.get('sk', '')
            sig = self._calc_sig(uri, params, sk) if sk else ""

            encoded_params = "&".join(
                f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items())
            )
            url = f"https://apis.map.qq.com{uri}?{encoded_params}"
            if sig:
                url += f"&sig={sig}"

            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                status = data.get("status", -1)
                if status == 0:
                    loc = data.get("result", {}).get("location", {})
                    lat = loc.get("lat")
                    lng = loc.get("lng")
                    if lat and lng:
                        return (lat, lng)
                    return None

                # 配额相关错误码: 121 (key 频率超限), 112 (key 无余额)
                if status in (121, 112):
                    logger.warning(
                        f"腾讯 key 配额耗尽 (status={status}): "
                        f"{key_id[:8]}...")
                    self._km.mark_depleted(key_dict)
                    continue

                logger.debug(
                    f"腾讯 API 返回非零状态: status={status}, "
                    f"msg={data.get('message', '')}")
                return None

            except Exception as e:
                logger.warning(f"腾讯地理编码 API 调用失败 ({address}): {e}")
                return None

        return None

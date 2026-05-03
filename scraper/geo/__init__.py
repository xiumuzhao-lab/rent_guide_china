"""
地理编码模块

支持多平台 (腾讯、天地图) 多 key 轮换的地理编码服务。
"""

from scraper.geo.coder import GeoCoder, get_geocoder, geocode_community
from scraper.geo.validation import (
    haversine,
    km_to_deg_lat,
    km_to_deg_lng,
    validate_coords,
    DISTRICT_CENTERS,
    DISTRICT_TOLERANCE_KM,
    SUB_REGION_CENTERS,
    SUB_REGION_TOLERANCE_KM,
    SH_BOUNDARY,
    BJ_BOUNDARY,
    SH_DISTRICT_CENTERS,
    BJ_DISTRICT_CENTERS,
    BJ_DISTRICT_TOLERANCE_KM,
    BJ_SUB_REGION_CENTERS,
    KNOWN_TOWNS,
)

__all__ = [
    'GeoCoder',
    'get_geocoder',
    'geocode_community',
    'haversine',
    'km_to_deg_lat',
    'km_to_deg_lng',
    'validate_coords',
    'DISTRICT_CENTERS',
    'DISTRICT_TOLERANCE_KM',
    'SUB_REGION_CENTERS',
    'SUB_REGION_TOLERANCE_KM',
    'SH_BOUNDARY',
    'BJ_BOUNDARY',
    'KNOWN_TOWNS',
]

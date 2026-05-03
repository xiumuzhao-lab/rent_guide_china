"""
地理编码缓存模块

JSON 文件读写，支持按城市隔离缓存。
"""

import json
import logging
from pathlib import Path

from scraper.config import get_geo_cache_file

logger = logging.getLogger('lianjia')


class GeoCache:
    """
    地理编码结果缓存.

    每个城市一个 JSON 文件，格式: { community_name: {lat, lng, source} }
    """

    def __init__(self, city=None):
        self._city = city
        self._data = {}
        self._dirty = False
        self._load()

    def _load(self):
        cache_file = get_geo_cache_file(self._city)
        if cache_file.exists():
            try:
                self._data = json.loads(
                    cache_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self):
        if not self._dirty:
            return
        cache_file = get_geo_cache_file(self._city)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._dirty = False

    def get(self, name, default=None):
        return self._data.get(name, default)

    def __contains__(self, name):
        return name in self._data

    def __getitem__(self, name):
        return self._data[name]

    def __setitem__(self, name, value):
        self._data[name] = value
        self._dirty = True

    def __delitem__(self, name):
        if name in self._data:
            del self._data[name]
            self._dirty = True

    def clear(self):
        self._data = {}
        self._dirty = False
        cache_file = get_geo_cache_file(self._city)
        if cache_file.exists():
            cache_file.unlink()

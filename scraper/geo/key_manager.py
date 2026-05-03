"""
多 key 轮换与配额追踪

每个 provider 持有一个 KeyManager 实例。
key 用尽后标记当天不可用，跨天自动重置。
depleted 状态持久化到文件，避免重启后重复探测已耗尽的 key。
"""

import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger('lianjia')

_DEPLETED_FILE = Path(__file__).parent.parent.parent / "output" / "geo_key_depleted.json"


class KeyManager:
    """
    管理同一 provider 的多个 API key.

    配额耗尽状态持久化到 output/geo_key_depleted.json，跨天自动重置。
    """

    def __init__(self, keys):
        """
        Args:
            keys: key 列表，每个元素为一个 dict。
                  腾讯: {"key": "xxx", "sk": "yyy"}
                  天地图: {"token": "xxx"}
        """
        self._keys = list(keys)
        self._depleted = {}
        self._load_depleted()

    def _load_depleted(self):
        if _DEPLETED_FILE.exists():
            try:
                data = json.loads(_DEPLETED_FILE.read_text(encoding="utf-8"))
                today = datetime.date.today().isoformat()
                # 只加载今天的记录，过期的忽略
                self._depleted = {k: v for k, v in data.items() if v == today}
            except (json.JSONDecodeError, OSError):
                self._depleted = {}

    def _save_depleted(self):
        _DEPLETED_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DEPLETED_FILE.write_text(
            json.dumps(self._depleted, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _reset_if_new_day(self):
        today = datetime.date.today().isoformat()
        stale = [k for k, d in self._depleted.items() if d != today]
        if stale:
            for k in stale:
                del self._depleted[k]
                logger.info(f"key 配额已重置 (跨天): {k[:8]}...")
            self._save_depleted()

    def _key_id(self, key_dict):
        return key_dict.get('key') or key_dict.get('token') or str(key_dict)

    @property
    def has_available_key(self):
        self._reset_if_new_day()
        return any(self._key_id(k) not in self._depleted for k in self._keys)

    @property
    def current_key(self):
        """
        返回第一个未耗尽的 key，全部耗尽则返回第一个 key (降级).
        """
        self._reset_if_new_day()
        for k in self._keys:
            if self._key_id(k) not in self._depleted:
                return k
        logger.warning(f"所有 key 今日已耗尽，降级使用第一个 key")
        return self._keys[0] if self._keys else {}

    def mark_depleted(self, key_dict):
        """
        标记某个 key 今天已耗尽配额，并持久化.
        """
        kid = self._key_id(key_dict)
        today = datetime.date.today().isoformat()
        self._depleted[kid] = today
        self._save_depleted()
        logger.warning(f"key 配额耗尽，已切换: {kid[:8]}...")

    @property
    def keys_count(self):
        return len(self._keys)

    @property
    def available_count(self):
        self._reset_if_new_day()
        return sum(1 for k in self._keys if self._key_id(k) not in self._depleted)

    @property
    def has_keys(self):
        return len(self._keys) > 0

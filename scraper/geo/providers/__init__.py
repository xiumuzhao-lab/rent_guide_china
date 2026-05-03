"""
Provider 工厂

根据配置文件或 .env 创建 provider 实例列表。
"""

import json
import logging
import os
from pathlib import Path

from scraper.geo.key_manager import KeyManager
from scraper.geo.providers.base import GeoProvider
from scraper.geo.providers.tencent import TencentProvider
from scraper.geo.providers.tianditu import TiandituProvider

logger = logging.getLogger('lianjia')

# Provider 类型注册表
PROVIDER_TYPES = {
    'tencent': TencentProvider,
    'tianditu': TiandituProvider,
}


def load_provider_config():
    """
    加载 provider 配置.

    优先读取 scraper/geo_providers.json（geo 包同级目录），
    不存在时从 .env 读取腾讯单 key 配置 (向后兼容)。

    Returns:
        list[dict]: provider 配置列表
    """
    config_path = Path(__file__).parent.parent.parent / "geo_providers.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data.get("providers", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取 geo_providers.json 失败: {e}")

    # fallback: 从 .env 读取腾讯 key
    return _load_from_env()


def _load_from_env():
    """
    从 .env 文件读取腾讯 API key (向后兼容).

    Returns:
        list[dict]: 单个腾讯 provider 配置
    """
    key = os.environ.get("TENCENT_MAP_KEY")
    sk = os.environ.get("TENCENT_MAP_SK")

    if not key or not sk:
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k == "TENCENT_MAP_KEY" and not key:
                    key = v
                elif k == "TENCENT_MAP_SK" and not sk:
                    sk = v

    if key and sk:
        return [{
            "type": "tencent",
            "enabled": True,
            "priority": 1,
            "keys": [{"key": key, "sk": sk}],
        }]

    return []


def create_providers():
    """
    根据配置创建 provider 实例列表 (按 priority 排序).

    Returns:
        list[GeoProvider]: 可用的 provider 列表
    """
    configs = load_provider_config()
    providers = []

    for cfg in sorted(configs, key=lambda c: c.get("priority", 99)):
        if not cfg.get("enabled", True):
            continue
        ptype = cfg.get("type", "")
        keys = cfg.get("keys", [])
        if not keys:
            continue

        cls = PROVIDER_TYPES.get(ptype)
        if not cls:
            logger.warning(f"未知 provider 类型: {ptype}")
            continue

        km = KeyManager(keys)
        providers.append(cls(km))
        logger.info(
            f"已加载 provider: {ptype} ({len(keys)} keys, "
            f"priority={cfg.get('priority', 99)})")

    return providers

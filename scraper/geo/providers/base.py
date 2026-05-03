"""
地理编码 Provider 基类
"""

from abc import ABC, abstractmethod
from typing import Optional


class GeoProvider(ABC):
    """地理编码 API 提供者的抽象基类."""

    @property
    @abstractmethod
    def name(self) -> str:
        """短标识，用于缓存 source 字段 (如 'tencent', 'tianditu')."""
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """是否至少有一个未耗尽的 key 可用."""
        ...

    @abstractmethod
    def geocode(self, address: str) -> Optional[tuple]:
        """
        地理编码单个地址.

        Args:
            address: 地址字符串

        Returns:
            (lat, lng) 或 None
        """
        ...

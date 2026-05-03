"""
地址构建模块

根据 location 字段自动识别城市，构造精确的查询地址。
"""

from scraper.geo.validation import (
    BJ_DISTRICT_CENTERS,
    SH_DISTRICT_CENTERS,
    KNOWN_TOWNS,
)


def build_address(name, location=""):
    """
    构造精确的查询地址.

    根据区名自动识别城市:
      - 北京: "朝阳区-望京-XX" → "北京市朝阳区望京 XX"
      - 上海: "浦东-惠南-XX" → "上海市浦东新区惠南镇 XX"

    Args:
        name: 小区名
        location: location 字段 (如 "浦东-惠南-小区名" 或 "朝阳区-望京-小区名")

    Returns:
        str: 查询地址
    """
    if location:
        parts = [p.strip() for p in location.split("-") if p.strip()]
        if len(parts) >= 2:
            district = parts[0]
            is_bj = district in BJ_DISTRICT_CENTERS or district.endswith('区')
            is_sh = not is_bj and district in SH_DISTRICT_CENTERS
            if is_bj and not is_sh:
                sub_parts = parts[1:]
                rest = " ".join(sub_parts)
                return f"北京市{district}{rest} {name}"
            if is_sh:
                district_suffix = "新区" if district == "浦东" else "区"
                sub_parts = []
                for p in parts[1:]:
                    if p in KNOWN_TOWNS and not p.endswith('镇') and not p.endswith('新城'):
                        sub_parts.append(p + "镇")
                    else:
                        sub_parts.append(p)
                rest = " ".join(sub_parts)
                return f"上海市{district}{district_suffix}{rest} {name}"
        return f"{location.replace('-', ' ').replace(' ', '')}{name}"
    return f"{name}"

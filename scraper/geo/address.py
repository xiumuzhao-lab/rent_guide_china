"""
地址构建模块

根据 location 字段自动识别城市，构造精确的查询地址。
"""

from scraper.geo.validation import (
    BJ_DISTRICT_CENTERS,
    SH_DISTRICT_CENTERS,
    SZ_DISTRICT_CENTERS,
    HZ_DISTRICT_CENTERS,
    KNOWN_TOWNS,
)


def build_address(name, location="", city_cn=""):
    """
    构造精确的查询地址.

    根据区名自动识别城市:
      - 北京: "朝阳区-望京-XX" → "北京市朝阳区望京 XX"
      - 上海: "浦东-惠南-XX" → "上海市浦东新区惠南镇 XX"

    Args:
        name: 小区名
        location: location 字段 (如 "浦东-惠南-小区名" 或 "朝阳区-望京-小区名")
        city_cn: 城市中文名 (如 "北京"、"上海")，无 location 时用作前缀

    Returns:
        str: 查询地址
    """
    if location:
        parts = [p.strip() for p in location.split("-") if p.strip()]
        if len(parts) >= 2:
            district = parts[0]
            is_bj = district in BJ_DISTRICT_CENTERS
            is_sh = district in SH_DISTRICT_CENTERS
            is_sz = district in SZ_DISTRICT_CENTERS
            is_hz = district in HZ_DISTRICT_CENTERS
            # 区名可能带 "区" 后缀 (如 "临平区" -> "临平")
            district_base = district.rstrip('区')
            if not is_sz and district_base in SZ_DISTRICT_CENTERS:
                is_sz = True
                district = district_base
            if not is_hz and district_base in HZ_DISTRICT_CENTERS:
                is_hz = True
                district = district_base
            if is_bj:
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
            if is_sz:
                sub_parts = parts[1:]
                rest = " ".join(sub_parts)
                return f"深圳市{district}区{rest} {name}"
            if is_hz:
                sub_parts = parts[1:]
                rest = " ".join(sub_parts)
                return f"杭州市{district}区{rest} {name}"
        return f"{location.replace('-', ' ').replace(' ', '')}{name}"
    if city_cn:
        return f"{city_cn}{name}"
    return f"{name}"

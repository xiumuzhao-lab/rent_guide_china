"""
通用工具模块

日志初始化、系统通知、去重、单价计算、环境变量加载。
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from scraper.config import OUTPUT_DIR, REGIONS


def load_env():
    """
    从 .env 文件加载环境变量 (不覆盖已存在的).

    Returns:
        bool: 是否成功加载了 .env 文件
    """
    env_file = Path(__file__).parent.parent / '.env'
    if not env_file.exists():
        return False
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v
    return True


# 模块加载时自动读取 .env
load_env()


def setup_logging(output_dir: Path = None):
    """
    配置日志: 控制台 + 文件.

    Args:
        output_dir: 日志文件目录，默认使用 OUTPUT_DIR

    Returns:
        logging.Logger: 配置好的日志器
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)
    log = logging.getLogger('lianjia')
    log.setLevel(logging.INFO)

    # 避免重复添加 handler
    if log.handlers:
        return log

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(ch)

    # 文件
    fh = logging.FileHandler(output_dir / 'scraper.log', encoding='utf-8', mode='a')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    log.addHandler(fh)

    return log


logger = setup_logging()


def notify(title, message):
    """
    发送 macOS 系统通知 + 终端响铃.

    Args:
        title: 通知标题
        message: 通知内容
    """
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}" sound name "Glass"'
        ], timeout=5, capture_output=True)
    except Exception:
        pass
    sys.stdout.write('\a')
    sys.stdout.flush()


# ============================================================
# 小区名称清洗: 去除链家品牌公寓标题中的广告文案
# ============================================================

# 广告关键词 — 出现在社区名中时，表示其后为广告文案
_AD_KEYWORDS = (
    '可短租', '可月付', '可月租', '可养', '可办', '可开', '可提', '可做',
    '民用水电', '民水民电', '民水电', '通燃气', '包水电', '包网络',
    '无中介', '免中介', '无服务费', '免服务费', '直租', '无佣金',
    '0中介', '0服务费',
    '近地铁', '地铁口', '地铁旁', '地铁房', '地铁上盖', '直达',
    '免费班车', '班车直达', '班车接送',
    '特惠', '特价', '优惠', '限时', '首月', '开春', '毕业季',
    '春季特惠', '新年特惠', '巨惠', '开年特惠', '限时特惠',
    '拎包入住', '随时看房', '精装', '简装', '落地窗', '独卫',
    '居住证', '公积金', '网签', '保租房', '备案',
    '宠物友好', '猫咪友好', '可养猫', '可养宠',
    '央企', '国企', '连锁', '直营', '品牌',
    '优选', '精选', '臻选', '甄选',
    '温馨', '舒适', '高品质', '轻奢',
    '班车', '健身房', '安保', '管家', '保洁',
    '整租一室', '整租长租', '独立厨卫', '独门独户',
    '全朝南', '超大', '带阳台', '好房推荐', '好房',
    '此为长租', '送', '赠送', '年租特价',
    '押一付', '非底楼', '非顶楼',
    '租期灵活', '现房实拍', '好采光', '近漕河泾', '近同济',
    '近复旦', '近上中', '此为长租', '史上巨惠', '看房有礼',
    '人才补贴', '陪读', '三个月起租', '不限购',
    '高端', '精品', '精致', '豪华', '通勤',
)

import re as _re

_AD_KW_RE = _re.compile('|'.join(_re.escape(k) for k in _AD_KEYWORDS))

# 括号类字符 (含中文全角)
_BRACKET_RE = _re.compile(r'[【《（(〔]')

# 含数字 + 单位的广告短语: 12号线, 42平, 1500元, 300米, 15分钟
_NUM_UNIT_RE = _re.compile(r'\d+\s*(?:号线|平[方米]?|元|米|m\b|km\b|分钟)')

# 户型描述 (出现在社区名中即为广告文案): 三房两厅, 一居室, 小一居等
_ROOM_TYPE_RE = _re.compile(r'[一二三四五六][居房室厅]|小一居|大一居|大两居|大一房')

# 常见句末广告标点
_AD_PUNCT_RE = _re.compile(r'[，、！？!?,]')


def clean_community_name(name):
    """
    清洗社区名称，去除品牌公寓标题中的广告文案.

    只处理名称过长 (>15字符) 的情况，短名称原样返回.
    针对链家「独栋」类品牌公寓标题，去除店铺名之后的推广描述.

    Args:
        name: 原始社区名称

    Returns:
        str: 清洗后的社区名称
    """
    if not name or len(name) <= 15:
        return name

    # 去除 【...】 括号及其内容
    cleaned = _re.sub(r'【.*?】', '', name).strip()

    # 按空格拆分，逐段检查 (始终保留第一段 = 品牌名)
    parts = cleaned.split()
    clean_parts = []
    for i, part in enumerate(parts):
        # 第一段 (品牌名) 始终保留，不做广告检测
        if i == 0:
            clean_parts.append(part)
            continue
        # 以 【 开头 → 截断
        if part.startswith('【') or part.startswith('《'):
            break
        # 包含广告关键词 → 截断
        if _AD_KW_RE.search(part):
            break
        # 包含 数字+单位 广告短语 → 截断
        if _NUM_UNIT_RE.search(part):
            break
        # 包含户型描述 → 截断
        if _ROOM_TYPE_RE.search(part):
            break
        # 超长且含句内标点 (如逗号) → 截断
        if len(part) > 15 and _AD_PUNCT_RE.search(part):
            break
        clean_parts.append(part)

    result = ' '.join(clean_parts).strip()
    # 去除尾部多余标点/连字符
    result = _re.sub(r'[-·\s]+$', '', result)
    # 去除末尾不完整的括号内容
    result = _re.sub(r'[（(]\s*$', '', result).strip()
    # 清洗后为空则保留原名
    return result if result else name


def clean_listing_community(item):
    """
    清洗单条房源的 community 字段.

    Args:
        item: 房源数据字典，原地修改 community 字段

    Returns:
        bool: 是否修改了 community
    """
    old = item.get('community', '')
    new = clean_community_name(old)
    if new != old:
        item['community'] = new
        return True
    return False


def add_unit_price(item):
    """
    为单条房源计算单价 (元/㎡/月).

    Args:
        item: 房源数据字典，会原地修改添加 unit_price 字段
    """
    try:
        price = int(item['price']) if str(item.get('price', '')).isdigit() else None
        area = float(item['area']) if item.get('area') else None
        if price and area and area > 0:
            item['unit_price'] = round(price / area, 1)
        else:
            item['unit_price'] = ''
    except (ValueError, TypeError):
        item['unit_price'] = ''


def deduplicate(data):
    """
    按 URL 去重，保留最新记录.

    Args:
        data: 房源数据列表

    Returns:
        list: 去重后的列表
    """
    seen = {}
    for item in data:
        key = item.get('url', '') or (
            item.get('community', '') + str(item.get('price', ''))
            + str(item.get('area', '')) + item.get('region', '')
        )
        if key:
            seen[key] = item
    return list(seen.values())


def get_area_url(slug: str, page: int = None) -> str:
    """
    根据区域 slug 和页码生成 URL.

    优先使用从页面直接提取的 URL (REGIONS[slug]['url'])，
    避免手动拼接。找不到时再根据 parent 字段构造。

    Args:
        slug: 区域标识 (如 zhangjiang)
        page: 页码，None 或 0 表示首页

    Returns:
        str: 完整 URL
    """
    region = REGIONS.get(slug, {})
    # 优先使用从页面直接提取的完整 URL
    base = region.get('url', '')
    if not base:
        parent = region.get('parent')
        if parent:
            base = f"https://sh.lianjia.com/zufang/{parent}/{slug}/"
        else:
            base = f"https://sh.lianjia.com/zufang/{slug}/"
    # 确保 base 以 / 结尾
    if not base.endswith('/'):
        base += '/'
    if page is None or page <= 0:
        return base
    return f"{base}pg{page}/"

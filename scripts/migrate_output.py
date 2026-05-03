#!/usr/bin/env python3.10
"""
历史数据迁移脚本

将 output/ 目录下平铺的旧格式文件迁移到 output/{city}/{YYYY-MM}/ 分层结构。

用法:
  python3.10 scripts/migrate_output.py                    # 预览 (dry-run)
  python3.10 scripts/migrate_output.py --run              # 执行迁移
  python3.10 scripts/migrate_output.py --city shanghai    # 指定城市 (默认 shanghai)
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_DIR / "output"

# 文件名中的时间戳模式: lianjia_{region}_{YYYYMMDD}_{HHMMSS}.{ext}
TIMESTAMP_RE = re.compile(r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})')

# 需要迁移的文件模式
MIGRATE_PATTERNS = [
    'lianjia_*_*.json',
    'lianjia_*_*.csv',
]

# 排除的文件 (非数据文件)
EXCLUDE_NAMES = {
    'community_geo_cache.json',
    'lianjia_merged_latest.json',
}


def extract_month(filename):
    """
    从文件名中提取年月.

    Args:
        filename: 文件名

    Returns:
        str or None: 格式 'YYYY-MM'
    """
    m = TIMESTAMP_RE.search(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def collect_files(output_dir):
    """
    收集需要迁移的文件.

    Args:
        output_dir: output 目录路径

    Returns:
        list: (src_path, city, month) 元组列表
    """
    files = []
    for pattern in MIGRATE_PATTERNS:
        for fp in sorted(output_dir.glob(pattern)):
            if fp.name in EXCLUDE_NAMES:
                continue
            # 排除 partial 文件
            if '.partial.' in fp.name:
                continue
            month = extract_month(fp.name)
            if month:
                files.append((fp, month))
    return files


def migrate(dry_run=True, city='shanghai'):
    """
    执行迁移.

    Args:
        dry_run: True 只预览不执行
        city: 默认城市标识
    """
    files = collect_files(OUTPUT_DIR)

    if not files:
        print("没有需要迁移的文件")
        return

    print(f"找到 {len(files)} 个文件待迁移 (城市: {city})")
    print("")

    months = {}
    for src, month in files:
        months.setdefault(month, []).append(src)

    for month in sorted(months.keys()):
        dest_dir = OUTPUT_DIR / city / month
        print(f"  {city}/{month}/")
        for src in months[month]:
            dest = dest_dir / src.name
            marker = "  " if not dry_run else "[dry] "
            exists = " (已存在)" if dest.exists() else ""
            print(f"    {marker}{src.name} -> {dest.relative_to(OUTPUT_DIR)}{exists}")
            if not dry_run and not dest.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))

    # 迁移 geo cache
    old_geo = OUTPUT_DIR / "community_geo_cache.json"
    new_geo = OUTPUT_DIR / city / "community_geo_cache.json"
    if old_geo.exists() and not new_geo.exists():
        print(f"\n  community_geo_cache.json -> {city}/")
        if not dry_run:
            (OUTPUT_DIR / city).mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_geo), str(new_geo))

    if dry_run:
        print(f"\n[dry-run] 以上为预览，使用 --run 执行实际迁移")
    else:
        print(f"\n迁移完成!")


def main():
    parser = argparse.ArgumentParser(description='迁移旧格式数据到 city/month 分层目录')
    parser.add_argument('--run', action='store_true', help='执行迁移 (默认 dry-run)')
    parser.add_argument('--city', type=str, default='shanghai',
                        help='城市标识 (默认 shanghai)')
    args = parser.parse_args()

    if not OUTPUT_DIR.exists():
        print(f"output 目录不存在: {OUTPUT_DIR}")
        sys.exit(1)

    migrate(dry_run=not args.run, city=args.city)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3.10
"""
一次性提取链家租房的完整区域层级结构 (区 → 板块).

用法:
  python3.10 scrape_regions.py                     # 默认上海
  python3.10 scrape_regions.py --city beijing      # 北京
  python3.10 scrape_regions.py --city guangzhou    # 广州
输出: scraper/regions_config_{city}.json
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from scraper.browser_helpers import (
    create_browser_context,
    human_scroll,
    human_mouse_move,
)
from scraper.config import CITY_NAMES, CITY_URL_PREFIX

# 各城市的行政区 slug 白名单 (用于从页面精确匹配)
DISTRICT_SLUGS = {
    'shanghai': [
        'huangpu', 'xuhui', 'changning', 'jingan', 'putuo',
        'hongkou', 'yangpu', 'minhang', 'baoshan', 'jiading',
        'pudong', 'jinshan', 'songjiang', 'qingpu', 'fengxian',
        'chongming', 'shanghaizhoubian',
    ],
    'beijing': [
        'dongchengqu3', 'xichengqu3', 'chaoyangqu5', 'haidianqu',
        'fengtaiqu', 'shijingshanqu', 'tongzhouqu1', 'changpingqu',
        'daxingqu', 'shunyiqu', 'fangshanqu', 'mentougouqu',
        'pingguqu', 'huairouqu', 'miyunqu', 'yanqingqu',
        'beijingjingjijishukaifaqu',
    ],
    'guangzhou': [
        'tianhe', 'yuexiu', 'liwan', 'haizhu', 'panyu',
        'baiyun', 'huangpugz', 'huadou', 'nansha', 'conghua',
        'zengcheng', 'guangfuzhoubian',
    ],
    'shenzhen': [
        'luohuqu', 'futianqu', 'nanshanqu', 'yantianqu', 'baoanqu',
        'longgangqu', 'longhuaqu', 'pingshanqu', 'guangmingqu', 'dapengxinqu',
        'shenzhenzhoubianqu',
    ],
    'hangzhou': [
        'shangcheng', 'xiacheng', 'jianggan', 'gongshu', 'xihu',
        'binjiang', 'xiaoshan', 'yuhang', 'fuyang', 'linan',
        'tonglu', 'chun', 'jiande', 'dajingqu',
    ],
    'chengdu': [
        'jinjiang', 'qingyang', 'jinniu', 'wuhou', 'chenghua',
        'longquanyi', 'xindu', 'wenjiang', 'shuangliu', 'pidu',
        'xipu', 'tianfujiangbei', 'gaoxinxi', 'gaoxinnan',
        'gaoxinwai', 'chengdoushizhoubian',
    ],
    'nanjing': [
        'xuanwu', 'qinhuai', 'jianye', 'gulou', 'pukou',
        'qixia', 'yuhuatai', 'jiangning', 'liuhe', 'lishui',
        'gaochun', 'nanjingshizhoubian',
    ],
}

# 从区域页提取板块 (子区域) 的 JS
EXTRACT_BOARDS_JS = """
(parentSlug) => {
    const results = [];
    const seen = new Set();

    const allUls = document.querySelectorAll('ul');
    for (const ul of allUls) {
        const links = ul.querySelectorAll('a[href]');
        if (links.length < 3) continue;

        let isBoardRow = false;
        for (const a of links) {
            const href = a.getAttribute('href') || '';
            const text = (a.textContent || '').trim();
            if (text === '不限' && href.includes(parentSlug)) {
                isBoardRow = true;
                break;
            }
        }
        if (!isBoardRow) continue;

        for (const a of links) {
            const href = a.getAttribute('href') || '';
            const text = (a.textContent || '').trim();
            if (!text || text === '不限') continue;
            if (!/^[\\u4e00-\\u9fff]{2,6}$/.test(text)) continue;

            let path = href;
            try { path = new URL(href, location.origin).pathname; } catch(e) {}
            path = path.replace(/\\/+$/, '');
            if (!path.startsWith('/zufang/')) continue;

            const slug = path.replace('/zufang/', '');
            if (!slug || slug.includes('/') || seen.has(slug)) continue;
            if (!/^[a-z]{3,}\\d*$/.test(slug)) continue;
            if (slug === parentSlug) continue;

            seen.add(slug);
            let fullUrl = href;
            try { fullUrl = new URL(href, location.origin).href; } catch(e) {}
            if (!fullUrl.endsWith('/')) fullUrl += '/';
            results.push({ slug, name: text, url: fullUrl });
        }
        if (results.length > 0) return results;
    }
    return results;
}
"""


def build_args():
    parser = argparse.ArgumentParser(
        description='提取链家租房区域层级结构')
    parser.add_argument('--city', type=str, default='shanghai',
                        choices=list(CITY_NAMES.keys()),
                        help='城市标识 (默认: shanghai)')
    return parser.parse_args()


async def main():
    args = build_args()
    city = args.city
    city_cn = CITY_NAMES[city]
    url_prefix = CITY_URL_PREFIX[city]
    district_slugs = DISTRICT_SLUGS.get(city, [])
    base_url = f'https://{url_prefix}.lianjia.com'
    zufang_url = f'{base_url}/zufang/'

    print(f"{'=' * 60}")
    print(f"链家区域提取 | 城市: {city_cn} | {base_url}")
    print(f"{'=' * 60}")

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await create_browser_context(p)
        page = context.pages[0] if context.pages else await context.new_page()

        # 1. 访问首页
        print("访问链家首页...")
        await page.goto(base_url + '/',
                        wait_until='domcontentloaded', timeout=30000)
        await human_scroll(page)
        await human_mouse_move(page)
        await asyncio.sleep(2)

        # 2. 访问租房首页，提取所有行政区链接
        print("访问租房首页，提取行政区...")
        await page.goto(zufang_url,
                        wait_until='networkidle', timeout=30000)
        await human_scroll(page)
        await asyncio.sleep(2)

        try:
            await page.wait_for_selector('ul a[href*="/zufang/"]',
                                         timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(1)

        # 构建提取行政区的 JS (带城市专属 slug 白名单)
        district_slugs_js = json.dumps(district_slugs)
        extract_districts_js = f"""
            () => {{
                const seen = new Set();
                const results = [];
                const districtSlugs = new Set({district_slugs_js});
                document.querySelectorAll('a[href*="/zufang/"]').forEach(a => {{
                    const href = a.getAttribute('href') || '';
                    const text = (a.textContent || '').trim();
                    if (!text || text.length > 6) return;
                    if (!/^[\\u4e00-\\u9fff]{{2,4}}$/.test(text)) return;

                    let path = href;
                    try {{ path = new URL(href, location.origin).pathname; }} catch(e) {{}}
                    path = path.replace(/\\/+$/, '');
                    if (!path.startsWith('/zufang/')) return;

                    const slug = path.replace('/zufang/', '');
                    if (!slug || slug.includes('/') || seen.has(slug)) return;
                    if (!/^[a-z][a-z0-9]+$/.test(slug)) return;

                    if (districtSlugs.size > 0 && !districtSlugs.has(slug)) return;

                    seen.add(slug);
                    let fullUrl = href;
                    try {{ fullUrl = new URL(href, location.origin).href; }} catch(e) {{}}
                    if (!fullUrl.endsWith('/')) fullUrl += '/';
                    results.push({{ slug, name: text, url: fullUrl }});
                }});
                return results;
            }}
        """

        districts_raw = await page.evaluate(extract_districts_js)

        print(f"找到 {len(districts_raw)} 个行政区:")
        for d in districts_raw:
            print(f"  {d['name']} ({d['slug']})")

        # 3. 逐区访问，提取板块
        all_regions = {}
        for dist in districts_raw:
            slug = dist['slug']
            name = dist['name']
            print(f"\n提取板块: {name} ({slug})...")

            try:
                await page.goto(dist['url'], wait_until='networkidle',
                                timeout=30000)
                try:
                    await page.wait_for_selector(
                        '.content__list--item', timeout=10000)
                except Exception:
                    pass
                await human_scroll(page)
                await asyncio.sleep(2)

                boards = await page.evaluate(EXTRACT_BOARDS_JS, slug)

                all_regions[slug] = {
                    'name': name,
                    'slug': slug,
                    'boards': boards,
                }

                board_names = [b['name'] for b in boards]
                print(f"  {len(boards)} 个板块: {', '.join(board_names)}")

            except Exception as e:
                print(f"  失败: {e}")
                all_regions[slug] = {
                    'name': name,
                    'slug': slug,
                    'boards': [],
                }

            await asyncio.sleep(1.5)

        await context.close()

    # 4. 保存结果
    output_path = PROJECT_DIR / 'scraper' / f'regions_config_{city}.json'
    output_path.parent.mkdir(exist_ok=True)

    total_boards = sum(len(r['boards']) for r in all_regions.values())
    empty_districts = [r['name'] for r in all_regions.values()
                       if not r['boards']]

    output = {
        '_meta': {
            'source': zufang_url,
            'city': city_cn,
            'total_districts': len(all_regions),
            'total_boards': total_boards,
            'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        },
        'districts': all_regions,
    }

    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    print(f"\n{'=' * 60}")
    print(f"已保存: {output_path}")
    print(f"行政区: {len(all_regions)}")
    print(f"板块总数: {total_boards}")
    if empty_districts:
        print(f"无板块的区: {', '.join(empty_districts)}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    asyncio.run(main())

#!/usr/bin/env python3.10
"""
一次性提取链家上海租房的完整区域层级结构 (区 → 板块).

用法: python3.10 scrape_regions.py
输出: scraper/regions_config.json
"""

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

# 从区域页提取板块 (子区域) 的 JS
EXTRACT_BOARDS_JS = """
(parentSlug) => {
    const results = [];
    const seen = new Set();

    // 搜索全页所有 <ul>，找板块行:
    // 特征: 含 "不限" 链接且 href 包含 parentSlug
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
            // 只保留中文 2-6 字的板块名
            if (!/^[\\u4e00-\\u9fff]{2,6}$/.test(text)) continue;

            let path = href;
            try { path = new URL(href, location.origin).pathname; } catch(e) {}
            path = path.replace(/\\/+$/, '');
            if (!path.startsWith('/zufang/')) continue;

            const slug = path.replace('/zufang/', '');
            if (!slug || slug.includes('/') || seen.has(slug)) continue;
            // 至少 3 个字母 (排除 l0, f100500000009 等筛选编码)
            if (!/^[a-z]{3,}\\d*$/.test(slug)) continue;
            if (slug === parentSlug) continue;

            // 排除其他行政区 slug
            const districtSlugs = [
                'huangpu','xuhui','changning','jingan','putuo',
                'hongkou','yangpu','minhang','baoshan','jiading',
                'pudong','jinshan','songjiang','qingpu','fengxian',
                'chongming','shanghaizhoubian'
            ];
            if (districtSlugs.includes(slug)) continue;

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


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await create_browser_context(p)
        page = context.pages[0] if context.pages else await context.new_page()

        # 1. 访问首页
        print("访问链家首页...")
        await page.goto('https://sh.lianjia.com/',
                        wait_until='domcontentloaded', timeout=30000)
        await human_scroll(page)
        await human_mouse_move(page)
        await asyncio.sleep(2)

        # 2. 访问租房首页，提取所有行政区链接
        print("访问租房首页，提取行政区...")
        await page.goto('https://sh.lianjia.com/zufang/',
                        wait_until='networkidle', timeout=30000)
        await human_scroll(page)
        await asyncio.sleep(2)

        # 等待筛选器加载
        try:
            await page.wait_for_selector('ul a[href*="/zufang/"]', timeout=10000)
        except Exception:
            pass
        await asyncio.sleep(1)

        # 提取行政区: 搜索所有 /zufang/{slug}/ 链接，排除板块级
        districts_raw = await page.evaluate("""
            () => {
                const seen = new Set();
                const results = [];
                const districtSlugs = new Set([
                    'huangpu','xuhui','changning','jingan','putuo',
                    'hongkou','yangpu','minhang','baoshan','jiading',
                    'pudong','jinshan','songjiang','qingpu','fengxian',
                    'chongming','shanghaizhoubian'
                ]);
                document.querySelectorAll('a[href*="/zufang/"]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const text = (a.textContent || '').trim();
                    if (!text || text.length > 6) return;
                    if (!/^[\\u4e00-\\u9fff]{2,4}$/.test(text)) return;

                    let path = href;
                    try { path = new URL(href, location.origin).pathname; } catch(e) {}
                    path = path.replace(/\\/+$/, '');
                    if (!path.startsWith('/zufang/')) return;

                    const slug = path.replace('/zufang/', '');
                    if (!slug || slug.includes('/') || seen.has(slug)) return;
                    if (!/^[a-z]+$/.test(slug)) return;

                    // 只保留纯字母 slug (行政区级)
                    if (!districtSlugs.has(slug)) return;

                    seen.add(slug);
                    let fullUrl = href;
                    try { fullUrl = new URL(href, location.origin).href; } catch(e) {}
                    if (!fullUrl.endsWith('/')) fullUrl += '/';
                    results.push({ slug, name: text, url: fullUrl });
                });
                return results;
            }
        """)

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

            # 区域间休息
            await asyncio.sleep(1.5)

        await context.close()

    # 4. 保存结果
    output_path = PROJECT_DIR / 'scraper' / 'regions_config.json'
    output_path.parent.mkdir(exist_ok=True)

    # 统计
    total_boards = sum(len(r['boards']) for r in all_regions.values())
    empty_districts = [r['name'] for r in all_regions.values()
                       if not r['boards']]

    output = {
        '_meta': {
            'source': 'https://sh.lianjia.com/zufang/',
            'city': '上海',
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

    print(f"\n{'=' * 50}")
    print(f"已保存: {output_path}")
    print(f"行政区: {len(all_regions)}")
    print(f"板块总数: {total_boards}")
    if empty_districts:
        print(f"无板块的区: {', '.join(empty_districts)}")
    print(f"{'=' * 50}")


if __name__ == '__main__':
    asyncio.run(main())

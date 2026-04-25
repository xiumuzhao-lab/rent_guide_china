#!/usr/bin/env python3.10
"""
诊断脚本: 检测浦东页面子区域链接提取是否正常。
不爬取数据，只打印页面结构和提取结果。
"""

import asyncio
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from scraper.browser_helpers import (
    EXTRACT_SUBAREAS_JS,
    create_browser_context,
    human_scroll,
    human_mouse_move,
)


async def debug():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await create_browser_context(p)
        page = context.pages[0] if context.pages else await context.new_page()

        # 1. 先访问链家首页
        print("=== 访问链家首页 ===")
        await page.goto('https://sh.lianjia.com/',
                        wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 2. 访问浦东租房页面
        print("\n=== 访问浦东租房页 ===")
        await page.goto('https://sh.lianjia.com/zufang/pudong/',
                        wait_until='domcontentloaded', timeout=30000)
        await human_scroll(page)
        await human_mouse_move(page)
        await asyncio.sleep(2)

        url = page.url
        print(f"当前 URL: {url}")
        title = await page.title()
        print(f"页面标题: {title}")

        # 3. 检查页面上所有含 /zufang/ 的链接
        print("\n=== 页面中所有 /zufang/ 链接 ===")
        all_zufang_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href*="/zufang/"]').forEach(a => {
                    links.push({
                        text: (a.textContent || '').trim().substring(0, 30),
                        href: a.getAttribute('href') || '',
                        className: a.className || '',
                    });
                });
                return links;
            }
        """)
        for i, link in enumerate(all_zufang_links):
            print(f"  [{i}] text={link['text']!r}  href={link['href']!r}  class={link['className']!r}")

        # 4. 检查分页信息
        print("\n=== 分页信息 ===")
        pagination = await page.evaluate("""
            () => {
                const pg = document.querySelector('.content__pg');
                if (!pg) return '未找到 .content__pg';
                return {
                    html: pg.innerHTML.substring(0, 500),
                    total: pg.getAttribute('data-total'),
                    currentPage: pg.getAttribute('data-curpage'),
                };
            }
        """)
        print(f"  {pagination}")

        # 5. 运行 EXTRACT_SUBAREAS_JS
        print("\n=== EXTRACT_SUBAREAS_JS 结果 ===")
        subareas = await page.evaluate(EXTRACT_SUBAREAS_JS, 'pudong')
        if subareas:
            for sa in subareas:
                print(f"  slug={sa.get('slug')!r}  name={sa.get('name')!r}  url={sa.get('url')!r}")
        else:
            print("  (空) 未提取到任何子区域!")

        # 6. 检查筛选器/区域选择器的结构
        print("\n=== 区域筛选器 HTML 片段 ===")
        filter_info = await page.evaluate("""
            () => {
                const results = [];
                // 检查各种可能的筛选器容器
                const selectors = [
                    '.filter', '.filter__list', '.filter__item',
                    '[data-type="area"]', '.filter__area',
                    '.filter__list--selected', '.filter__item--level2',
                    '[class*="area"]', '[class*="region"]',
                    '[class*="district"]', '[class*="subway"]',
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        results.push({
                            selector: sel,
                            count: els.length,
                            sample: els[0].outerHTML.substring(0, 200),
                        });
                    }
                }
                return results;
            }
        """)
        for info in filter_info:
            print(f"  {info['selector']} ({info['count']}个)")
            print(f"    样本: {info['sample']}")

        await context.close()

    print("\n=== 诊断完成 ===")


if __name__ == '__main__':
    asyncio.run(debug())

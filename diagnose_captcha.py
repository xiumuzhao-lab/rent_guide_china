#!/usr/bin/env python3
"""
诊断链家验证码: 快速触发验证码, 截图并 dump HTML 结构。
"""

import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).parent / "output"
USER_DATA_DIR = Path(__file__).parent / ".browser_data"

EXTRACT_JS = """
() => {
    // 收集页面上所有可能的验证码相关元素
    const results = {};

    // 1. 检查常见验证码容器
    const selectors = [
        '.captcha-container', '.tc-captcha', '.geetest_panel',
        '#captcha', '.verify-wrap', '.verify-content',
        '.captcha', '.baxia-dialog', '.J_captcha',
        '.slider-btn', '.tc-slider-handle', '.geetest_slider_button',
        '.captcha-slider-btn', '.drag-btn', '.slider-thumb',
        '.nc_iconfont', '.btn_slide', '.slide-btn',
        '[class*="captcha"]', '[class*="verify"]', '[class*="slider"]',
        '[id*="captcha"]', '[id*="verify"]',
        'iframe',  // 验证码可能在 iframe 里
    ];

    selectors.forEach(sel => {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
            results[sel] = Array.from(els).map(el => ({
                tag: el.tagName,
                id: el.id || '',
                className: el.className || '',
                src: el.src || '',
                visible: el.offsetParent !== null,
                width: el.offsetWidth,
                height: el.offsetHeight,
                innerHTML_len: el.innerHTML.length,
                text: (el.textContent || '').substring(0, 200),
            }));
        }
    });

    // 2. 页面标题和URL
    results['_meta'] = {
        title: document.title,
        url: location.href,
    };

    return results;
}
"""


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        USER_DATA_DIR.mkdir(exist_ok=True)
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel='chrome',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--window-size=1440,900',
            ],
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.pages[0] if context.pages else await context.new_page()

        # 先访问首页
        print("访问链家首页...")
        await page.goto('https://sh.lianjia.com/', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # 快速翻页触发验证码
        print("快速翻页触发验证码...")
        captcha_triggered = False
        for pg in range(1, 15):
            url = f"https://sh.lianjia.com/zufang/changning/pg{pg}/"
            print(f"  第{pg}页: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(0.5, 1.5))

            title = await page.title()
            url_now = page.url
            if 'CAPTCHA' in title or '验证' in title or '登录' in title or '/login' in url_now:
                print(f"\n✓ 验证码已触发! title={title}, url={url_now}")
                captcha_triggered = True
                break

        if not captcha_triggered:
            print("未触发验证码, 再试一轮...")
            for pg in range(15, 30):
                url = f"https://sh.lianjia.com/zufang/changning/pg{pg}/"
                print(f"  第{pg}页: {url}")
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(random.uniform(0.3, 0.8))
                title = await page.title()
                if 'CAPTCHA' in title or '验证' in title or '登录' in title:
                    print(f"\n✓ 验证码已触发! title={title}")
                    captcha_triggered = True
                    break

        if not captcha_triggered:
            print("未能触发验证码, 截取当前页面作为参考")

        # 等验证码完全加载
        await asyncio.sleep(3)

        # 截图
        screenshot_path = OUTPUT_DIR / "captcha_diagnose.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"\n截图已保存: {screenshot_path}")

        # Dump HTML 结构
        elements_info = await page.evaluate(EXTRACT_JS)
        dump_path = OUTPUT_DIR / "captcha_elements.json"
        dump_path.write_text(json.dumps(elements_info, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"元素信息已保存: {dump_path}")

        # 打印关键信息
        print(f"\n页面标题: {await page.title()}")
        print(f"页面URL: {page.url}")
        print(f"\n匹配到的元素:")
        for sel, els in elements_info.items():
            if sel == '_meta':
                continue
            print(f"\n  选择器: {sel}")
            for el in els:
                print(f"    <{el['tag']}> id='{el['id']}' class='{el['className'][:80]}'"
                      f" visible={el['visible']} {el['width']}x{el['height']}"
                      f" src='{el['src'][:80]}'")

        # 也 dump 完整 HTML 方便调试
        html_path = OUTPUT_DIR / "captcha_page.html"
        html_content = await page.content()
        html_path.write_text(html_content, encoding='utf-8')
        print(f"\n完整HTML已保存: {html_path}")

        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

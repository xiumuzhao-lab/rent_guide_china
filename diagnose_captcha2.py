#!/usr/bin/env python3.10
"""
诊断链家验证码 v2: 触发验证码，截图并 dump DOM 结构。
"""

import asyncio
import json
import random
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
import sys
sys.path.insert(0, str(PROJECT_DIR))

USER_DATA_DIR = PROJECT_DIR / ".browser_data"
OUTPUT_DIR = PROJECT_DIR / "output"

DUMP_DOM_JS = """
() => {
    const results = {};

    // 1. 查找所有 geetest 相关元素
    const allEls = document.querySelectorAll('*');
    const geetestEls = [];
    for (const el of allEls) {
        const cls = el.className || '';
        const id = el.id || '';
        if (typeof cls === 'string' && (cls.includes('geetest') || cls.includes('captcha') || cls.includes('verify'))
            || (typeof id === 'string' && (id.includes('geetest') || id.includes('captcha')))) {
            const bb = el.getBoundingClientRect();
            geetestEls.push({
                tag: el.tagName,
                id: id,
                class: cls.substring(0, 200),
                visible: bb.width > 0 && bb.height > 0,
                width: Math.round(bb.width),
                height: Math.round(bb.height),
                x: Math.round(bb.x),
                y: Math.round(bb.y),
                children: el.children.length,
                text: (el.textContent || '').substring(0, 100).trim(),
            });
        }
    }
    results['geetest_elements'] = geetestEls;

    // 2. 查找 iframe
    const iframes = document.querySelectorAll('iframe');
    results['iframes'] = Array.from(iframes).map(f => ({
        src: f.src || '',
        id: f.id || '',
        class: f.className || '',
        width: f.offsetWidth,
        height: f.offsetHeight,
    }));

    // 3. 页面信息
    results['page'] = {
        title: document.title,
        url: location.href,
        bodyText: document.body ? document.body.innerText.substring(0, 500) : '',
    };

    return results;
}
"""


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    from playwright.async_api import async_playwright
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
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = context.pages[0] if context.pages else await context.new_page()

        print("访问链家首页...")
        await page.goto('https://sh.lianjia.com/',
                        wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        print("触发验证码...")
        for pg in range(1, 20):
            url = f"https://sh.lianjia.com/zufang/zhangjiang/pg{pg}/"
            print(f"  第{pg}页...", end=" ", flush=True)
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            title = await page.title()
            print(f"title={title[:30]}")
            if '验证' in title or 'CAPTCHA' in title or '登录' in title:
                print(f"\n验证码已触发!")
                break

        # 等待验证码完全加载
        print("等待验证码加载...")
        await asyncio.sleep(5)

        # 截图
        ss_path = OUTPUT_DIR / "captcha_diag2_full.png"
        await page.screenshot(path=str(ss_path), full_page=False)
        print(f"截图: {ss_path}")

        # Dump DOM
        dom_info = await page.evaluate(DUMP_DOM_JS)
        dump_path = OUTPUT_DIR / "captcha_diag2.json"
        dump_path.write_text(
            json.dumps(dom_info, ensure_ascii=False, indent=2),
            encoding='utf-8')
        print(f"DOM: {dump_path}")

        # 打印关键信息
        print(f"\n页面: title={dom_info['page']['title']}")
        print(f"      url={dom_info['page']['url']}")
        print(f"\n--- iframe ({len(dom_info['iframes'])}) ---")
        for f in dom_info['iframes']:
            print(f"  {f['tag']} id={f['id']} src={f['src'][:100]} "
                  f"{f['width']}x{f['height']}")
        print(f"\n--- geetest/captcha 元素 ({len(dom_info['geetest_elements'])}) ---")
        for el in dom_info['geetest_elements']:
            print(f"  <{el['tag']}> id='{el['id']}' "
                  f"class='{el['class'][:80]}' "
                  f"vis={el['visible']} {el['width']}x{el['height']} "
                  f"@({el['x']},{el['y']}) children={el['children']}")
            if el['text']:
                print(f"    text: {el['text'][:80]}")

        # 也检查 iframe 内部
        for f_info in dom_info['iframes']:
            if f_info['src'] and f_info['width'] > 0:
                try:
                    frame = page.frame_locator(f"iframe[src='{f_info['src'][:100]}']")
                    inner = await frame.locator('body').inner_text()
                    print(f"\n--- iframe 内容 ({f_info['src'][:60]}) ---")
                    print(inner[:300])
                except Exception as e:
                    print(f"\n  iframe 内容获取失败: {e}")

        # 保存完整 HTML
        html_path = OUTPUT_DIR / "captcha_diag2.html"
        html_content = await page.content()
        html_path.write_text(html_content, encoding='utf-8')
        print(f"\nHTML: {html_path}")

        await context.close()
        print("\n诊断完成!")


if __name__ == '__main__':
    asyncio.run(main())

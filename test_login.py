#!/usr/bin/env python3.10
"""
登录流程测试: 逐步操作并截图，定位失败原因。
"""

import asyncio
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

USER_DATA_DIR = PROJECT_DIR / ".browser_data"
OUTPUT_DIR = PROJECT_DIR / "output"
SCREENSHOT_DIR = OUTPUT_DIR / "login_debug"


async def main():
    os.environ.clear()
    # 重新加载 .env
    env_file = PROJECT_DIR / '.env'
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ[k.strip()] = v.strip()

    phone = os.environ['LIANJIA_PHONE']
    password = os.environ['LIANJIA_PASSWORD']
    print(f"账号: {phone[:3]}****{phone[-4:]}")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False, channel='chrome',
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--window-size=1440,900',
            ],
            viewport={'width': 1440, 'height': 900}, locale='zh-CN',
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/131.0.0.0 Safari/537.36')
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}};
        """)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Step 1: 先访问首页，建立 cookie
        print("\n[Step 1] 访问首页...")
        await page.goto('https://sh.lianjia.com/', wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        await page.screenshot(path=str(SCREENSHOT_DIR / '01_home.png'))

        # Step 2: 导航到登录页 (模拟真实跳转)
        print("\n[Step 2] 访问张江租房 (触发登录跳转)...")
        await page.goto('https://sh.lianjia.com/zufang/zhangjiang/',
                        wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)
        print(f"  URL: {page.url}")
        print(f"  Title: {await page.title()}")
        await page.screenshot(path=str(SCREENSHOT_DIR / '02_login_redirect.png'))

        is_login = 'clogin' in page.url or '登录' in await page.title()
        if not is_login:
            print("  没有跳转到登录页，可能已登录，直接测试爬取")
            await ctx.close()
            return

        # Step 3: 等待表单完全加载
        print("\n[Step 3] 等待登录表单加载...")
        try:
            await page.wait_for_selector('input[placeholder="请输入手机号"]', timeout=15000)
            print("  表单已出现")
        except Exception:
            print("  等待超时，尝试 networkidle...")
            await page.goto(page.url, wait_until='networkidle', timeout=30000)
            await page.wait_for_selector('input[placeholder="请输入手机号"]', timeout=15000)

        # 等安全 SDK 初始化
        print("  等待安全 SDK 初始化 (5s)...")
        await asyncio.sleep(5)
        await page.screenshot(path=str(SCREENSHOT_DIR / '03_form_loaded.png'))

        # dump 当前所有 input 状态
        form_state = await page.evaluate('''() => {
            const r = {};
            document.querySelectorAll('input').forEach((el, i) => {
                r['input_'+i] = {
                    type: el.type, placeholder: el.placeholder,
                    value: el.value, checked: el.checked,
                    disabled: el.disabled, visible: el.offsetWidth > 0,
                    rect: el.getBoundingClientRect()
                };
            });
            const btn = document.querySelector('button');
            if (btn) r['button'] = {
                text: btn.textContent.trim(), disabled: btn.disabled,
                rect: btn.getBoundingClientRect()
            };
            return r;
        }''')
        print(f"  表单状态: {json.dumps(form_state, ensure_ascii=False, default=str)}")

        # Step 4: 输入手机号
        print("\n[Step 4] 输入手机号...")
        phone_input = await page.query_selector('input[placeholder="请输入手机号"]')
        await phone_input.click()
        await asyncio.sleep(0.5)
        await phone_input.fill('')  # 清空
        await asyncio.sleep(0.3)
        # 用 keyboard.type 模拟真实输入
        await page.keyboard.type(phone, delay=80)
        actual_phone = await phone_input.evaluate('el => el.value')
        print(f"  实际输入: {actual_phone}")
        await page.screenshot(path=str(SCREENSHOT_DIR / '04_phone_entered.png'))

        # Step 5: 输入密码
        print("\n[Step 5] 输入密码...")
        pwd_input = await page.query_selector('input[type="password"]')
        await pwd_input.click()
        await asyncio.sleep(0.5)
        await pwd_input.fill('')
        await asyncio.sleep(0.3)
        await page.keyboard.type(password, delay=80)
        actual_pwd = await pwd_input.evaluate('el => el.value')
        print(f"  密码长度: {len(actual_pwd)}")
        await page.screenshot(path=str(SCREENSHOT_DIR / '05_pwd_entered.png'))

        # Step 6: 勾选协议
        print("\n[Step 6] 勾选协议...")
        checkbox = await page.query_selector('input[type="checkbox"]')
        checked = await checkbox.evaluate('el => el.checked')
        print(f"  当前勾选状态: {checked}")
        if not checked:
            await checkbox.click()
            await asyncio.sleep(0.5)
            checked = await checkbox.evaluate('el => el.checked')
            print(f"  点击后: {checked}")
        await page.screenshot(path=str(SCREENSHOT_DIR / '06_agreed.png'))

        # Step 7: 点击登录
        print("\n[Step 7] 点击登录...")
        login_btn = await page.query_selector('button[type="submit"]')
        bb = await login_btn.bounding_box()
        print(f"  按钮位置: {bb}")

        # 监听网络请求
        responses = []
        def on_response(response):
            if 'login' in response.url or 'auth' in response.url:
                responses.append({
                    'url': response.url[:100],
                    'status': response.status,
                })
        page.on('response', on_response)

        await page.mouse.click(bb['x'] + bb['width'] / 2, bb['y'] + bb['height'] / 2)
        print("  已点击")
        await page.screenshot(path=str(SCREENSHOT_DIR / '07_clicked.png'))

        # Step 8: 等待结果
        print("\n[Step 8] 等待登录响应...")
        for i in range(15):
            await asyncio.sleep(1)
            url = page.url
            title = await page.title()
            print(f"  [{i+1}s] url={url[:60]} title={title[:30]}")

            # 检查错误
            error = await page.evaluate('''() => {
                const el = document.querySelector('[class*="error"], [class*="toast"], [class*="warn"]');
                return el ? el.textContent.trim().substring(0, 100) : '';
            }''')
            if error:
                print(f"  错误提示: {error}")

            if 'clogin' not in url and '登录' not in title:
                print(f"\n  登录成功! 跳转到: {url}")
                await page.screenshot(path=str(SCREENSHOT_DIR / '08_login_success.png'))
                await ctx.close()
                return

        await page.screenshot(path=str(SCREENSHOT_DIR / '08_login_result.png'))
        print(f"\n  网络请求: {json.dumps(responses, ensure_ascii=False)}")

        print("\n登录未成功，截图已保存到 output/login_debug/")
        await ctx.close()


if __name__ == '__main__':
    asyncio.run(main())

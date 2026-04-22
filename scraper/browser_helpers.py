"""
浏览器辅助模块

Playwright 浏览器上下文创建、人类行为模拟、页面延迟计算、数据提取 JS。
"""

import asyncio
import random

from scraper.config import USER_DATA_DIR


# ============================================================
# JavaScript 数据提取脚本
# ============================================================

EXTRACT_JS = """
() => {
    const items = document.querySelectorAll('.content__list--item');
    const results = [];

    items.forEach(item => {
        const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();

        // ---- 标题和链接 ----
        const titleEl = item.querySelector('.content__list--item--title a')
            || item.querySelector('.title a')
            || item.querySelector('a');
        const title = clean(titleEl ? titleEl.textContent : '');
        const url = titleEl ? titleEl.href : '';

        // ---- 从标题解析: 社区/户型/朝向 ----
        let rentType = '', community = '', rooms = '', direction = '';
        const titleMatch = title.match(/^(.*?)·(.+?)\\s+(\\d+室\\d*厅\\d*卫?)\\s*([南北东西\\/\\s]*?)$/);
        if (titleMatch) {
            rentType = clean(titleMatch[1]);
            community = clean(titleMatch[2]);
            rooms = clean(titleMatch[3]);
            direction = clean(titleMatch[4]);
        } else {
            const dotIdx = title.indexOf('·');
            if (dotIdx >= 0) {
                const afterDot = title.substring(dotIdx + 1);
                const roomMatch = afterDot.match(/^(.+?)\\s+(\\d+室\\d*厅\\d*卫?)\\s*([南北东西\\/\\s]*)/);
                if (roomMatch) {
                    community = clean(roomMatch[1]);
                    rooms = clean(roomMatch[2]);
                    direction = clean(roomMatch[3]);
                } else {
                    community = clean(afterDot);
                }
            }
            rentType = dotIdx >= 0 ? clean(title.substring(0, dotIdx)) : '';
        }

        // ---- 描述信息 ----
        let area = '', floor = '';
        const desEl = item.querySelector('.content__list--item--des')
            || item.querySelector('.des');
        if (desEl) {
            const desText = clean(desEl.textContent);
            const areaMatch = desText.match(/([\\d.]+)㎡/);
            if (areaMatch) area = areaMatch[1];
            const floorMatch = desText.match(/([\\u4e00\\u9fa5]+楼层\\s*[（(]\\s*\\d+层\\s*[）)])/);
            if (floorMatch) floor = clean(floorMatch[1]);
        }

        // ---- 价格 ----
        const priceEl = item.querySelector('.content__list--item-price em')
            || item.querySelector('.price em');
        const price = clean(priceEl ? priceEl.textContent : '');

        // ---- 标签 ----
        const tagEls = item.querySelectorAll(
            '.content__list--item--tag span, .content__list--item--bottom .tag span, .tag span'
        );
        const tags = Array.from(tagEls)
            .map(el => clean(el.textContent))
            .filter(t => t && t.length < 20)
            .join(',');

        // ---- 来源/品牌 ----
        const sourceEl = item.querySelector('.content__list--item--brand')
            || item.querySelector('.brand');
        let source = '';
        if (sourceEl) {
            source = clean(sourceEl.childNodes[0] ? sourceEl.childNodes[0].textContent : sourceEl.textContent);
            if (source.length > 10) source = source.split(/\\s+/)[0];
        }

        if (title || price) {
            results.push({
                title, community, area, rooms, direction,
                floor, price, tags, source, url,
                rent_type: rentType,
            });
        }
    });

    return results;
}
"""


# ============================================================
# 浏览器上下文创建
# ============================================================

async def create_browser_context(playwright):
    """
    创建持久化浏览器上下文 (共享 cookie).

    Args:
        playwright: Playwright 实例

    Returns:
        BrowserContext: 浏览器上下文
    """
    USER_DATA_DIR.mkdir(exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        channel='chrome',
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=AutomationControlled',
            '--no-sandbox',
            '--window-size=1440,900',
            '--disable-infobars',
        ],
        viewport={'width': 1440, 'height': 900},
        locale='zh-CN',
        user_agent=(
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
    )
    await context.add_init_script("""
        // 隐藏 webdriver 标志
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };

        // 修复 permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );

        // 让 JSONP 回调正常工作 (GeeTest 依赖 JSONP)
        // 不拦截任何 script 标签加载
    """)
    return context


# ============================================================
# 人类行为模拟
# ============================================================

async def human_scroll(page):
    """
    模拟人类滚动浏览页面.

    Args:
        page: Playwright Page 对象
    """
    try:
        for _ in range(random.randint(1, 3)):
            scroll_y = random.randint(200, 500)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.2, 0.5))
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(0.1, 0.2))
    except Exception:
        pass


async def human_mouse_move(page):
    """
    模拟随机鼠标移动.

    Args:
        page: Playwright Page 对象
    """
    try:
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, 1300)
            y = random.randint(100, 800)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


async def mouse_click_selector(page, selector):
    """
    用 page.mouse.click 点击元素 (绕过遮罩层拦截).

    Args:
        page: Playwright Page 对象
        selector: CSS 选择器
    """
    el = await page.query_selector(selector)
    if not el:
        return
    box = await el.bounding_box()
    if not box:
        return
    await page.mouse.click(
        box['x'] + box['width'] / 2,
        box['y'] + box['height'] / 2,
    )


def get_page_delay(page_num: int, had_captcha: bool = False) -> float:
    """
    根据页码动态计算延迟.

    越往后延迟越长，模拟人类疲劳；验证码后额外休息；每5页长休息。

    Args:
        page_num: 当前页码
        had_captcha: 刚刚是否处理过验证码

    Returns:
        float: 延迟秒数
    """
    base = random.uniform(2.0, 5.0)
    if page_num > 3:
        base += (page_num - 3) * random.uniform(0.2, 0.5)
    if had_captcha:
        base += random.uniform(3, 8)
    if page_num % 5 == 0:
        base += random.uniform(8, 15)
    if random.random() < 0.08:
        base += random.uniform(2, 4)
    return base

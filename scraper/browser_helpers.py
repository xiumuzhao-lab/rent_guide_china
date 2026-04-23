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
        let area = '', floor = '', location = '';
        const desEl = item.querySelector('.content__list--item--des')
            || item.querySelector('.des');
        if (desEl) {
            const desText = clean(desEl.textContent);
            const areaMatch = desText.match(/([\\d.]+)㎡/);
            if (areaMatch) area = areaMatch[1];
            const floorMatch = desText.match(/([\\u4e00\\u9fa5]+楼层\\s*[（(]\\s*\\d+层\\s*[）)])/);
            if (floorMatch) floor = clean(floorMatch[1]);
            // 提取位置: "浦东-御桥-xxx" 格式
            const locMatch = desText.match(
                /([\\u4e00-\\u9fff]+-[\\u4e00-\\u9fff]+(?:-[\\u4e00-\\u9fff(\\)]+)?)/
            );
            if (locMatch) location = locMatch[1];
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
                location,
            });
        }
    });

    return results;
}
"""

# 提取页面上的子区域链接 (用于大区域下钻)
# 三级搜索策略: filter 容器 → 全页 <ul> → 全页链接
# 子区域链接是直接路径 (如 /zufang/beicai/)，不是嵌套路径
EXTRACT_SUBAREAS_JS = """
(parentSlug) => {
    const results = [];
    const seen = new Set();

    function tryAddLink(a) {
        const href = a.getAttribute('href') || '';
        const text = (a.textContent || '').trim();
        if (!text || text === '不限') return;
        let path = href;
        try { path = new URL(href, location.origin).pathname; } catch(e) {}
        path = path.replace(/\\/+$/, '');
        if (!path.startsWith('/zufang/')) return;
        const slug = path.replace('/zufang/', '');
        if (!slug || slug.includes('/') || seen.has(slug)) return;
        if (!/^[a-z]{3,}\\d*$/.test(slug)) return;
        if (slug === parentSlug) return;
        seen.add(slug);
        let fullUrl = href;
        try { fullUrl = new URL(href, location.origin).href; } catch(e) {}
        if (!fullUrl.endsWith('/')) fullUrl += '/';
        results.push({ slug: slug, name: text, url: fullUrl });
    }

    // 策略 1: filter 容器内查找
    const filterEl = document.querySelector('.filter')
                  || document.querySelector('#filter');
    if (filterEl) {
        const uls = filterEl.querySelectorAll('ul');
        for (const ul of uls) {
            const links = ul.querySelectorAll('a[href]');
            let isRow = false;
            for (const a of links) {
                const h = a.getAttribute('href') || '';
                const t = (a.textContent || '').trim();
                if (t === '不限' && h.includes(parentSlug)) { isRow = true; break; }
            }
            if (isRow) {
                links.forEach(a => tryAddLink(a));
                if (results.length > 0) return results;
            }
        }
    }

    // 策略 2: 全页所有 <ul> 中查找"不限"+parentSlug 行
    for (const ul of document.querySelectorAll('ul')) {
        const links = ul.querySelectorAll('a[href]');
        if (links.length < 3) continue;
        let isRow = false;
        for (const a of links) {
            const h = a.getAttribute('href') || '';
            const t = (a.textContent || '').trim();
            if (t === '不限' && h.includes(parentSlug)) { isRow = true; break; }
        }
        if (isRow) {
            links.forEach(a => tryAddLink(a));
            if (results.length > 0) return results;
        }
    }

    // 策略 3: 全页搜索 /zufang/ 链接 (中文 2-6 字，在列表容器内)
    for (const a of document.querySelectorAll('a[href*="/zufang/"]')) {
        const text = (a.textContent || '').trim();
        if (!/^[\\u4e00-\\u9fff]{2,6}$/.test(text)) continue;
        const p = a.parentElement;
        if (!p) continue;
        const tag = p.tagName.toLowerCase();
        if (tag !== 'li' && tag !== 'span' && tag !== 'div') continue;
        tryAddLink(a);
    }
    return results;
}
"""

# 兜底方案: 从房源描述中提取子区域名称，再匹配页面链接
EXTRACT_SUBAREAS_FROM_LISTINGS_JS = """
(parentSlug) => {
    const results = [];
    const seen = new Set();
    const subareaNames = new Set();

    // 1. 从房源描述 "长宁-虹桥-xxx" 中提取子区域名
    document.querySelectorAll('.content__list--item--des').forEach(el => {
        const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        const m = text.match(/[\\u4e00-\\u9fff]+-([\\u4e00-\\u9fff]+)/);
        if (m) subareaNames.add(m[1]);
    });
    if (subareaNames.size === 0) return results;

    // 2. 在全页搜索与子区域名匹配的 /zufang/ 链接
    document.querySelectorAll('a[href*="/zufang/"]').forEach(a => {
        const href = a.getAttribute('href') || '';
        const text = (a.textContent || '').trim();
        if (!subareaNames.has(text)) return;
        let path = href;
        try { path = new URL(href, location.origin).pathname; } catch(e) {}
        path = path.replace(/\\/+$/, '');
        if (!path.startsWith('/zufang/')) return;
        const slug = path.replace('/zufang/', '');
        if (!slug || slug.includes('/') || seen.has(slug)) return;
        if (!/^[a-z]{3,}\\d*$/.test(slug)) return;
        if (slug === parentSlug) return;
        seen.add(slug);
        let fullUrl = href;
        try { fullUrl = new URL(href, location.origin).href; } catch(e) {}
        if (!fullUrl.endsWith('/')) fullUrl += '/';
        results.push({ slug, name: text, url: fullUrl });
    });
    return results;
}
"""

# 已知大区域的子区域列表 (作为自动检测失败时的后备)
# 注意: 子区域链接是直接路径如 /zufang/beicai/，不是嵌套路径
KNOWN_SUBAREAS = {
    'pudong': [
        {'slug': 'beicai', 'name': '北蔡'},
        {'slug': 'biyun', 'name': '碧云'},
        {'slug': 'caolu', 'name': '曹路'},
        {'slug': 'chuansha', 'name': '川沙'},
        {'slug': 'datuanzhen', 'name': '大团镇'},
        {'slug': 'geqing', 'name': '合庆'},
        {'slug': 'gaohang', 'name': '高行'},
        {'slug': 'gaodong', 'name': '高东'},
        {'slug': 'huamu', 'name': '花木'},
        {'slug': 'hangtou', 'name': '航头'},
        {'slug': 'huinan', 'name': '惠南'},
        {'slug': 'jinqiao', 'name': '金桥'},
        {'slug': 'jinyang', 'name': '金杨'},
        {'slug': 'kangqiao', 'name': '康桥'},
        {'slug': 'lujiazui', 'name': '陆家嘴'},
        {'slug': 'laogangzhen', 'name': '老港镇'},
        {'slug': 'lingangxincheng', 'name': '临港新城'},
        {'slug': 'lianyang', 'name': '联洋'},
        {'slug': 'meiyuan1', 'name': '梅园'},
        {'slug': 'nichengzhen', 'name': '泥城镇'},
        {'slug': 'nanmatou', 'name': '南码头'},
        {'slug': 'sanlin', 'name': '三林'},
        {'slug': 'shibo', 'name': '世博'},
        {'slug': 'shuyuanzhen', 'name': '书院镇'},
        {'slug': 'tangqiao', 'name': '塘桥'},
        {'slug': 'tangzhen', 'name': '唐镇'},
        {'slug': 'waigaoqiao', 'name': '外高桥'},
        {'slug': 'wanxiangzhen', 'name': '万祥镇'},
        {'slug': 'weifang', 'name': '潍坊'},
        {'slug': 'xuanqiao', 'name': '宣桥'},
        {'slug': 'xinchang', 'name': '新场'},
        {'slug': 'yuqiao1', 'name': '御桥'},
        {'slug': 'yangsiqiantan', 'name': '杨思前滩'},
        {'slug': 'yangdong', 'name': '杨东'},
        {'slug': 'yuanshen', 'name': '源深'},
        {'slug': 'yangjing', 'name': '洋泾'},
        {'slug': 'zhangjiang', 'name': '张江'},
        {'slug': 'zhuqiao', 'name': '祝桥'},
        {'slug': 'zhoupu', 'name': '周浦'},
    ],
    'changning': [
        {'slug': 'beixinjing', 'name': '北新泾'},
        {'slug': 'hongqiao1', 'name': '虹桥'},
        {'slug': 'tianshan', 'name': '天山'},
        {'slug': 'xianxia', 'name': '仙霞'},
        {'slug': 'xinhualu', 'name': '新华路'},
        {'slug': 'zhenninglu', 'name': '镇宁路'},
        {'slug': 'zhongshangongyuan', 'name': '中山公园'},
    ],
}


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
        for _ in range(random.randint(1, 2)):
            scroll_y = random.randint(200, 400)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.1, 0.3))
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(0.05, 0.1))
    except Exception:
        pass


async def human_mouse_move(page):
    """
    模拟随机鼠标移动.

    Args:
        page: Playwright Page 对象
    """
    try:
        for _ in range(random.randint(1, 2)):
            x = random.randint(100, 1300)
            y = random.randint(100, 800)
            await page.mouse.move(x, y, steps=random.randint(3, 8))
            await asyncio.sleep(random.uniform(0.05, 0.15))
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

    越往后延迟越长，模拟人类疲劳；验证码后额外休息。

    Args:
        page_num: 当前页码
        had_captcha: 刚刚是否处理过验证码

    Returns:
        float: 延迟秒数
    """
    base = random.uniform(1.0, 2.5)
    if page_num > 5:
        base += (page_num - 5) * random.uniform(0.1, 0.3)
    if had_captcha:
        base += random.uniform(2, 4)
    if page_num % 10 == 0:
        base += random.uniform(3, 6)
    return base

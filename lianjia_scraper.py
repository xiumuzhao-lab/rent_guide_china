#!/usr/bin/env python3
"""
链家租房数据爬虫 - Browser Use 版

支持多区域爬取、数据分析和图表展示。

安装依赖:
    pip install playwright matplotlib
    playwright install chromium (或用系统 Chrome)

使用方法:
    # 爬取所有区域
    python lianjia_zhangjiang_scraper.py --areas all

    # 爬取指定区域
    python lianjia_zhangjiang_scraper.py --areas zhangjiang,jinqiao

    # 仅分析已有数据 (不爬取)
    python lianjia_zhangjiang_scraper.py --analyze output/xxx.json

    # AI Agent 模式
    OPENAI_API_KEY="sk-xxx" python lianjia_zhangjiang_scraper.py --mode agent --areas all
"""

import asyncio
import csv
import json
import os
import re
import random
import subprocess
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path
from collections import Counter


# ============================================================
# 配置
# ============================================================

REGIONS = {
    'zhangjiang': {'name': '张江', 'slug': 'zhangjiang'},
    'jinqiao':    {'name': '金桥', 'slug': 'jinqiao'},
    'tangzhen':   {'name': '唐镇', 'slug': 'tangzhen'},
    'chuansha':   {'name': '川沙', 'slug': 'chuansha'},
    'changning':  {'name': '长宁', 'slug': 'changning'},
}
ALL_REGIONS = list(REGIONS.keys())

OUTPUT_DIR = Path(__file__).parent / "output"
USER_DATA_DIR = Path(__file__).parent / ".browser_data"
DEFAULT_MAX_PAGES = 100

CSV_FIELDS = [
    "region", "title", "rent_type", "community", "area", "rooms", "direction",
    "floor", "price", "unit_price", "tags", "source", "url", "scraped_at", "lat", "lng"
]

logger = logging.getLogger('lianjia')


def _load_env():
    """从 .env 文件加载环境变量 (不覆盖已存在的)"""
    env_file = Path(__file__).parent / '.env'
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


# 模块加载时读取 .env
_load_env()


def _notify(title, message):
    """发送 macOS 系统通知 + 终端响铃"""
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}" sound name "Glass"'
        ], timeout=5, capture_output=True)
    except Exception:
        pass
    # 终端响铃
    sys.stdout.write('\a')
    sys.stdout.flush()


def _add_unit_price(item):
    """为单条房源计算单价 (元/㎡/月)."""
    try:
        price = int(item['price']) if str(item.get('price', '')).isdigit() else None
        area = float(item['area']) if item.get('area') else None
        if price and area and area > 0:
            item['unit_price'] = round(price / area, 1)
        else:
            item['unit_price'] = ''
    except (ValueError, TypeError):
        item['unit_price'] = ''


def _deduplicate(data):
    """按 URL 去重，保留最新记录."""
    seen = {}
    for item in data:
        key = item.get('url', '') or (
            item.get('community', '') + str(item.get('price', ''))
            + str(item.get('area', '')) + item.get('region', '')
        )
        if key:
            seen[key] = item
    return list(seen.values())


def _partial_path(area_slug):
    """断点续爬文件路径."""
    return OUTPUT_DIR / f"lianjia_{area_slug}.partial.json"


def _load_resume(area_slug):
    """
    加载断点续爬数据.

    Returns:
        (existing_data, start_page) — 已有数据和起始页码
    """
    pfile = _partial_path(area_slug)
    if not pfile.exists():
        return [], 1
    try:
        resume = json.loads(pfile.read_text(encoding='utf-8'))
        data = resume.get('data', [])
        start_page = resume.get('last_page', 1)
        logger.info(f"发现断点数据: {len(data)} 条, 从第 {start_page} 页续爬")
        return data, start_page
    except Exception:
        return [], 1


def _save_partial(area_slug, data, last_page):
    """保存断点文件 (每页爬完调用)."""
    pfile = _partial_path(area_slug)
    pfile.write_text(
        json.dumps({'last_page': last_page, 'data': data},
                   ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def get_area_url(slug: str, page: int = None) -> str:
    """根据区域 slug 和页码生成 URL"""
    base = f"https://sh.lianjia.com/zufang/{slug}/"
    if page is None or page <= 0:
        return base
    return f"{base}pg{page}/"


def setup_logging(output_dir: Path):
    """配置日志: 控制台 + 文件"""
    output_dir.mkdir(exist_ok=True)
    log = logging.getLogger('lianjia')
    log.setLevel(logging.INFO)

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(ch)

    # 文件
    fh = logging.FileHandler(output_dir / 'scraper.log', encoding='utf-8', mode='a')
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    log.addHandler(fh)

    return log


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
# 浏览器辅助
# ============================================================

class CaptchaFailedError(Exception):
    """验证码自动识别 9 次全部失败."""
    pass


async def _wait_for_captcha_or_login(page):
    """检测验证码/登录，先尝试超级鹰自动识别 (最多 9 次)，全部失败则通知用户手动处理并等待"""
    logger.warning("\n" + "=" * 50)
    logger.warning("检测到验证码，正在自动识别...")
    logger.warning("=" * 50 + "\n")

    auto_solved = await _try_auto_solve_captcha(page)
    if auto_solved:
        return True

    # 9 次全部失败，通知用户手动处理，持续等待
    msg = "验证码自动识别 9 次全部失败，请在浏览器窗口中手动完成验证"
    logger.warning(f"\n{msg}")
    _notify("链家爬虫 ⚠️", "验证码自动识别 9 次全部失败，请手动处理!")
    while True:
        await asyncio.sleep(2)
        try:
            title = await page.title()
            url = page.url
            is_blocking = (
                'CAPTCHA' in title or '验证' in title
                or '登录' in title or '/login' in url
            )
            if not is_blocking:
                logger.info("检测到验证码已通过，继续爬取...")
                return True
        except Exception:
            continue


async def _try_auto_solve_captcha(page, rounds=3, attempts_per_round=3):
    """
    使用超级鹰自动解决极验 GeeTest v4 点选验证码.

    策略: 3 轮 × 3 次 = 最多 9 次尝试。
    每轮开头点按钮展开面板，内循环只截图+识别+点击。
    每轮失败 3 次后刷新验证码，等 5 秒再继续。
    失败自动上报超级鹰退积分。仅全部失败才返回 False。
    """
    try:
        from chaojiying import solve, report_error
    except ImportError:
        logger.info("未找到 chaojiying.py，跳过自动识别")
        return False

    username = os.environ.get('CHAOJIYING_USER', '')
    password = os.environ.get('CHAOJIYING_PASS', '')
    if not username or not password:
        logger.info("未配置超级鹰账号，跳过自动识别")
        return False

    async def _open_popup():
        """点击按钮打开验证码面板，等待展开完成。返回 box_el 或 None。"""
        await asyncio.sleep(1)
        btn = await page.query_selector('.geetest_btn_click')
        if btn:
            btn_box = await btn.bounding_box()
            if btn_box:
                await page.mouse.click(
                    btn_box['x'] + btn_box['width'] / 2,
                    btn_box['y'] + btn_box['height'] / 2,
                )
                logger.info("已点击验证按钮，等待面板展开...")
                await asyncio.sleep(3)

        # 等待面板完全展开
        for _ in range(15):
            box_el = await page.query_selector('.geetest_box')
            if box_el:
                bb = await box_el.bounding_box()
                if bb and bb['height'] > 200:
                    return box_el
            await asyncio.sleep(0.5)
        return None

    for rnd in range(1, rounds + 1):
        # 每轮开头：打开面板 (只点一次)
        box_el = await _open_popup()
        if not box_el:
            logger.warning(f"第 {rnd} 轮: 面板未展开")
            continue
        box_box = await box_el.bounding_box()

        for att in range(1, attempts_per_round + 1):
            total = (rnd - 1) * attempts_per_round + att
            try:
                # 确认面板还在
                box_el_now = await page.query_selector('.geetest_box')
                if box_el_now:
                    bb = await box_el_now.bounding_box()
                    if not bb or bb['height'] < 200:
                        # 面板消失了，重新打开
                        box_el_now = await _open_popup()
                        if not box_el_now:
                            continue
                        box_box = await box_el_now.bounding_box()

                # 截图
                image_bytes = await page.screenshot(clip={
                    'x': box_box['x'], 'y': box_box['y'],
                    'width': box_box['width'], 'height': box_box['height'],
                })

                # 超级鹰识别
                pic_str, pic_id = solve(image_bytes, codetype=9102,
                                        username=username, password=password)
                if not pic_str:
                    logger.warning(f"[{total}/9] 超级鹰未返回结果")
                    if pic_id:
                        report_error(pic_id, username, password)
                    continue

                # 解析坐标
                points = []
                for pair in pic_str.split('|'):
                    parts = pair.strip().split(',')
                    if len(parts) == 2:
                        points.append((int(parts[0]), int(parts[1])))

                if not points:
                    logger.warning(f"[{total}/9] 坐标解析失败: {pic_str}")
                    if pic_id:
                        report_error(pic_id, username, password)
                    continue

                logger.info(f"[{total}/9] 识别到 {len(points)} 个目标: {pic_str}")

                # 依次点击
                for px, py in points:
                    click_x = box_box['x'] + px
                    click_y = box_box['y'] + py
                    await page.mouse.move(
                        click_x + random.uniform(-1, 1),
                        click_y + random.uniform(-1, 1),
                    )
                    await asyncio.sleep(random.uniform(0.15, 0.3))
                    await page.mouse.click(click_x, click_y)
                    await asyncio.sleep(random.uniform(0.5, 1.0))

                # 点击确定
                await asyncio.sleep(random.uniform(0.3, 0.6))
                for _ in range(10):
                    submit_el = await page.query_selector('.geetest_submit')
                    if submit_el:
                        disabled = await submit_el.evaluate(
                            'el => el.classList.contains("geetest_disable")'
                        )
                        if not disabled:
                            break
                    await asyncio.sleep(0.3)
                await _mouse_click_selector(page, '.geetest_submit')

                await asyncio.sleep(3)

                # 检查是否通过
                try:
                    title = await page.title()
                    url = page.url
                    if not ('CAPTCHA' in title or '验证' in title
                            or '登录' in title or '/login' in url):
                        logger.info(f"[{total}/9] 验证码自动解决成功!")
                        return True
                except Exception:
                    pass

                # 未通过，上报退积分
                logger.warning(f"[{total}/9] 验证码未通过，上报超级鹰退积分 (pic_id={pic_id})")
                if pic_id:
                    report_error(pic_id, username, password)
                    logger.info(f"[{total}/9] 已上报识别错误")

            except Exception as e:
                logger.error(f"[{total}/9] 异常: {e}")

        # 本轮 3 次全部失败，刷新验证码
        if rnd < rounds:
            logger.info(f"第 {rnd} 轮失败，刷新验证码，等待 5 秒...")
            await _mouse_click_selector(page, '.geetest_refresh')
            await asyncio.sleep(5)

    logger.warning("自动识别全部失败 (9 次)")
    return False


async def _mouse_click_selector(page, selector):
    """用 page.mouse.click 点击元素 (绕过遮罩层拦截)."""
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


async def _human_scroll(page):
    """模拟人类滚动浏览页面"""
    try:
        for _ in range(random.randint(1, 3)):
            scroll_y = random.randint(200, 500)
            await page.evaluate(f"window.scrollBy(0, {scroll_y})")
            await asyncio.sleep(random.uniform(0.2, 0.5))
        # 滚回顶部
        await asyncio.sleep(random.uniform(0.1, 0.3))
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(0.1, 0.2))
    except Exception:
        pass


async def _human_mouse_move(page):
    """模拟随机鼠标移动"""
    try:
        for _ in range(random.randint(1, 3)):
            x = random.randint(100, 1300)
            y = random.randint(100, 800)
            await page.mouse.move(x, y, steps=random.randint(5, 15))
            await asyncio.sleep(random.uniform(0.1, 0.3))
    except Exception:
        pass


def _get_page_delay(page_num: int, had_captcha: bool = False) -> float:
    """
    根据页码动态计算延迟。
    越往后延迟越长，模拟人类疲劳；验证码后额外休息；每5页长休息。
    """
    base = random.uniform(2.0, 5.0)
    # 第3页起逐步增加延迟
    if page_num > 3:
        base += (page_num - 3) * random.uniform(0.2, 0.5)
    # 验证码后额外恢复时间
    if had_captcha:
        base += random.uniform(3, 8)
    # 每5页长休息 (降低触发验证码频率)
    if page_num % 5 == 0:
        base += random.uniform(8, 15)
    # 偶尔模拟"发呆"
    if random.random() < 0.08:
        base += random.uniform(2, 4)
    return base


async def _create_browser_context(playwright):
    """创建持久化浏览器上下文 (共享 cookie)"""
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
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );
    """)
    return context


async def _scrape_single_area(page, area_slug: str, max_pages: int,
                              start_page: int = 1,
                              existing_data: list = None) -> tuple:
    """
    爬取单个区域的所有页面，支持断点续爬和增量保存.

    Returns:
        (list, bool) — (房源列表, 是否完整完成)
    """
    region_name = REGIONS[area_slug]['name']
    all_listings = list(existing_data) if existing_data else []
    had_captcha = False

    # 访问目标页面
    base_url = get_area_url(area_slug)

    if start_page == 1:
        logger.info(f"正在访问 {region_name} 租房页面...")
        await page.goto(base_url, wait_until='domcontentloaded', timeout=30000)
        await _human_scroll(page)
        await _human_mouse_move(page)

        # 检测验证码/登录
        try:
            title = await page.title()
            url = page.url
            is_blocking = (
                'CAPTCHA' in title or '验证' in title
                or '登录' in title or '/login' in url
            )
        except Exception:
            is_blocking = True

        if is_blocking:
            success = await _wait_for_captcha_or_login(page)
            if not success:
                logger.error("等待超时")
                return all_listings
            had_captcha = True

            await asyncio.sleep(3)
            if f'/zufang/{area_slug}' not in page.url:
                try:
                    await page.goto(base_url, wait_until='load', timeout=30000)
                except Exception:
                    await asyncio.sleep(2)
                await asyncio.sleep(2)
    else:
        # 续爬: 直接跳到起始页
        url = get_area_url(area_slug, start_page)
        logger.info(f"续爬 {region_name}，从第 {start_page} 页开始...")
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await _human_scroll(page)
        await asyncio.sleep(2)

    # 逐页爬取
    for page_num in range(start_page, max_pages + 1):
        url = get_area_url(area_slug, page_num) if page_num > start_page or start_page > 1 else get_area_url(area_slug)
        if page_num > start_page or start_page > 1:
            if page_num > start_page:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        try:
            # 模拟人类: 先随机滚动和移动鼠标
            await _human_scroll(page)
            if random.random() < 0.4:
                await _human_mouse_move(page)

            # 检查验证码
            try:
                pt = await page.title()
                pu = page.url
                if 'CAPTCHA' in pt or '验证' in pt or '登录' in pt or '/login' in pu:
                    ok = await _wait_for_captcha_or_login(page)
                    if not ok:
                        break
                    had_captcha = True
                    # 验证码后恢复: 重新导航
                    await asyncio.sleep(2)
                    if f'/zufang/{area_slug}' not in page.url:
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                        await _human_scroll(page)
            except Exception:
                pass

            # 等待列表加载
            try:
                await page.wait_for_selector('.content__list--item', timeout=10000)
            except Exception:
                await asyncio.sleep(3)

            listings = await page.evaluate(EXTRACT_JS)
            if not listings:
                logger.info(f"  [{region_name}] 第{page_num}页无数据，结束")
                return all_listings, True

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for item in listings:
                item['scraped_at'] = now
                item['region'] = area_slug
                _add_unit_price(item)

            all_listings.extend(listings)
            logger.info(f"  [{region_name}] 第{page_num}页: {len(listings)} 条 (累计 {len(all_listings)})")

            # 增量保存断点文件
            _save_partial(area_slug, _deduplicate(all_listings), page_num)

            # 检查下一页
            has_next = await page.evaluate("""
                () => {
                    const next = document.querySelector('.content__pg .next');
                    return next && !next.classList.contains('disabled');
                }
            """)
            if not has_next:
                logger.info(f"  [{region_name}] 已到最后一页")
                return all_listings, True

            # 动态延迟
            delay = _get_page_delay(page_num, had_captcha)
            had_captcha = False
            await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"  [{region_name}] 第{page_num}页出错: {e}")
            # 出错也保存已爬数据
            _save_partial(area_slug, _deduplicate(all_listings), page_num)
            return all_listings, False

    # 正常结束 (达到 max_pages)
    return all_listings, True


# ============================================================
# Browser 模式
# ============================================================

async def scrape_with_browser(areas: list, max_pages: int = DEFAULT_MAX_PAGES):
    """使用浏览器爬取多个区域，支持断点续爬"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("请先安装: pip install playwright && playwright install chromium")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    all_listings = []

    async with async_playwright() as p:
        context = await _create_browser_context(p)
        page = context.pages[0] if context.pages else await context.new_page()

        # 先访问首页建立 cookie + 模拟人类浏览
        logger.info("正在访问链家首页...")
        try:
            await page.goto('https://sh.lianjia.com/', wait_until='domcontentloaded', timeout=30000)
            await _human_scroll(page)
            await _human_mouse_move(page)
            await asyncio.sleep(random.uniform(2, 4))
        except Exception:
            pass

        for area_slug in areas:
            region_name = REGIONS[area_slug]['name']
            logger.info(f"\n{'=' * 50}")
            logger.info(f"开始爬取: {region_name} ({area_slug})")
            logger.info(f"{'=' * 50}")

            # 检查断点数据
            existing_data, start_page = _load_resume(area_slug)

            area_listings, completed = await _scrape_single_area(
                page, area_slug, max_pages,
                start_page=start_page,
                existing_data=existing_data,
            )

            all_listings.extend(area_listings)
            logger.info(f"{region_name} 完成: {len(area_listings)} 条")

            if completed:
                # 正常完成，清除断点文件
                pfile = _partial_path(area_slug)
                if pfile.exists():
                    pfile.unlink()
            else:
                # 未完成 (出错/中断)，保留断点文件以便续爬
                logger.warning(f"{region_name} 未完成，断点已保存，下次运行将续爬")

            # 区域间短暂休息
            if area_slug != areas[-1]:
                delay = random.uniform(3, 8)
                logger.info(f"休息 {delay:.0f} 秒后继续下一区域...\n")
                await asyncio.sleep(delay)

        await context.close()

    return all_listings


# ============================================================
# Agent 模式
# ============================================================

async def scrape_with_agent(areas: list, max_pages: int, model: str):
    """使用 AI Agent 爬取多个区域"""
    try:
        from browser_use import Agent, Browser, BrowserConfig
    except ImportError:
        logger.error("请先安装: pip install browser-use")
        sys.exit(1)
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error("请先安装: pip install langchain-openai")
        sys.exit(1)

    all_listings = []
    for area_slug in areas:
        region_name = REGIONS[area_slug]['name']
        base_url = get_area_url(area_slug)
        logger.info(f"启动 AI Agent 爬取: {region_name}")

        task = f"""打开链家{region_name}租房页面: {base_url}
提取所有房源的 title/community/area/rooms/direction/floor/price/tags/source。
翻页直到最后一页或{max_pages}页。返回纯 JSON 数组。"""

        browser = Browser(config=BrowserConfig(headless=False))
        agent = Agent(task=task, llm=ChatOpenAI(model=model, temperature=0.0), browser=browser)
        result = await agent.run()
        await browser.close()

        listings = _parse_agent_result(result)
        for item in listings:
            item['region'] = area_slug
        all_listings.extend(listings)

    return all_listings


def _parse_agent_result(result) -> list:
    """从 Agent 返回结果中提取 JSON 数据"""
    text = ""
    if isinstance(result, list):
        for item in reversed(result):
            content = ""
            if hasattr(item, 'extracted_content') and item.extracted_content:
                content = item.extracted_content
            elif hasattr(item, 'text') and item.text:
                content = item.text
            elif isinstance(item, str):
                content = item
            if content:
                text = content
                break
        if not text:
            text = str(result)
    else:
        text = str(result)

    json_match = re.search(r'\[[\s\S]*\]', text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, list) and data:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                for item in data:
                    item.setdefault('scraped_at', now)
                    item.setdefault('url', '')
                return data
        except json.JSONDecodeError:
            pass
    return []


# ============================================================
# 数据保存
# ============================================================

def save_to_csv(data: list, filepath: Path):
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"CSV 已保存: {filepath}")


def save_to_json(data: list, filepath: Path):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 已保存: {filepath}")


def enrich_with_geo(data: list):
    """为每条房源添加经纬度 (基于小区名批量地理编码)"""
    from community_geo_map import _geocoder

    # 收集唯一小区名 -> region 映射
    community_regions = {}
    for item in data:
        community = item.get('community', '').strip()
        if community and community not in community_regions:
            community_regions[community] = item.get('region', '')

    if not community_regions:
        return

    logger.info(f"开始地理编码: {len(community_regions)} 个唯一小区...")
    geo_coords = _geocoder.batch_geocode(community_regions)

    matched = 0
    for item in data:
        community = item.get('community', '').strip()
        if community and community in geo_coords:
            lat, lng = geo_coords[community]
            item['lat'] = round(lat, 6)
            item['lng'] = round(lng, 6)
            matched += 1
        else:
            item['lat'] = ''
            item['lng'] = ''

    logger.info(f"地理编码完成: {matched}/{len(data)} 条房源匹配到坐标")


def save_results(all_listings: list, selected_areas: list, fmt: str = 'both'):
    """
    统一保存: 去重 + 按区域 + 合并文件.

    Returns:
        Path or None — 合并 JSON 的路径（单区域时为该区域 JSON），未生成 JSON 时返回 None
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 去重
    all_listings = _deduplicate(all_listings)
    logger.info(f"去重后: {len(all_listings)} 条")

    # 在保存前添加经纬度
    enrich_with_geo(all_listings)

    latest_json = None

    for slug in selected_areas:
        region_data = [l for l in all_listings if l.get('region') == slug]
        if not region_data:
            continue
        if fmt in ('csv', 'both'):
            save_to_csv(region_data, OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_{slug}_{timestamp}.json"
            save_to_json(region_data, p)
            if not latest_json:
                latest_json = p

    # 合并文件
    if len(selected_areas) > 1:
        if fmt in ('csv', 'both'):
            save_to_csv(all_listings, OUTPUT_DIR / f"lianjia_all_{timestamp}.csv")
        if fmt in ('json', 'both'):
            p = OUTPUT_DIR / f"lianjia_all_{timestamp}.json"
            save_to_json(all_listings, p)
            latest_json = p

    return latest_json


# ============================================================
# 数据分析 + 图表
# ============================================================

def analyze_listings(data: list):
    """生成统计摘要和图表"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    charts_dir = OUTPUT_DIR / 'charts'
    charts_dir.mkdir(parents=True, exist_ok=True)

    # 预处理数值
    for item in data:
        try:
            item['_price'] = int(item['price']) if str(item.get('price', '')).isdigit() else None
        except (ValueError, TypeError):
            item['_price'] = None
        try:
            item['_area'] = float(item['area']) if item.get('area') else None
        except (ValueError, TypeError):
            item['_area'] = None

    regions = sorted(set(item.get('region', '') for item in data))
    region_names = {r: REGIONS.get(r, {}).get('name', r) for r in regions}
    colors = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f']
    region_colors = {r: colors[i % len(colors)] for i, r in enumerate(regions)}

    # ---- 1. 各区域价格分布 (箱线图) ----
    fig, ax = plt.subplots(figsize=(10, 6))
    price_data = []
    labels = []
    for r in regions:
        prices = [item['_price'] for item in data if item.get('region') == r and item['_price']]
        # 过滤极端值便于展示
        prices = [p for p in prices if p <= 30000]
        if prices:
            price_data.append(prices)
            labels.append(region_names[r])
    if price_data:
        bp = ax.boxplot(price_data, tick_labels=labels, patch_artist=True)
        for patch, r in zip(bp['boxes'], regions):
            patch.set_facecolor(region_colors.get(r, '#4e79a7'))
        ax.set_title('各区域月租金分布 (≤3万)', fontsize=14)
        ax.set_ylabel('月租金 (元/月)')
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '1_price_by_region.png', dpi=150)
    plt.close(fig)

    # ---- 2. 价格直方图 ----
    fig, ax = plt.subplots(figsize=(10, 6))
    all_prices = [item['_price'] for item in data if item['_price'] and item['_price'] <= 30000]
    if all_prices:
        ax.hist(all_prices, bins=30, color='#4e79a7', edgecolor='white', alpha=0.8)
        ax.set_title('整体价格分布', fontsize=14)
        ax.set_xlabel('月租金 (元/月)')
        ax.set_ylabel('房源数量')
        ax.axvline(sum(all_prices) / len(all_prices), color='red', linestyle='--', label=f'均价 {sum(all_prices)/len(all_prices):,.0f}')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '2_price_histogram.png', dpi=150)
    plt.close(fig)

    # ---- 3. 各区域户型分布 (堆叠条形图) ----
    fig, ax = plt.subplots(figsize=(12, 6))
    all_rooms = Counter(item.get('rooms', '') for item in data if item.get('rooms'))
    top_rooms = [r for r, _ in all_rooms.most_common(8)]
    x = range(len(top_rooms))
    width = 0.15
    for i, r in enumerate(regions):
        r_data = [item for item in data if item.get('region') == r]
        counts = [sum(1 for item in r_data if item.get('rooms') == room) for room in top_rooms]
        ax.bar([xi + i * width for xi in x], counts, width, label=region_names[r],
               color=region_colors[r], alpha=0.85)
    ax.set_title('各区域户型分布', fontsize=14)
    ax.set_xlabel('户型')
    ax.set_ylabel('房源数量')
    ax.set_xticks([xi + width * (len(regions) - 1) / 2 for xi in x])
    ax.set_xticklabels(top_rooms)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '3_rooms_by_region.png', dpi=150)
    plt.close(fig)

    # ---- 4. 各区域平均面积 (条形图) ----
    fig, ax = plt.subplots(figsize=(8, 5))
    avg_areas = {}
    for r in regions:
        areas = [item['_area'] for item in data if item.get('region') == r and item['_area']]
        if areas:
            avg_areas[region_names[r]] = sum(areas) / len(areas)
    if avg_areas:
        bars = ax.bar(avg_areas.keys(), avg_areas.values(),
                       color=[region_colors[r] for r in regions if region_names[r] in avg_areas])
        ax.set_title('各区域平均面积', fontsize=14)
        ax.set_ylabel('平均面积 (㎡)')
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f'{bar.get_height():.0f}', ha='center', fontsize=11)
        ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '4_avg_area_by_region.png', dpi=150)
    plt.close(fig)

    # ---- 5. TOP15 热门小区 (水平条形图) ----
    fig, ax = plt.subplots(figsize=(10, 7))
    comm_counter = Counter(item.get('community', '') for item in data if item.get('community'))
    top15 = comm_counter.most_common(15)
    if top15:
        names = [c[:20] + '...' if len(c) > 20 else c for c, _ in reversed(top15)]
        counts = [n for _, n in reversed(top15)]
        ax.barh(names, counts, color='#59a14f', alpha=0.85)
        ax.set_title('热门小区 TOP 15', fontsize=14)
        ax.set_xlabel('房源数量')
        for i, v in enumerate(counts):
            ax.text(v + 0.3, i, str(v), va='center', fontsize=10)
        ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '5_top_communities.png', dpi=150)
    plt.close(fig)

    # ---- 6. 租赁类型占比 (饼图) ----
    fig, ax = plt.subplots(figsize=(7, 7))
    type_counter = Counter(item.get('rent_type', '') for item in data if item.get('rent_type'))
    if type_counter:
        labels_pie = list(type_counter.keys())
        sizes = list(type_counter.values())
        ax.pie(sizes, labels=labels_pie, autopct='%1.1f%%', startangle=90,
               colors=['#4e79a7', '#f28e2b', '#e15759', '#76b7b2'])
        ax.set_title('租赁类型占比', fontsize=14)
    fig.tight_layout()
    fig.savefig(charts_dir / '6_rent_type_pie.png', dpi=150)
    plt.close(fig)

    # ---- 7. 价格 vs 面积散点图 ----
    fig, ax = plt.subplots(figsize=(10, 7))
    for r in regions:
        pts = [(item['_area'], item['_price'])
               for item in data if item.get('region') == r and item['_area'] and item['_price']]
        if pts:
            xs, ys = zip(*pts)
            ax.scatter(xs, ys, alpha=0.5, s=20, label=region_names[r], color=region_colors[r])
    ax.set_title('价格 vs 面积', fontsize=14)
    ax.set_xlabel('面积 (㎡)')
    ax.set_ylabel('月租金 (元/月)')
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '7_price_vs_area.png', dpi=150)
    plt.close(fig)

    # ---- 8. 各区域朝向分布 (分组条形图) ----
    fig, ax = plt.subplots(figsize=(10, 6))
    all_dirs = Counter(item.get('direction', '') for item in data if item.get('direction'))
    top_dirs = [d for d, _ in all_dirs.most_common(8)]
    x = range(len(top_dirs))
    for i, r in enumerate(regions):
        r_data = [item for item in data if item.get('region') == r]
        counts = [sum(1 for item in r_data if item.get('direction') == d) for d in top_dirs]
        ax.bar([xi + i * width for xi in x], counts, width,
               label=region_names[r], color=region_colors[r], alpha=0.85)
    ax.set_title('各区域朝向分布', fontsize=14)
    ax.set_xlabel('朝向')
    ax.set_ylabel('房源数量')
    ax.set_xticks([xi + width * (len(regions) - 1) / 2 for xi in x])
    ax.set_xticklabels(top_dirs)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(charts_dir / '8_direction_by_region.png', dpi=150)
    plt.close(fig)

    # ---- 控制台摘要 ----
    _print_summary(data, regions, region_names)
    logger.info(f"\n图表已保存到: {charts_dir}/")


def _print_summary(data, regions, region_names):
    """打印统计摘要到控制台和日志"""
    total = len(data)
    logger.info(f"\n{'=' * 60}")
    logger.info(f"数据分析报告 | 总计 {total} 条房源")
    logger.info(f"{'=' * 60}")

    all_prices = []
    all_areas = []

    for r in regions:
        rdata = [d for d in data if d.get('region') == r]
        prices = [d['_price'] for d in rdata if d.get('_price')]
        areas = [d['_area'] for d in rdata if d.get('_area')]
        all_prices.extend(prices)
        all_areas.extend(areas)

        logger.info(f"\n--- {region_names[r]} ({len(rdata)} 条) ---")
        if prices:
            logger.info(f"  价格: {min(prices):,} ~ {max(prices):,} 元/月 | "
                        f"均价 {sum(prices)/len(prices):,.0f} | "
                        f"中位数 {sorted(prices)[len(prices)//2]:,}")
        if areas:
            logger.info(f"  面积: {min(areas):.0f} ~ {max(areas):.0f} ㎡ | "
                        f"均面积 {sum(areas)/len(areas):.1f} ㎡")
        # 户型 TOP3
        rooms = Counter(d.get('rooms', '') for d in rdata if d.get('rooms'))
        if rooms:
            top3 = rooms.most_common(3)
            logger.info(f"  户型: {' | '.join(f'{r}({n})' for r, n in top3)}")
        # 热门小区 TOP5
        comms = Counter(d.get('community', '') for d in rdata if d.get('community'))
        if comms:
            top5 = comms.most_common(5)
            logger.info(f"  热门小区: {', '.join(f'{c}({n})' for c, n in top5)}")

    # 总览
    logger.info(f"\n--- 总览 ---")
    if all_prices:
        logger.info(f"  价格: {min(all_prices):,} ~ {max(all_prices):,} 元/月 | "
                    f"均价 {sum(all_prices)/len(all_prices):,.0f}")
    if all_areas:
        logger.info(f"  面积: {min(all_areas):.0f} ~ {max(all_areas):.0f} ㎡ | "
                    f"均面积 {sum(all_areas)/len(all_areas):.1f} ㎡")
    comms = Counter(d.get('community', '') for d in data if d.get('community'))
    logger.info(f"  涉及小区: {len(comms)} 个")


# ============================================================
# 主函数
# ============================================================

async def main():
    parser = argparse.ArgumentParser(
        description='链家租房数据爬虫 (多区域 + 分析)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python %(prog)s --areas all
  python %(prog)s --areas zhangjiang,jinqiao --max-pages 20
  python %(prog)s --analyze output/lianjia_all_xxx.json
  OPENAI_API_KEY="sk-xxx" python %(prog)s --mode agent --areas all
        """
    )

    parser.add_argument('--mode', choices=['browser', 'agent'], default='browser')
    parser.add_argument('--areas', type=str, default='all',
                        help='区域: all 或 zhangjiang,jinqiao,tangzhen,chuansha')
    parser.add_argument('--max-pages', type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument('--model', default='gpt-4o')
    parser.add_argument('--format', choices=['csv', 'json', 'both'], default='both')
    parser.add_argument('--analyze', type=str, default=None,
                        help='仅分析模式: 指定 JSON 文件路径')

    args = parser.parse_args()

    # 日志初始化
    global logger
    logger = setup_logging(OUTPUT_DIR)

    # 仅分析模式
    if args.analyze:
        fpath = Path(args.analyze)
        if not fpath.exists():
            logger.error(f"文件不存在: {fpath}")
            sys.exit(1)
        data = json.loads(fpath.read_text(encoding='utf-8'))
        logger.info(f"加载数据: {len(data)} 条")
        analyze_listings(data)
        return

    # 解析区域
    if args.areas == 'all':
        selected = ALL_REGIONS[:]
    else:
        selected = [a.strip() for a in args.areas.split(',')]
    invalid = [a for a in selected if a not in REGIONS]
    if invalid:
        logger.error(f"未知区域: {invalid}，可选: {ALL_REGIONS}")
        sys.exit(1)

    area_names = [REGIONS[a]['name'] for a in selected]
    logger.info("=" * 60)
    logger.info(f"链家租房数据爬虫 | 区域: {', '.join(area_names)} | 模式: {args.mode}")
    logger.info("=" * 60)

    # 爬取
    if args.mode == 'browser':
        listings = await scrape_with_browser(selected, args.max_pages)
    else:
        listings = await scrape_with_agent(selected, args.max_pages, args.model)

    # 保存
    if listings:
        logger.info(f"\n共爬取 {len(listings)} 条房源数据")
        save_results(listings, selected, args.format)
        # 分析 + 图表
        analyze_listings(listings)
    else:
        logger.warning("未爬取到任何数据")


if __name__ == '__main__':
    asyncio.run(main())

"""
爬取核心模块

浏览器爬取主逻辑，集成断点续爬、验证码处理、自动重试。
"""

import asyncio
import json
import logging
import random
import re
import sys
import time as _time
from datetime import datetime

from scraper.config import (
    ALL_REGIONS,
    DEFAULT_MAX_PAGES,
    OUTPUT_DIR,
    REGIONS,
    SAVE_INTERVAL,
    STALE_DATA_TIMEOUT,
)
from scraper.utils import (
    add_unit_price,
    deduplicate,
    get_area_url,
    logger,
    notify,
    setup_logging,
)
from scraper.retry import error_log
from scraper.browser_helpers import (
    EXTRACT_JS,
    EXTRACT_SUBAREAS_JS,
    create_browser_context,
    get_page_delay,
    human_mouse_move,
    human_scroll,
)
from scraper.captcha import (
    is_captcha_async,
    wait_for_captcha_or_login,
)
from scraper.storage import (
    load_resume,
    save_partial,
    save_periodic,
)


async def _retry_page_operation(page, operation_name: str,
                                 operation_func, max_retries: int = 3):
    """
    单页操作重试包装器.

    Args:
        page: Playwright Page 对象
        operation_name: 操作名称 (用于日志)
        operation_func: 异步操作函数
        max_retries: 最大重试次数

    Returns:
        操作结果，全部失败返回 None
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await operation_func()
        except Exception as e:
            wait = 2 ** (attempt - 1)
            error_log.log(
                f"page_operation:{operation_name}", e,
                attempt=attempt,
                context={"retry_in": f"{wait}s"},
            )
            if attempt < max_retries:
                logger.warning(
                    f"  [{operation_name}] 第 {attempt} 次失败，"
                    f"{wait}s 后重试...")
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"  [{operation_name}] 重试 {max_retries} 次后放弃: {e}")
    return None


async def scrape_single_area(page, area_slug: str, max_pages: int,
                              start_page: int = 1,
                              existing_data: list = None) -> tuple:
    """
    爬取单个区域的所有页面，支持断点续爬和每 N 条自动保存.

    Args:
        page: Playwright Page 对象
        area_slug: 区域标识
        max_pages: 最大页数
        start_page: 起始页码 (断点续爬)
        existing_data: 已有数据 (断点续爬)

    Returns:
        tuple: (list, bool) — (房源列表, 是否完整完成)
    """
    region_name = REGIONS[area_slug]['name']
    all_listings = list(existing_data) if existing_data else []
    had_captcha = False
    last_save_count = len(all_listings)
    last_data_time = _time.time()

    base_url = get_area_url(area_slug)

    if start_page == 1:
        logger.info(f"正在访问 {region_name} 租房页面...")

        async def _goto_first():
            await page.goto(base_url, wait_until='domcontentloaded',
                            timeout=30000)
        await _retry_page_operation(page, f"访问{region_name}首页", _goto_first)
        await human_scroll(page)
        await human_mouse_move(page)

        if await is_captcha_async(page):
            success = await wait_for_captcha_or_login(page)
            if not success:
                logger.error("等待超时")
                return all_listings, False
            had_captcha = True
            await asyncio.sleep(2)
            if f'/zufang/{area_slug}' not in page.url:
                try:
                    await page.goto(base_url, wait_until='load', timeout=30000)
                except Exception:
                    await asyncio.sleep(1)
                await asyncio.sleep(1)
    else:
        url = get_area_url(area_slug, start_page)
        logger.info(f"续爬 {region_name}，从第 {start_page} 页开始...")

        async def _goto_resume():
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await _retry_page_operation(page, f"续爬{region_name}", _goto_resume)
        await human_scroll(page)
        await asyncio.sleep(1)

    # 逐页爬取
    for page_num in range(start_page, max_pages + 1):
        # 停滞检测: 超过阈值未产出新数据，中止并保存
        stale_seconds = _time.time() - last_data_time
        if stale_seconds > STALE_DATA_TIMEOUT and page_num > start_page:
            logger.warning(
                f"  [{region_name}] 已 {stale_seconds:.0f} 秒无新数据，"
                f"疑似卡死 (第{page_num}页)，保存断点并中止")
            save_partial(area_slug, deduplicate(all_listings), page_num)
            return all_listings, False

        url = (get_area_url(area_slug, page_num)
               if page_num > start_page or start_page > 1
               else get_area_url(area_slug))
        if page_num > start_page or start_page > 1:
            if page_num > start_page:
                async def _goto_page(_url=url):
                    await page.goto(_url, wait_until='domcontentloaded',
                                    timeout=30000)
                await _retry_page_operation(
                    page, f"{region_name}第{page_num}页", _goto_page)

        try:
            await human_scroll(page)
            if random.random() < 0.4:
                await human_mouse_move(page)

            # 检查验证码
            if await is_captcha_async(page):
                try:
                    ok = await asyncio.wait_for(
                        wait_for_captcha_or_login(page),
                        timeout=STALE_DATA_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"  [{region_name}] 验证码处理超时"
                        f" ({STALE_DATA_TIMEOUT}s)，中止")
                    save_partial(area_slug, deduplicate(all_listings),
                                 page_num)
                    return all_listings, False
                if not ok:
                    # 验证码失败，保存已爬数据并返回
                    save_partial(area_slug, deduplicate(all_listings),
                                 page_num)
                    return all_listings, False
                had_captcha = True
                await asyncio.sleep(1)
                if f'/zufang/{area_slug}' not in page.url:
                    async def _recover(_url=url):
                        await page.goto(_url, wait_until='domcontentloaded',
                                        timeout=30000)
                    await _retry_page_operation(
                        page, f"恢复{region_name}第{page_num}页", _recover)
                    await human_scroll(page)

            # 等待列表加载
            try:
                await page.wait_for_selector(
                    '.content__list--item', timeout=8000)
            except Exception:
                await asyncio.sleep(2)

            # 提取数据
            listings = await _retry_page_operation(
                page, f"提取{region_name}第{page_num}页数据",
                lambda: page.evaluate(EXTRACT_JS))

            if not listings:
                logger.info(
                    f"  [{region_name}] 第{page_num}页无数据，结束")
                return all_listings, True

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for item in listings:
                item['scraped_at'] = now
                item['region'] = area_slug
                add_unit_price(item)

            all_listings.extend(listings)
            last_data_time = _time.time()
            logger.info(
                f"  [{region_name}] 第{page_num}页: {len(listings)} 条 "
                f"(累计 {len(all_listings)})")

            # 每页保存断点
            save_partial(area_slug, deduplicate(all_listings), page_num)

            # 每 SAVE_INTERVAL 条额外保存一次中间结果
            last_save_count = save_periodic(
                area_slug, all_listings, page_num, last_save_count)

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
            delay = get_page_delay(page_num, had_captcha)
            had_captcha = False
            await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"  [{region_name}] 第{page_num}页出错: {e}")
            error_log.log(
                f"scrape:{region_name}", e,
                context={"page": page_num})
            # 出错也保存已爬数据
            save_partial(area_slug, deduplicate(all_listings), page_num)
            return all_listings, False

    return all_listings, True


async def _detect_subareas(page, area_slug: str) -> list:
    """
    检测区域是否有子区域 (下钻). 访问首页提取子区域链接.

    Args:
        page: Playwright Page 对象
        area_slug: 区域标识

    Returns:
        list: 子区域列表 [{slug, name, url}]，无子区域返回空列表
    """
    region_name = REGIONS[area_slug]['name']
    base_url = get_area_url(area_slug)
    try:
        await page.goto(base_url, wait_until='domcontentloaded',
                         timeout=30000)
        await human_scroll(page)
        await asyncio.sleep(1)

        subareas = await page.evaluate(EXTRACT_SUBAREAS_JS)
        if subareas:
            logger.info(
                f"  [{region_name}] 检测到 {len(subareas)} 个子区域: "
                + ", ".join(s['name'] for s in subareas[:10])
                + (f" 等{len(subareas)}个" if len(subareas) > 10 else ""))
        return subareas
    except Exception as e:
        logger.warning(f"  [{region_name}] 子区域检测失败: {e}")
        return []


async def scrape_with_browser(areas: list,
                               max_pages: int = DEFAULT_MAX_PAGES):
    """
    使用浏览器爬取多个区域，支持断点续爬.

    Args:
        areas: 区域标识列表
        max_pages: 每区域最大页数

    Returns:
        list: 全部房源数据
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("请先安装: pip install playwright && "
                     "playwright install chromium")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    all_listings = []

    async with async_playwright() as p:
        context = await create_browser_context(p)
        page = (context.pages[0]
                if context.pages else await context.new_page())

        # 访问首页建立 cookie
        logger.info("正在访问链家首页...")
        try:
            await page.goto('https://sh.lianjia.com/',
                            wait_until='domcontentloaded', timeout=30000)
            await human_scroll(page)
            await human_mouse_move(page)
            await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass

        # ---- 预处理: 展开大区域为子区域 ----
        expanded_areas = []
        for area_slug in areas:
            subareas = await _detect_subareas(page, area_slug)
            if subareas:
                region_name = REGIONS[area_slug]['name']
                logger.info(
                    f"{region_name} 发现 {len(subareas)} 个子区域，"
                    f"自动展开下钻")
                # 注册子区域
                for sa in subareas:
                    if sa['slug'] not in REGIONS:
                        REGIONS[sa['slug']] = {
                            'name': sa['name'], 'slug': sa['slug']}
                    expanded_areas.append(sa['slug'])
            else:
                expanded_areas.append(area_slug)

        # ---- 逐区域爬取 ----
        for area_slug in expanded_areas:

            area_listings, completed = await scrape_single_area(
                page, area_slug, max_pages,
                start_page=start_page,
                existing_data=existing_data,
            )

            all_listings.extend(area_listings)
            logger.info(f"{region_name} 完成: {len(area_listings)} 条")

            if completed:
                save_partial(area_slug, deduplicate(area_listings),
                             completed=True)
            else:
                logger.warning(
                    f"{region_name} 未完成，断点已保存，下次运行将续爬")

            # 区域间休息
            if area_slug != areas[-1]:
                delay = random.uniform(1, 3)
                logger.info(f"休息 {delay:.0f} 秒后继续下一区域...\n")
                await asyncio.sleep(delay)

        await context.close()

    return all_listings


async def scrape_with_agent(areas: list, max_pages: int, model: str):
    """
    使用 AI Agent 爬取多个区域.

    Args:
        areas: 区域标识列表
        max_pages: 最大页数
        model: LLM 模型名

    Returns:
        list: 全部房源数据
    """
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

        task = (
            f"打开链家{region_name}租房页面: {base_url}\n"
            f"提取所有房源的 title/community/area/rooms/direction/floor/"
            f"price/tags/source。\n"
            f"翻页直到最后一页或{max_pages}页。返回纯 JSON 数组。"
        )

        browser = Browser(config=BrowserConfig(headless=False))
        agent = Agent(task=task,
                      llm=ChatOpenAI(model=model, temperature=0.0),
                      browser=browser)
        result = await agent.run()
        await browser.close()

        listings = _parse_agent_result(result)
        for item in listings:
            item['region'] = area_slug
        all_listings.extend(listings)

    return all_listings


def _parse_agent_result(result) -> list:
    """
    从 Agent 返回结果中提取 JSON 数据.

    Args:
        result: Agent 返回结果

    Returns:
        list: 房源数据列表
    """
    text = ""
    if isinstance(result, list):
        for item in reversed(result):
            content = ""
            if (hasattr(item, 'extracted_content')
                    and item.extracted_content):
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

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
    CITY,
    CITY_URL_PREFIX,
    DEFAULT_MAX_PAGES,
    OUTPUT_DIR,
    PROJECT_DIR,
    REGIONS,
    SAVE_INTERVAL,
    STALE_DATA_TIMEOUT,
    get_output_dir,
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
    EXTRACT_SUBAREAS_FROM_LISTINGS_JS,
    EXTRACT_SUBAREAS_JS,
    KNOWN_SUBAREAS,
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


# ============================================================
# 子区域校验: 过滤明显不是子区域的条目 (其他行政区、租房类型等)
# ============================================================

_NON_SUBAREA_NAMES = frozenset({
    # 租房类型/方式
    '整租', '合租', '公寓', '独栋', '短租', '别墅', '品牌', '新上',
    # 户型
    '一居', '两居', '三居', '四居', '五居', '开间', '一室', '两室',
    '三室', '四室', '五室',
    # 朝向
    '东', '南', '西', '北', '东西', '南北', '东南', '西南',
    '东北', '西北',
    # 服务/标签
    '近地铁', '拎包入住', '精装修', '押一付一', '随时看房', '新上',
    '链家', '自如', '贝壳', '必看好房',
    # 上海顶级行政区 (不是某个区的子区域)
    '黄浦', '徐汇', '长宁', '静安', '普陀', '虹口', '杨浦',
    '闵行', '宝山', '嘉定', '浦东', '金山', '松江', '青浦',
    '奉贤', '崇明', '上海周边',
})

_NON_SUBAREA_SLUGS = frozenset({
    # 上海顶级行政区 slug
    'huangpu', 'xuhui', 'changning', 'jingan', 'putuo',
    'hongkou', 'yangpu', 'minhang', 'baoshan', 'jiading',
    'pudong', 'jinshan', 'songjiang', 'qingpu', 'fengxian',
    'chongming', 'shanghaizhoubian',
})


def _validate_subareas(subareas: list, area_slug: str) -> list:
    """
    校验提取的子区域列表，过滤明显错误的条目.

    Args:
        subareas: 提取到的子区域列表 [{slug, name, url}]
        area_slug: 父区域标识

    Returns:
        list: 校验通过的子区域列表

    Raises:
        RuntimeError: 提取结果全部无效时抛出，应停止爬取
    """
    region_name = REGIONS[area_slug]['name']
    valid = []
    rejected = []

    for sa in subareas:
        name = sa.get('name', '')
        slug = sa.get('slug', '')

        if name in _NON_SUBAREA_NAMES:
            rejected.append(f"{name}(黑名单)")
            continue
        if slug in _NON_SUBAREA_SLUGS:
            rejected.append(f"{name}({slug},行政区)")
            continue
        # 过滤户型/价格/面积等关键词
        if any(kw in name for kw in ('室', '厅', '卫', '元', '万', '㎡')):
            rejected.append(f"{name}(非区域)")
            continue
        # 子区域名应为纯中文 2-6 字
        if not re.match(r'^[\u4e00-\u9fff]{2,6}$', name):
            rejected.append(f"{name}(名称不符)")
            continue
        # slug 应至少 3 个字母 (排除 l0, l1 等筛选编码)
        if len(slug) < 3 or not re.match(r'^[a-z]{3,}\d*$', slug):
            rejected.append(f"{name}({slug},slug过短)")
            continue

        valid.append(sa)

    if rejected:
        logger.warning(
            f"  [{region_name}] 过滤无效子区域 {len(rejected)} 个: "
            f"{', '.join(rejected[:10])}")

    if subareas and not valid:
        raise RuntimeError(
            f"{region_name} 子区域提取失败: "
            f"提取到 {len(subareas)} 条全部无效 "
            f"({', '.join(rejected[:5])})，"
            f"疑似提取到错误筛选行，请检查页面结构")

    return valid


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
                              existing_data: list = None,
                              city: str = None) -> tuple:
    """
    爬取单个区域的所有页面，支持断点续爬和每 N 条自动保存.

    Args:
        page: Playwright Page 对象
        area_slug: 区域标识
        max_pages: 最大页数
        start_page: 起始页码 (断点续爬)
        existing_data: 已有数据 (断点续爬)
        city: 城市标识

    Returns:
        tuple: (list, bool, bool) — (房源列表, 是否完整完成, 是否触顶)
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
                return all_listings, False, False
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
            save_partial(area_slug, deduplicate(all_listings), page_num,
                         city=city)
            return all_listings, False, False

        url = (get_area_url(area_slug, page_num, city=city)
               if page_num > start_page or start_page > 1
               else get_area_url(area_slug, city=city))
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
                                 page_num, city=city)
                    return all_listings, False, False
                if not ok:
                    # 验证码失败，保存已爬数据并返回
                    save_partial(area_slug, deduplicate(all_listings),
                                 page_num, city=city)
                    return all_listings, False, False
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

            # 区域验证: 第一页检查房源 location 是否包含预期区域名
            if page_num == start_page and listings:
                locations = [l.get('location', '') for l in listings[:5]]
                has_match = any(region_name in loc for loc in locations)
                if not has_match and region_name not in (
                        listings[0].get('title', '')):
                    logger.warning(
                        f"  [{region_name}] 页面区域不匹配! "
                        f"预期含'{region_name}'，"
                        f"实际: {locations[:3]}")
                    logger.warning(
                        f"  [{region_name}] 跳过此区域 (slug 可能无效)")
                    return all_listings, True, False

            if not listings:
                logger.info(
                    f"  [{region_name}] 第{page_num}页无数据，结束")
                return all_listings, True, False

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for item in listings:
                item['scraped_at'] = now
                item['region'] = REGIONS.get(area_slug, {}).get('name', area_slug)
                add_unit_price(item)

            all_listings.extend(listings)
            last_data_time = _time.time()
            logger.info(
                f"  [{region_name}] 第{page_num}页: {len(listings)} 条 "
                f"(累计 {len(all_listings)})")

            # 每页保存断点
            save_partial(area_slug, deduplicate(all_listings), page_num,
                         city=city)

            # 每 SAVE_INTERVAL 条额外保存一次中间结果
            last_save_count = save_periodic(
                area_slug, all_listings, page_num, last_save_count, city=city)

            # 检查下一页
            has_next = await page.evaluate("""
                () => {
                    const next = document.querySelector('.content__pg .next');
                    return next && !next.classList.contains('disabled');
                }
            """)
            if not has_next:
                logger.info(f"  [{region_name}] 已到最后一页")
                return all_listings, True, False

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
            save_partial(area_slug, deduplicate(all_listings), page_num,
                         city=city)
            return all_listings, False, False

    # 循环正常结束 = 已到达 max_pages 上限 (非自然终止)
    logger.info(f"  [{region_name}] 已爬满 {max_pages} 页上限")
    return all_listings, True, True


async def _detect_subareas(page, area_slug: str,
                            max_retries: int = 3) -> list:
    """
    从城市专属 regions_config_{city}.json 读取子区域配置.

    根据当前 config.CITY 加载对应城市的配置文件。
    配置文件不存在时提示运行 scrape_regions.py --city {city}。

    Args:
        page: Playwright Page 对象 (保留参数兼容，不使用)
        area_slug: 区域标识
        max_retries: 未使用 (保留参数兼容)

    Returns:
        list: 子区域列表 [{slug, name, url}]，无子区域返回空列表

    Raises:
        RuntimeError: 配置文件不存在或区域未在配置中
    """
    region_name = REGIONS[area_slug]['name']

    # 加载城市专属配置文件
    from scraper import config as _cfg
    city = _cfg.CITY
    config_path = PROJECT_DIR / 'scraper' / f'regions_config_{city}.json'
    if not config_path.exists():
        # fallback 到旧路径
        config_path = PROJECT_DIR / 'scraper' / 'regions_config.json'
    if not config_path.exists():
        raise RuntimeError(
            f"区域配置文件不存在: {config_path}\n"
            f"请先运行: python3.10 scrape_regions.py --city {city}")

    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f"区域配置文件读取失败: {config_path}\n{e}")

    districts = config.get('districts', {})

    # 在一级目录查找
    if area_slug in districts:
        dist = districts[area_slug]
        boards = dist.get('boards', [])
        if boards:
            logger.info(
                f"  [{region_name}] 配置文件: {len(boards)} 个板块 — "
                f"{', '.join(b['name'] for b in boards[:8])}"
                + (f" 等{len(boards)}个" if len(boards) > 8 else ""))
            return boards
        else:
            logger.info(
                f"  [{region_name}] 配置文件中无板块，"
                f"作为单一区域爬取")
            return []

    # 在二级目录查找 (area_slug 是某个区的板块)
    for dist_slug, dist_info in districts.items():
        for board in dist_info.get('boards', []):
            if board['slug'] == area_slug:
                logger.info(
                    f"  [{region_name}] 配置文件中确认为 "
                    f"{dist_info['name']} 的板块，无下级")
                return []

    # 未找到
    raise RuntimeError(
        f"{region_name} ({area_slug}) 不在区域配置文件中\n"
        f"请运行 python3.10 scrape_regions.py 更新配置，"
        f"或检查区域名称是否正确")


async def scrape_with_browser(areas: list,
                               max_pages: int = DEFAULT_MAX_PAGES,
                               city: str = None):
    """
    使用浏览器爬取多个区域，支持断点续爬.

    Args:
        areas: 区域标识列表
        max_pages: 每区域最大页数
        city: 城市标识，None 则使用全局 CITY

    Returns:
        list: 全部房源数据
    """
    city = city or CITY
    prefix = CITY_URL_PREFIX.get(city, city)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("请先安装: pip install playwright && "
                     "playwright install chromium")
        sys.exit(1)

    get_output_dir(city).mkdir(parents=True, exist_ok=True)
    all_listings = []

    async with async_playwright() as p:
        context = await create_browser_context(p)
        page = (context.pages[0]
                if context.pages else await context.new_page())

        # 访问首页建立 cookie
        logger.info("正在访问链家首页...")
        try:
            await page.goto(f'https://{prefix}.lianjia.com/',
                            wait_until='domcontentloaded', timeout=30000)
            await human_scroll(page)
            await human_mouse_move(page)
            await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass

        # ---- 预处理: 展开大区域为子区域 ----
        # 直接从页面提取子区域的完整 URL，存入 REGIONS 供后续使用
        expanded_areas = []
        for area_slug in areas:
            subareas = await _detect_subareas(page, area_slug)
            if subareas:
                region_name = REGIONS[area_slug]['name']
                logger.info(
                    f"{region_name} 发现 {len(subareas)} 个子区域，"
                    f"自动展开下钻 (直接使用页面提取的 URL)")
                # 注册子区域，存储从页面提取的完整 URL
                for sa in subareas:
                    if sa['slug'] not in REGIONS:
                        REGIONS[sa['slug']] = {
                            'name': sa['name'], 'slug': sa['slug'],
                            'parent': area_slug, 'url': sa.get('url', '')}
                    else:
                        # 已存在的区域，更新 parent 和 url
                        REGIONS[sa['slug']]['parent'] = area_slug
                        if sa.get('url'):
                            REGIONS[sa['slug']]['url'] = sa['url']
                    expanded_areas.append(sa['slug'])
            else:
                expanded_areas.append(area_slug)

        # ---- 逐区域爬取 ----
        # 集合: 记录已触顶的区域，避免下钻后再次触顶死循环
        drilled_areas = set()

        for area_slug in expanded_areas:
            region_name = REGIONS[area_slug]['name']
            logger.info(f"\n{'=' * 50}")
            logger.info(f"开始爬取: {region_name} ({area_slug})")
            logger.info(f"{'=' * 50}")

            # 检查断点数据
            existing_data, start_page, already_completed = load_resume(
                area_slug, city=city)

            if already_completed:
                logger.info(
                    f"{region_name} 已完成 ({len(existing_data)} 条)，"
                    f"跳过 (使用 --fresh 重爬)")
                all_listings.extend(existing_data)
                continue

            area_listings, completed, hit_limit = await scrape_single_area(
                page, area_slug, max_pages,
                start_page=start_page,
                existing_data=existing_data,
                city=city,
            )

            all_listings.extend(area_listings)
            logger.info(f"{region_name} 完成: {len(area_listings)} 条")

            # ---- 触顶自动下钻: 爬满 max_pages 且未下钻过 ----
            if hit_limit and area_slug not in drilled_areas:
                logger.info(
                    f"  [{region_name}] 触顶 {max_pages} 页，"
                    f"尝试自动下钻到子区域...")
                drilled_areas.add(area_slug)
                subareas = await _detect_subareas(page, area_slug)
                if subareas:
                    logger.info(
                        f"  [{region_name}] 下钻发现 {len(subareas)} 个子区域，"
                        f"逐个爬取")
                    for sa in subareas:
                        sa_slug = sa['slug']
                        if sa_slug not in REGIONS:
                            REGIONS[sa_slug] = {
                                'name': sa['name'], 'slug': sa_slug,
                                'parent': area_slug,
                                'url': sa.get('url', '')}
                        else:
                            REGIONS[sa_slug]['parent'] = area_slug
                            if sa.get('url'):
                                REGIONS[sa_slug]['url'] = sa['url']
                        # 跳过已完成的子区域
                        sub_data, sub_start, sub_done = load_resume(
                            sa_slug, city=city)
                        if sub_done:
                            logger.info(
                                f"  {sa['name']} 已完成"
                                f" ({len(sub_data)} 条)，跳过")
                            all_listings.extend(sub_data)
                            continue
                        sub_listings, sub_ok, _ = await scrape_single_area(
                            page, sa_slug, max_pages,
                            start_page=sub_start,
                            existing_data=sub_data,
                            city=city)
                        all_listings.extend(sub_listings)
                        logger.info(
                            f"  {sa['name']}: {len(sub_listings)} 条")
                        if sub_ok:
                            save_partial(sa_slug,
                                         deduplicate(sub_listings),
                                         0, completed=True, city=city)
                        # 子区域间短暂休息
                        if sa != subareas[-1]:
                            await asyncio.sleep(random.uniform(0.5, 1.5))
                    # 去重合并
                    all_listings = deduplicate(all_listings)
                    logger.info(
                        f"  [{region_name}] 下钻完成，"
                        f"去重后共 {len(all_listings)} 条")

            if completed and not hit_limit:
                save_partial(area_slug, deduplicate(area_listings),
                             0, completed=True, city=city)
            elif not completed:
                logger.warning(
                    f"{region_name} 未完成，断点已保存，下次运行将续爬")

            # 区域间休息
            if area_slug != expanded_areas[-1]:
                delay = random.uniform(1, 3)
                logger.info(f"休息 {delay:.0f} 秒后继续下一区域...\n")
                await asyncio.sleep(delay)

        await context.close()

    return all_listings


async def scrape_with_agent(areas: list, max_pages: int, model: str,
                            city: str = None):
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

    city = city or CITY
    all_listings = []
    for area_slug in areas:
        region_name = REGIONS[area_slug]['name']
        base_url = get_area_url(area_slug, city=city)
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
            item['region'] = REGIONS.get(area_slug, {}).get('name', area_slug)
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

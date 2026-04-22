"""
验证码/登录处理模块

检测验证码和登录拦截，自动使用账号密码登录链家。
如果登录后出现验证码，使用超级鹰自动识别。
"""

import asyncio
import logging
import os
import random

from scraper.utils import notify
from scraper.browser_helpers import mouse_click_selector

logger = logging.getLogger('lianjia')


# 验证码/登录处理的超时上限 (秒)
CAPTCHA_TIMEOUT = 120


class CaptchaFailedError(Exception):
    """验证码自动识别全部失败."""
    pass


async def is_captcha_async(page) -> bool:
    """
    检查当前页面是否为验证码/登录拦截页面.

    Args:
        page: Playwright Page 对象

    Returns:
        bool: 是否为拦截页面
    """
    try:
        title = await page.title()
        url = page.url
        return ('CAPTCHA' in title or '验证' in title
                or '登录' in title or '/login' in url
                or 'clogin' in url)
    except Exception:
        return True


async def _is_login_page(page) -> bool:
    """
    检测是否为链家登录页面.

    Args:
        page: Playwright Page 对象

    Returns:
        bool: 是否为登录页
    """
    try:
        url = page.url
        if 'clogin.lianjia.com' in url or '/login' in url:
            return True
        title = await page.title()
        if '登录' in title:
            return True
    except Exception:
        pass
    return False


async def _is_captcha_passed(page) -> bool:
    """
    检查验证码/登录是否已通过.

    Args:
        page: Playwright Page 对象

    Returns:
        bool: 已通过
    """
    try:
        title = await page.title()
        url = page.url
        if ('CAPTCHA' not in title and '验证' not in title
                and '登录' not in title and '/login' not in url
                and 'clogin' not in url):
            return True
    except Exception:
        pass
    return False


async def _auto_login(page):
    """
    自动登录链家.

    使用 .env 中配置的手机号和密码进行登录。

    Args:
        page: Playwright Page 对象

    Returns:
        bool: 是否登录成功
    """
    phone = os.environ.get('LIANJIA_PHONE', '')
    password = os.environ.get('LIANJIA_PASSWORD', '')

    if not phone or not password:
        logger.warning("未配置链家账号密码 (LIANJIA_PHONE/LIANJIA_PASSWORD)")
        return False

    logger.info(f"检测到登录页面，使用手机号 {phone[:3]}****{phone[-4:]} 自动登录...")

    try:
        # 等待登录表单完全渲染 (输入框出现)
        try:
            await page.wait_for_selector(
                'input[placeholder="请输入手机号"]', timeout=15000)
            logger.info("登录表单已加载")
        except Exception:
            # 尝试 networkidle 后再等
            await asyncio.sleep(5)
            phone_chk = await page.query_selector('input[type="text"]')
            if not phone_chk:
                logger.warning("登录表单未出现")
                return False

        await asyncio.sleep(1)

        # 填入手机号 — 用精确选择器
        phone_input = await page.query_selector(
            'input[placeholder="请输入手机号"], input[type="text"]')
        if not phone_input:
            logger.warning("未找到手机号输入框")
            return False

        await phone_input.click()
        await asyncio.sleep(0.3)
        await phone_input.fill('')
        await asyncio.sleep(0.2)
        for char in phone:
            await phone_input.type(char, delay=random.uniform(30, 80))
        logger.info("已输入手机号")
        await asyncio.sleep(random.uniform(0.3, 0.6))

        # 填入密码
        pwd_input = await page.query_selector('input[type="password"]')
        if not pwd_input:
            logger.warning("未找到密码输入框")
            return False

        await pwd_input.click()
        await asyncio.sleep(0.3)
        await pwd_input.fill('')
        await asyncio.sleep(0.2)
        for char in password:
            await pwd_input.type(char, delay=random.uniform(30, 80))
        logger.info("已输入密码")
        await asyncio.sleep(random.uniform(0.3, 0.6))

        # 勾选协议复选框
        checkbox = await page.query_selector('input[type="checkbox"]')
        if checkbox:
            checked = await checkbox.evaluate('el => el.checked')
            if not checked:
                await checkbox.click()
                await asyncio.sleep(0.3)
                logger.info("已勾选协议")

        # 点击登录按钮
        login_btn = await page.query_selector(
            'button[type="submit"]')
        if not login_btn:
            login_btn = await page.query_selector('button')

        if login_btn:
            bb = await login_btn.bounding_box()
            if bb:
                await page.mouse.click(
                    bb['x'] + bb['width'] / 2,
                    bb['y'] + bb['height'] / 2)
                logger.info("已点击登录按钮")
        else:
            await page.keyboard.press('Enter')
            logger.info("已按 Enter 登录")

        # 等待登录结果 (登录后可能出现 GeeTest 滑块,
        # 用户手动过完滑块后会跳转)
        logger.info("等待登录结果 (如出现滑块请在浏览器中手动完成)...")
        retry_count = 0
        max_retries = 5
        for i in range(90):
            await asyncio.sleep(1)
            if i > 0 and i % 15 == 0:
                logger.info(f"  登录等待中... ({i}s/{CAPTCHA_TIMEOUT}s)")
            if await _is_captcha_passed(page):
                logger.info("登录成功!")
                await asyncio.sleep(2)
                return True

            # 检测"网络超时"错误并点击重试
            try:
                timeout_link = await page.evaluate("""
                    () => {
                        const links = document.querySelectorAll('a, span, div');
                        for (const el of links) {
                            const text = (el.textContent || '').trim();
                            if (text.includes('重试') || text.includes('点击此处')) {
                                return el.outerHTML.substring(0, 200);
                            }
                        }
                        return '';
                    }
                """)
                if timeout_link and '超时' in (await page.evaluate("""
                    () => document.body.innerText.substring(0, 500)
                """)):
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.info(f"检测到网络超时，点击重试 "
                                    f"({retry_count}/{max_retries})...")
                        await page.evaluate("""
                            () => {
                                const links = document.querySelectorAll('a, span');
                                for (const el of links) {
                                    if ((el.textContent || '').includes('重试')
                                        || (el.textContent || '').includes('点击此处')) {
                                        el.click();
                                        break;
                                    }
                                }
                            }
                        """)
                        await asyncio.sleep(3)
                        continue
                    else:
                        logger.warning("网络超时重试已达上限")
                        break

                # 检测"指定的服务未被授权"等 GeeTest 错误弹窗
                error_modal = await page.query_selector(
                    '[class*="error"], [class*="modal"], [class*="dialog"]')
                if error_modal:
                    error_text = await error_modal.evaluate(
                        'el => el.textContent.substring(0, 200)')
                    if '未被授权' in error_text or '认证' in error_text:
                        logger.warning(f"GeeTest 服务错误: {error_text[:80]}")
                        # 关闭弹窗重试
                        close_btn = await page.query_selector(
                            '[class*="close"], [class*="dismiss"], button')
                        if close_btn:
                            try:
                                await close_btn.click()
                                await asyncio.sleep(2)
                            except Exception:
                                pass
            except Exception:
                pass

        # 登录后可能出现 GeeTest 滑块验证码
        # (链家登录接口返回 200 后会通过 JS 注入 GeeTest)
        # 检查是否出现了 GeeTest 面板
        logger.info("检查登录后验证码...")
        await asyncio.sleep(3)
        geetest_box = await page.query_selector(
            '.geetest_panel, .geetest_box, '
            '.geetest_slider_button, .geetest_ghost_slider')
        if geetest_box:
            logger.info("检测到登录后 GeeTest 验证码，尝试自动解决...")
            solved = await _solve_geetest_slider(page)
            if solved:
                for j in range(15):
                    await asyncio.sleep(1)
                    if await _is_captcha_passed(page):
                        logger.info("登录+验证通过!")
                        await asyncio.sleep(2)
                        return True
                logger.warning("验证通过但页面未跳转")
                return False

        logger.warning("登录超时")
        return False

    except Exception as e:
        logger.error(f"自动登录异常: {e}")
        return False


async def _solve_geetest_slider(page, max_attempts=5):
    """
    自动解决 GeeTest 滑块验证码 (链家登录后出现).

    GeeTest 滑块: 背景图中有缺口，需要拖动滑块拼图到缺口位置。
    使用超级鹰 codetype=9101 识别缺口 x 坐标。

    Args:
        page: Playwright Page 对象
        max_attempts: 最大尝试次数

    Returns:
        bool: 是否通过
    """
    try:
        from chaojiying import solve, report_error
    except ImportError:
        return False

    username = os.environ.get('CHAOJIYING_USER', '')
    password = os.environ.get('CHAOJIYING_PASS', '')
    if not username or not password:
        return False

    for attempt in range(1, max_attempts + 1):
        try:
            # 先检查是否已经通过 (用户可能手动过了)
            if await _is_captcha_passed(page):
                logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] 已通过!")
                return True

            # ---- 先点击"开始验证"按钮触发验证码 ----
            btn_click = await page.query_selector(
                '[class*="geetest_btn_click"]')
            if btn_click:
                bb = await btn_click.bounding_box()
                if bb and bb['width'] > 10 and bb['height'] > 10:
                    logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                f"点击开始验证按钮...")
                    await page.mouse.click(
                        bb['x'] + bb['width'] / 2,
                        bb['y'] + bb['height'] / 2)
                    # 等待验证码面板展开
                    await asyncio.sleep(3)

            # 等待 GeeTest 渲染完成 (GeeTest 需要加载远程资源)
            await asyncio.sleep(2)

            # 再次检查
            if await _is_captcha_passed(page):
                return True

            # ---- 检测验证码类型 ----
            # 滑块型: 有 slider handle/track 元素
            has_slider = await page.query_selector(
                '.geetest_slider_button, .geetest_ghost_slider, '
                '.geetest_btn_drag, .geetest_sliderbtn, '
                '.geetest_slider_track')
            # 点选型: 有 item_wrap / 图标元素
            has_click_select = await page.query_selector(
                '.geetest_item_wrap, .geetest_img, '
                '.geetest_table_img, '
                '[class*="geetest_"] [class*="item"]')

            if not has_slider and has_click_select:
                logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                            f"检测到点选验证码 (非滑块)，交给点选处理器")
                return False

            if not has_slider and not has_click_select:
                logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                            f"未识别到滑块或点选元素，等待加载...")
                await asyncio.sleep(3)
                # 再检查一次
                has_slider = await page.query_selector(
                    '.geetest_slider_button, .geetest_ghost_slider, '
                    '.geetest_btn_drag')
                if not has_slider:
                    logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                f"仍未检测到滑块元素，放弃滑块模式")
                    return False

            # 找滑块背景图区域 (GeeTest 用 canvas 渲染)
            # 重要: .geetest_panel 是全屏覆盖层, 不能用它截图
            # 需要找到内部的 widget/box/canvas 元素
            clip = None

            # 优先找 canvas 元素 (实际的验证码图片)
            for sel in ['.geetest_widget canvas',
                        '.geetest_canvas_bg canvas',
                        '.geetest_content canvas',
                        '.geetest_box canvas',
                        '[class*="geetest_"] canvas']:
                el = await page.query_selector(sel)
                if el:
                    bb = await el.bounding_box()
                    if bb and 100 < bb['width'] < 800 and bb['height'] > 30:
                        clip = {'x': bb['x'], 'y': bb['y'],
                                'width': bb['width'], 'height': bb['height']}
                        logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                    f"截图区域(canvas): {sel} "
                                    f"{bb['width']:.0f}x{bb['height']:.0f}")
                        break

            # 其次找 widget/content/box 容器
            if not clip:
                for sel in ['.geetest_widget', '.geetest_content',
                            '.geetest_captcha',
                            '.geetest_panel_box .geetest_box',
                            '.geetest_panel_box',
                            '.geetest_box_wrap',
                            '.geetest_box:not(.geetest_panel .geetest_box)']:
                    el = await page.query_selector(sel)
                    if el:
                        bb = await el.bounding_box()
                        if (bb and 100 < bb['width'] < 800
                                and bb['height'] > 80):
                            clip = {'x': bb['x'], 'y': bb['y'],
                                    'width': bb['width'], 'height': bb['height']}
                            logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                        f"截图区域: {sel} "
                                        f"{bb['width']:.0f}x{bb['height']:.0f}")
                            break

            # 最后兜底: 使用 .geetest_panel 但限制尺寸
            if not clip:
                # 可能"网络超时"提示挡住了, 尝试关闭
                close_el = await page.query_selector(
                    '[class*="close"], [class*="dismiss"]')
                if close_el:
                    try:
                        await close_el.click()
                        await asyncio.sleep(2)
                    except Exception:
                        pass

                for sel in ['.geetest_panel', '.geetest_box',
                            '.geetest_window']:
                    el = await page.query_selector(sel)
                    if el:
                        bb = await el.bounding_box()
                        if bb and bb['width'] > 100:
                            # 如果区域和视口一样大, 说明是覆盖层, 截图效果差
                            vp = page.viewport_size
                            is_fullscreen = (vp and
                                             abs(bb['width'] - vp['width']) < 50
                                             and abs(bb['height'] - vp['height']) < 50)
                            if is_fullscreen:
                                logger.warning(
                                    f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                    f"元素 {sel} 覆盖全屏 ({bb['width']:.0f}x"
                                    f"{bb['height']:.0f}), 跳过")
                                continue
                            clip = {'x': bb['x'], 'y': bb['y'],
                                    'width': bb['width'], 'height': bb['height']}
                            break

                if not clip:
                    logger.warning(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                                   "未找到验证码面板内部元素")
                    # 调试: 保存截图和 DOM 结构
                    try:
                        from pathlib import Path
                        debug_dir = Path('output/captcha_debug')
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        await page.screenshot(
                            path=str(debug_dir / f'geetest_no_clip_{attempt}.png'))
                        dom_info = await page.evaluate("""
                            () => {
                                const els = document.querySelectorAll(
                                    '[class*="geetest"], [class*="captcha"]');
                                return Array.from(els).slice(0, 20).map(
                                    el => el.tagName + '.' + el.className
                                          + ' ' + (el.getBoundingClientRect().width|0)
                                          + 'x' + (el.getBoundingClientRect().height|0)
                                ).join('\\n');
                            }
                        """)
                        logger.info(f"GeeTest DOM 元素:\\n{dom_info}")
                    except Exception as e:
                        logger.warning(f"调试信息保存失败: {e}")
                    continue

            # 截图
            image_bytes = await page.screenshot(clip=clip)

            # 保存调试截图 (便于排查)
            try:
                from pathlib import Path
                debug_dir = Path('output/captcha_debug')
                debug_dir.mkdir(parents=True, exist_ok=True)
                ts = __import__('time').strftime('%H%M%S')
                (debug_dir / f'geetest_slider_{attempt}_{ts}.png').write_bytes(
                    image_bytes)
            except Exception:
                pass

            # 超级鹰识别 (9101 = 滑块坐标型)
            pic_str, pic_id = solve(
                image_bytes, codetype=9101,
                username=username, password=password)

            if not pic_str:
                logger.warning(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                               "超级鹰未返回结果")
                continue

            # 解析坐标
            try:
                coords = pic_str.split(',')
                target_x = int(coords[0])
            except (ValueError, IndexError):
                logger.warning(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                               f"解析失败: {pic_str}")
                continue

            logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                        f"缺口位置 x={target_x}")

            # 找滑块拖动按钮 (GeeTest v4 常见按钮类名)
            slider_btn = None
            for sel in ['.geetest_btn', '.geetest_sliderbtn',
                        '.geetest_btn_drag',
                        '.geetest_slider_button', '.geetest_ghost_slider',
                        '.geetest_slider_track .geetest_btn',
                        '.geetest_slider .geetest_btn',
                        '[class*="geetest"] [class*="btn"]',
                        '[class*="slider"] button',
                        '[class*="slider"] div[class*="btn"]',
                        '[class*="slider"] div[class*="drag"]']:
                el = await page.query_selector(sel)
                if el:
                    bb = await el.bounding_box()
                    # 排除过宽的按钮 (如"开始验证"按钮 260x50)
                    if (bb and 10 < bb['width'] < 100
                            and bb['height'] > 10):
                        slider_btn = el
                        logger.info(
                            f"[GeeTest滑块 {attempt}/{max_attempts}] "
                            f"滑块按钮: {sel} "
                            f"{bb['width']:.0f}x{bb['height']:.0f}")
                        break

            if not slider_btn:
                logger.warning(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                               "未找到滑块按钮")
                continue

            btn_bb = await slider_btn.bounding_box()
            start_x = btn_bb['x'] + btn_bb['width'] / 2
            start_y = btn_bb['y'] + btn_bb['height'] / 2

            # 目标 x = 截图区域起点 + 识别坐标 (如果是相对坐标)
            # GeeTest 滑块需要从起始位置拖到缺口位置
            # 超级鹰返回的是相对于截图的 x, 需要减去滑块初始位置偏移
            end_x = clip['x'] + target_x
            end_y = start_y

            logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] "
                        f"拖动: ({start_x:.0f},{start_y:.0f}) -> "
                        f"({end_x:.0f},{end_y:.0f})")

            # 模拟人类拖动
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(0.2)
            await page.mouse.down()
            await asyncio.sleep(0.1)

            steps = random.randint(20, 35)
            for i in range(steps):
                progress = (i + 1) / steps
                ease = 1 - (1 - progress) ** 2.5
                cur_x = start_x + (end_x - start_x) * ease
                cur_y = start_y + random.uniform(-1.5, 1.5)
                await page.mouse.move(cur_x, cur_y)
                await asyncio.sleep(random.uniform(0.008, 0.025))

            # 到达终点时稍微停顿再松手
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await page.mouse.up()

            logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] 已松手")

            # 等待验证结果
            await asyncio.sleep(4)

            if await _is_captcha_passed(page):
                logger.info(f"[GeeTest滑块 {attempt}/{max_attempts}] 通过!")
                return True

            # 失败
            if pic_id:
                report_error(pic_id, username, password)
            logger.warning(f"[GeeTest滑块 {attempt}/{max_attempts}] 未通过，重试...")
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[GeeTest滑块 {attempt}/{max_attempts}] 异常: {e}")
            # 如果页面已跳转 (元素脱离 DOM), 不再重试
            if 'not attached' in str(e) or 'navigated' in str(e):
                logger.info("页面已跳转，检查是否已通过验证...")
                if await _is_captcha_passed(page):
                    return True
                break

    return False


async def _solve_slider_captcha(page, max_attempts=5):
    """
    自动解决链家滑块验证码.

    策略: 截图发送给超级鹰 (codetype=9101 滑块坐标型) 获取 x 坐标，
    然后拖动滑块到指定位置。

    Args:
        page: Playwright Page 对象
        max_attempts: 最大尝试次数

    Returns:
        bool: 是否通过
    """
    try:
        from chaojiying import solve, report_error
    except ImportError:
        logger.info("未找到 chaojiying.py，跳过滑块识别")
        return False

    username = os.environ.get('CHAOJIYING_USER', '')
    password = os.environ.get('CHAOJIYING_PASS', '')
    if not username or not password:
        return False

    for attempt in range(1, max_attempts + 1):
        try:
            await asyncio.sleep(2)

            # 找滑块背景图区域
            clip = None
            slider_handle = None

            # 尝试多种选择器找滑块区域
            for sel in ['.tc-bg', '.captcha-bg', '.slider-bg',
                        '[class*="captcha"] img', '[class*="slider"] img',
                        '.tc-captcha', '[class*="verify-img"]']:
                el = await page.query_selector(sel)
                if el:
                    bb = await el.bounding_box()
                    if bb and bb['width'] > 100:
                        clip = {'x': bb['x'], 'y': bb['y'],
                                'width': bb['width'], 'height': bb['height']}
                        break

            if not clip:
                # 回退: 找整个验证码容器
                for sel in ['[class*="captcha"]', '[class*="verify"]',
                            '[class*="slider"]']:
                    el = await page.query_selector(sel)
                    if el:
                        bb = await el.bounding_box()
                        if bb and bb['width'] > 150 and bb['height'] > 50:
                            clip = {'x': bb['x'], 'y': bb['y'],
                                    'width': bb['width'], 'height': bb['height']}
                            break

            if not clip:
                logger.warning(f"[滑块 {attempt}/{max_attempts}] 未找到验证码区域")
                continue

            # 截图
            image_bytes = await page.screenshot(clip=clip)

            # 超级鹰识别 (9101 = 滑块坐标型, 返回 "x" 或 "x,y")
            pic_str, pic_id = solve(
                image_bytes, codetype=9101,
                username=username, password=password)

            if not pic_str:
                logger.warning(f"[滑块 {attempt}/{max_attempts}] 超级鹰未返回结果")
                continue

            # 解析 x 坐标
            try:
                target_x = int(pic_str.split(',')[0])
            except (ValueError, IndexError):
                logger.warning(f"[滑块 {attempt}/{max_attempts}] "
                               f"坐标解析失败: {pic_str}")
                continue

            logger.info(f"[滑块 {attempt}/{max_attempts}] "
                        f"目标 x={target_x}, 区域={clip['width']:.0f}x{clip['height']:.0f}")

            # 找滑块拖动手柄
            for sel in ['.tc-slider-handle', '.slider-btn',
                        '.captcha-slider-btn', '[class*="slider-btn"]',
                        '[class*="handle"]', '[class*="drag"]']:
                slider_handle = await page.query_selector(sel)
                if slider_handle:
                    break

            if not slider_handle:
                logger.warning(f"[滑块 {attempt}/{max_attempts}] 未找到拖动手柄")
                continue

            handle_bb = await slider_handle.bounding_box()
            if not handle_bb:
                continue

            # 拖动滑块到目标位置
            start_x = handle_bb['x'] + handle_bb['width'] / 2
            start_y = handle_bb['y'] + handle_bb['height'] / 2
            end_x = clip['x'] + target_x
            end_y = start_y  # y 不变

            # 模拟人类拖动: 分步移动 + 随机偏移
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(0.2)
            await page.mouse.down()
            await asyncio.sleep(0.1)

            steps = random.randint(15, 25)
            for i in range(steps):
                progress = (i + 1) / steps
                # 缓动函数: 先快后慢
                ease = 1 - (1 - progress) ** 2
                current_x = start_x + (end_x - start_x) * ease
                current_y = start_y + random.uniform(-2, 2)
                await page.mouse.move(current_x, current_y)
                await asyncio.sleep(random.uniform(0.01, 0.03))

            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.mouse.up()

            logger.info(f"[滑块 {attempt}/{max_attempts}] 已拖动到 x={end_x:.0f}")

            # 等待验证结果
            await asyncio.sleep(3)

            if await _is_captcha_passed(page):
                logger.info(f"[滑块 {attempt}/{max_attempts}] 滑块验证通过!")
                return True

            # 失败退积分
            if pic_id:
                report_error(pic_id, username, password)

            logger.warning(f"[滑块 {attempt}/{max_attempts}] 未通过，重试...")
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[滑块 {attempt}/{max_attempts}] 异常: {e}")

    return False


async def _try_auto_solve_captcha(page, rounds=5, attempts_per_round=5):
    """
    使用超级鹰自动解决极验 GeeTest v4 点选验证码.

    Args:
        page: Playwright Page 对象
        rounds: 总轮数
        attempts_per_round: 每轮尝试次数

    Returns:
        bool: 是否成功解决验证码
    """
    try:
        from chaojiying import solve, report_error
    except ImportError:
        logger.info("未找到 chaojiying.py，跳过自动识别")
        return False

    username = os.environ.get('CHAOJIYING_USER', '')
    password = os.environ.get('CHAOJIYING_PASS', '')
    if not username or not password:
        logger.info("未配置超级鹰账号")
        return False

    # 等待验证码面板出现
    panel_found = False
    for _ in range(30):
        try:
            for sel in ['.geetest_box', '.geetest_panel',
                        '.geetest_panel_box',
                        '.captcha-hidden:not(.captcha-hidden)',
                        '[class*="geetest_panel"]',
                        '[class*="geetest_box"]',
                        '[class*="geetest_widget"]',
                        '[class*="captcha"] canvas',
                        '[class*="verify"] canvas']:
                el = await page.query_selector(sel)
                if el:
                    bb = await el.bounding_box()
                    if bb and bb['height'] > 80 and bb['width'] > 100:
                        panel_found = True
                        break
        except Exception:
            pass
        if panel_found:
            break
        await asyncio.sleep(0.5)

    if not panel_found:
        logger.info("未发现 GeeTest 验证码面板")
        return False

    logger.info("发现 GeeTest 验证码面板，开始自动识别...")

    # 检测期望的目标数量 (从提示区域计数参考图标)
    expected_targets = 3
    try:
        expected_targets = await page.evaluate("""
            () => {
                // 尝试从提示区域统计参考图标数量
                const tipSelectors = [
                    '.geetest_tip img', '.geetest_tips img',
                    '.geetest_tip_content img',
                    '.geetest_tip .geetest_icon',
                    '[class*="geetest_tip"] img',
                ];
                for (const sel of tipSelectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) return els.length;
                }
                // 备选: 数提示区域的小图
                const tipWrap = document.querySelector(
                    '[class*="geetest_tip"]');
                if (tipWrap) {
                    const imgs = tipWrap.querySelectorAll('img, canvas');
                    if (imgs.length > 0) return imgs.length;
                }
                return 3;
            }
        """)
    except Exception:
        pass
    logger.info(f"期望点击 {expected_targets} 个目标")

    total = rounds * attempts_per_round
    for rnd in range(1, rounds + 1):
        for att in range(1, attempts_per_round + 1):
            num = (rnd - 1) * attempts_per_round + att
            try:
                # 等待图片加载
                await asyncio.sleep(2)

                # 获取截图区域 — 优先找精确图片区域
                clip = None
                for sel in ['.geetest_item_wrap', '.geetest_img',
                            '.geetest_table_img', '.geetest_widget',
                            '.geetest_content']:
                    el = await page.query_selector(sel)
                    if el:
                        bb = await el.bounding_box()
                        if bb and bb['width'] > 100 and bb['height'] > 100:
                            clip = {'x': bb['x'], 'y': bb['y'],
                                    'width': bb['width'],
                                    'height': bb['height']}
                            logger.info(f"[{num}/{total}] 截图区域: {sel} "
                                        f"{bb['width']:.0f}x{bb['height']:.0f}")
                            break

                # 回退: 用完整 geetest_box (不裁剪，完整截图效果更好)
                if not clip:
                    for sel in ['.geetest_box', '.geetest_panel_box']:
                        el = await page.query_selector(sel)
                        if el:
                            bb = await el.bounding_box()
                            if bb and bb['width'] > 100 and bb['height'] > 100:
                                clip = {'x': bb['x'], 'y': bb['y'],
                                        'width': bb['width'],
                                        'height': bb['height']}
                                logger.info(
                                    f"[{num}/{total}] 截图区域(完整): "
                                    f"{sel} "
                                    f"{bb['width']:.0f}x"
                                    f"{bb['height']:.0f}")
                                break

                if not clip:
                    # 面板可能已消失 — 检查是否已通过验证
                    if await _is_captcha_passed(page):
                        logger.info(f"[{num}/{total}] 面板消失且验证已通过!")
                        return True
                    if num > 1:
                        logger.warning(f"[{num}/{total}] 面板已消失，停止尝试")
                        break
                    logger.warning(f"[{num}/{total}] 未找到截图区域")
                    continue

                image_bytes = await page.screenshot(clip=clip)

                # 保存调试截图
                try:
                    from pathlib import Path
                    debug_dir = Path('output/captcha_debug')
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    ts = __import__('time').strftime('%H%M%S')
                    (debug_dir / f'click_{num}_{ts}.png').write_bytes(
                        image_bytes)
                except Exception:
                    pass

                pic_str, pic_id = solve(
                    image_bytes, codetype=9103,
                    username=username, password=password)

                if not pic_str:
                    logger.warning(f"[{num}/{total}] 超级鹰未返回结果")
                    continue

                points = []
                for pair in pic_str.split('|'):
                    parts = pair.strip().split(',')
                    if len(parts) == 2:
                        try:
                            points.append((int(parts[0]), int(parts[1])))
                        except ValueError:
                            pass

                if not points:
                    logger.warning(f"[{num}/{total}] 坐标解析失败: {pic_str}")
                    continue

                logger.info(f"[{num}/{total}] 识别到 {len(points)} 个目标: "
                            f"{pic_str}")

                # 目标数量不够 → 跳过本次，不浪费尝试
                if len(points) < expected_targets:
                    logger.info(f"[{num}/{total}] 期望 {expected_targets} "
                                f"个但只找到 {len(points)} 个，跳过")
                    # 点击刷新获取新验证码
                    await mouse_click_selector(page, '.geetest_refresh')
                    await asyncio.sleep(3)
                    continue

                for px, py in points:
                    click_x = clip['x'] + px
                    click_y = clip['y'] + py
                    await page.mouse.move(
                        click_x + random.uniform(-2, 2),
                        click_y + random.uniform(-2, 2))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await page.mouse.click(click_x, click_y)
                    await asyncio.sleep(random.uniform(0.5, 1.0))

                await asyncio.sleep(random.uniform(0.5, 1.0))
                await mouse_click_selector(page, '.geetest_submit')
                await asyncio.sleep(3)

                if await _is_captcha_passed(page):
                    logger.info(f"[{num}/{total}] 验证码解决成功!")
                    return True

                if pic_id:
                    report_error(pic_id, username, password)

                # 点击刷新获取新验证码 (避免面板消失后无法重试)
                await asyncio.sleep(1)
                await mouse_click_selector(page, '.geetest_refresh')
                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"[{num}/{total}] 异常: {e}")

        if rnd < rounds:
            await mouse_click_selector(page, '.geetest_refresh')
            await asyncio.sleep(5)

    return False


async def wait_for_captcha_or_login(page):
    """
    处理验证码/登录拦截: 自动登录 → 自动识别验证码 → 超时通知用户.

    链家的 GeeTest 验证码在自动化环境下可能无法渲染,
    因此登录步骤需要用户在浏览器中手动完成滑块验证。
    cookie 会被持久化, 后续运行无需再次登录。

    Args:
        page: Playwright Page 对象

    Returns:
        bool: True 表示已通过
    """
    import time
    start_time = time.time()

    logger.warning("\n" + "=" * 50)
    logger.warning("检测到拦截页面，开始自动处理...")
    logger.warning("=" * 50 + "\n")

    while True:
        elapsed = time.time() - start_time
        if elapsed > CAPTCHA_TIMEOUT:
            logger.error(f"拦截处理超时 ({CAPTCHA_TIMEOUT}s)，中止当前操作")
            notify("链家爬虫", "拦截处理超时，请手动检查!")
            return False

        # 1. 如果是登录页面 → 尝试自动登录
        if await _is_login_page(page):
            login_ok = await _auto_login(page)
            if login_ok:
                return True

            # 自动登录失败 (GeeTest 滑块验证码在自动化下可能无法渲染)
            # 通知用户手动处理
            logger.warning("")
            logger.warning("自动登录失败 (GeeTest 滑块在自动化下无法渲染)")
            logger.warning("请在弹出的浏览器窗口中手动完成登录!")
            logger.warning(f"账号: {os.environ.get('LIANJIA_PHONE', '')}")
            logger.warning(f"密码: {os.environ.get('LIANJIA_PASSWORD', '')}")
            logger.warning("")
            notify("链家爬虫", "请在浏览器中手动登录!")

            # 等待用户手动登录 + 过滑块
            manual_start = time.time()
            while time.time() - start_time < CAPTCHA_TIMEOUT:
                await asyncio.sleep(2)
                manual_waited = time.time() - manual_start
                if manual_waited > 0 and int(manual_waited) % 20 == 0:
                    remaining = CAPTCHA_TIMEOUT - (time.time() - start_time)
                    logger.info(
                        f"  等待手动登录中... ({manual_waited:.0f}s, "
                        f"剩余 {remaining:.0f}s)")
                if await _is_captcha_passed(page):
                    logger.info("检测到登录完成，继续爬取...")
                    return True
            return False

        # 2. 检查是否有滑块验证码
        slider = await page.query_selector(
            '.slider-btn, .tc-slider-handle, .captcha-slider-btn, '
            '[class*="slider"] img')
        if slider:
            solved = await _solve_slider_captcha(page)
            if solved:
                return True

        # 2.5 处理 GeeTest 验证码 (滑块或点选)
        geetest_panel = await page.query_selector(
            '.geetest_panel, .geetest_box, .geetest_panel_box, '
            '.geetest_captcha, .geetest_holder, '
            '[class*="geetest_btn_click"]')
        if geetest_panel:
            logger.info("检测到 GeeTest 面板，尝试自动解决...")
            # _solve_geetest_slider 会先点击按钮，再判断类型
            # 如果是点选型会立即返回 False，下面接着处理
            solved = await _solve_geetest_slider(page)
            if solved:
                return True
            # 滑块失败或检测到点选型，直接尝试点选自动识别
            logger.info("尝试 GeeTest 点选验证码自动识别...")
            solved = await _try_auto_solve_captcha(page)
            if solved:
                return True

        # 2.6 尝试点击"安全验证"按钮触发 GeeTest
        verify_btn = await page.query_selector(
            '[class*="verify"] button, '
            'button:has-text("验证"), '
            'div:has-text("安全验证")')
        if verify_btn:
            bb = await verify_btn.bounding_box()
            if bb and bb['width'] > 50:
                logger.info("发现验证按钮，点击触发 GeeTest...")
                try:
                    await page.mouse.click(
                        bb['x'] + bb['width'] / 2,
                        bb['y'] + bb['height'] / 2)
                    await asyncio.sleep(3)
                    solved = await _solve_geetest_slider(page)
                    if solved:
                        return True
                    solved = await _try_auto_solve_captcha(page)
                    if solved:
                        return True
                except Exception as e:
                    logger.warning(f"点击验证按钮失败: {e}")

        # 3. 再试一次点选 (兜底)
        solved = await _try_auto_solve_captcha(page)
        if solved:
            return True

        # 4. 自动识别失败，等待用户手动处理
        logger.warning("自动识别失败，请在浏览器中手动完成验证...")
        notify("链家爬虫", "请手动完成验证!")
        wait_start = time.time()
        while time.time() - start_time < CAPTCHA_TIMEOUT:
            await asyncio.sleep(2)
            waited = time.time() - wait_start
            if waited > 0 and int(waited) % 20 == 0:
                logger.info(
                    f"  等待手动验证中... "
                    f"({waited:.0f}s, 剩余 {CAPTCHA_TIMEOUT - waited:.0f}s)")
            if await _is_captcha_passed(page):
                logger.info("检测到已通过，继续爬取...")
                return True

        logger.error(f"等待超时 ({CAPTCHA_TIMEOUT}s)")
        return False

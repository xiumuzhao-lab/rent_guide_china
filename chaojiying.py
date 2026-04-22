#!/usr/bin/env python3
"""
超级鹰验证码识别 API 客户端

文档参考: https://www.chaojiying.com/api-14.html
API 地址: http://upload.chaojiying.net/Upload/Processing.php

使用方法:
    from chaojiying import solve

    result = solve(image_bytes, codetype=9101,
                   username='user', password='pass')
    # result: "120" 或 "120,150" 或 "x1,y1|x2,y2" 等
"""

import base64
import hashlib
import json
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger('chaojiying')

API_URL = "http://upload.chaojiying.net/Upload/Processing.php"
REPORT_URL = "http://upload.chaojiying.net/Upload/ReportError.php"

# 常用验证码类型
CODETYPE_SLIDER = 9101          # 滑块/坐标型 (返回 "x" 或 "x,y")
CODETYPE_CLICK_MULTI = 9102    # 多坐标点选型 (返回 "x1,y1|x2,y2|...")
CODETYPE_TEXT_4 = 1902         # 4位英文数字
CODETYPE_TEXT_6 = 1905         # 6位英文数字


def solve(image_bytes, codetype=CODETYPE_SLIDER,
          username='', password='', softid='96001'):
    """
    调用超级鹰识别验证码.

    Args:
        image_bytes: 图片二进制数据
        codetype: 验证码类型 (默认 9101 滑块坐标型)
        username: 超级鹰用户名
        password: 超级鹰密码 (明文, 内部会 md5)
        softid: 软件ID

    Returns:
        (pic_str, pic_id) 元组，失败返回 (None, None)
        pic_str: 识别结果 (如 "x1,y1|x2,y2")
        pic_id: 图片ID (用于 report_error 退积分)
    """
    if not username or not password:
        logger.warning('超级鹰账号未配置')
        return None, None

    b64 = base64.b64encode(image_bytes).decode('utf-8')
    pwd_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()

    params = urllib.parse.urlencode({
        'user': username,
        'pass2': pwd_md5,
        'softid': softid,
        'codetype': str(codetype),
        'file_base64': b64,
    }).encode('utf-8')

    try:
        req = urllib.request.Request(API_URL, data=params)
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        if result.get('err_no') == 0:
            pic_str = result.get('pic_str', '')
            pic_id = result.get('pic_id', '')
            logger.info(f'超级鹰识别成功: {pic_str} (pic_id={pic_id})')
            return pic_str, pic_id

        logger.warning(
            f'超级鹰识别失败: err_no={result.get("err_no")}, '
            f'{result.get("err_str", "")}'
        )
        return None, None
    except Exception as e:
        logger.error(f'超级鹰请求异常: {e}')
        return None, None


def report_error(pic_id, username='', password=''):
    """
    报告识别错误, 退还积分.

    Args:
        pic_id: 识别结果返回的 pic_id
        username: 超级鹰用户名
        password: 超级鹰密码
    """
    if not pic_id or not username or not password:
        return
    pwd_md5 = hashlib.md5(password.encode('utf-8')).hexdigest()
    params = urllib.parse.urlencode({
        'user': username,
        'pass2': pwd_md5,
        'softid': '96001',
        'pic_id': pic_id,
    }).encode('utf-8')
    try:
        req = urllib.request.Request(REPORT_URL, data=params)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_text = resp.read().decode('utf-8')
            logger.warning(f'已报告识别错误: pic_id={pic_id}, 响应: {resp_text}')
    except Exception as e:
        logger.warning(f'报告错误失败: pic_id={pic_id}, 异常: {e}')

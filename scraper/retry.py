"""
重试机制 + 错误日志管理

提供装饰器和流水线步骤级别的重试能力，以及结构化的错误日志记录。
"""

import asyncio
import functools
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Tuple, Type

from scraper.config import ERROR_LOG_FILE, OUTPUT_DIR

logger = logging.getLogger('lianjia')


# ============================================================
# 错误日志管理器
# ============================================================

class ErrorLog:
    """
    错误日志管理器，将结构化错误信息写入独立文件。

    格式: 时间戳 [级别] 步骤 | 错误类型: 错误信息 | 上下文
    """

    def __init__(self, log_file: Path = None):
        """
        初始化错误日志管理器.

        Args:
            log_file: 错误日志文件路径，默认使用 ERROR_LOG_FILE
        """
        self.log_file = log_file or ERROR_LOG_FILE
        self.entries = []
        self._ensure_dir()

    def _ensure_dir(self):
        """确保日志目录存在."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(self, step: str, error: Exception, context: dict = None,
            attempt: int = None):
        """
        记录一条错误.

        Args:
            step: 出错的步骤名称 (如 scrape, geo, save)
            error: 异常对象
            context: 附加上下文信息
            attempt: 当前重试次数
        """
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        error_type = type(error).__name__
        error_msg = str(error)

        parts = [f"{ts} [ERROR] {step} | {error_type}: {error_msg}"]
        if attempt is not None:
            parts.append(f"重试第 {attempt} 次")
        if context:
            ctx_str = " | ".join(f"{k}={v}" for k, v in context.items())
            parts.append(ctx_str)

        entry = " | ".join(parts)
        self.entries.append(entry)

        # 实时写入文件
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(entry + '\n')
                # 写入堆栈 (仅前3层)
                tb_lines = traceback.format_tb(error.__traceback__)[:3]
                for line in tb_lines:
                    f.write(f"  {line.strip()}\n")
                f.write('\n')
        except Exception:
            pass

        logger.warning(f"[{step}] {error_type}: {error_msg}"
                       + (f" (重试 {attempt})" if attempt else ""))

    def summary(self) -> str:
        """
        生成错误汇总.

        Returns:
            str: 错误统计摘要文本
        """
        if not self.entries:
            return "无错误记录"

        # 按步骤统计
        step_counts = {}
        for entry in self.entries:
            step = entry.split(' | ')[0].split('] ')[-1]
            step_counts[step] = step_counts.get(step, 0) + 1

        lines = [
            f"\n{'=' * 60}",
            f"错误汇总 | 共 {len(self.entries)} 个错误",
            f"{'=' * 60}",
        ]
        for step, count in sorted(step_counts.items()):
            lines.append(f"  {step}: {count} 次")

        lines.append(f"\n详细错误见: {self.log_file}")
        return '\n'.join(lines)


# 全局错误日志单例
error_log = ErrorLog()


# ============================================================
# 重试装饰器
# ============================================================

def retry_async(max_attempts: int = 3, backoff_base: float = 2.0,
                retry_on: Tuple[Type[Exception], ...] = (Exception,),
                step_name: str = ""):
    """
    异步函数重试装饰器.

    Args:
        max_attempts: 最大重试次数 (含首次执行)
        backoff_base: 退避基数 (秒), 第n次重试等待 backoff_base^n 秒
        retry_on: 需要重试的异常类型元组
        step_name: 步骤名称，用于错误日志
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            name = step_name or func.__name__
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_error = e
                    if attempt < max_attempts:
                        wait = backoff_base ** (attempt - 1)
                        error_log.log(name, e, attempt=attempt)
                        logger.warning(f"[{name}] 第 {attempt} 次失败，"
                                       f"{wait:.0f}s 后重试...")
                        await asyncio.sleep(wait)
                    else:
                        error_log.log(name, e, attempt=attempt,
                                      context={'status': '放弃重试'})
            raise last_error
        return wrapper
    return decorator


def retry_sync(max_attempts: int = 3, backoff_base: float = 2.0,
               retry_on: Tuple[Type[Exception], ...] = (Exception,),
               step_name: str = ""):
    """
    同步函数重试装饰器.

    Args:
        max_attempts: 最大重试次数 (含首次执行)
        backoff_base: 退避基数 (秒)
        retry_on: 需要重试的异常类型元组
        step_name: 步骤名称
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            name = step_name or func.__name__
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_error = e
                    if attempt < max_attempts:
                        wait = backoff_base ** (attempt - 1)
                        error_log.log(name, e, attempt=attempt)
                        logger.warning(f"[{name}] 第 {attempt} 次失败，"
                                       f"{wait:.0f}s 后重试...")
                        time.sleep(wait)
                    else:
                        error_log.log(name, e, attempt=attempt,
                                      context={'status': '放弃重试'})
            raise last_error
        return wrapper
    return decorator


# ============================================================
# 流水线步骤
# ============================================================

class PipelineStep:
    """
    流水线步骤: 封装名称、执行函数、重试配置.

    Attributes:
        name: 步骤名称
        func: 异步执行函数
        max_attempts: 最大重试次数
        backoff_base: 退避基数
        optional: 是否为可选步骤 (失败不中断整个流水线)
    """

    def __init__(self, name: str, func: Callable = None,
                 max_attempts: int = 3, backoff_base: float = 2.0,
                 optional: bool = False):
        """
        初始化流水线步骤.

        Args:
            name: 步骤名称
            func: 异步执行函数
            max_attempts: 最大重试次数
            backoff_base: 退避基数
            optional: 是否可选 (失败后继续后续步骤)
        """
        self.name = name
        self.func = func
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.optional = optional
        self.result = None
        self.error = None

    async def execute(self, *args, **kwargs):
        """
        执行步骤，自动重试.

        Args:
            *args: 传递给执行函数的位置参数
            **kwargs: 传递给执行函数的关键字参数

        Returns:
            步骤执行结果

        Raises:
            Exception: 重试耗尽后抛出最后一次异常
        """
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = self.func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                self.result = result
                self.error = None
                return self.result
            except Exception as e:
                last_error = e
                error_log.log(self.name, e, attempt=attempt)
                if attempt < self.max_attempts:
                    wait = self.backoff_base ** (attempt - 1)
                    logger.warning(
                        f"[{self.name}] 第 {attempt}/{self.max_attempts} 次失败，"
                        f"{wait:.0f}s 后重试..."
                    )
                    await asyncio.sleep(wait)

        # 全部重试失败
        self.error = last_error
        if self.optional:
            logger.error(f"[{self.name}] 失败 (可选步骤，继续执行)")
            return None
        raise last_error

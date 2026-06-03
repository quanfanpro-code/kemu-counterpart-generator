# -*- coding: utf-8 -*-
"""GUI 日志重定向器 - 将 print 和 logger 输出重定向到 GUI 日志队列"""
import sys
import datetime
import logging
import queue

# GUI 日志队列（全局单例）
GUI_LOG_QUEUE = queue.Queue()


class GuiLogRedirector:
    """重定向print输出到GUI日志队列"""

    def __init__(self, queue_obj=None):
        self.queue = queue_obj if queue_obj is not None else GUI_LOG_QUEUE

    def write(self, message):
        if message and message.strip():
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            self.queue.put(f"[{timestamp}] {message.strip()}")

    def flush(self):
        pass


class GuiLogHandler(logging.Handler):
    """将 logger 输出重定向到 GUI 日志队列"""

    def __init__(self, queue_obj=None):
        super().__init__()
        self.queue = queue_obj if queue_obj is not None else GUI_LOG_QUEUE
        self.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.queue.put(msg)
        except Exception:
            self.handleError(record)

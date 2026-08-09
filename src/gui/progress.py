# -*- coding: utf-8 -*-
"""GUI 进度消息队列。"""
import queue
from typing import Optional

class GuiProgressManager:
    """把工作线程的进度消息交给 GUI 主线程。"""

    def __init__(self):
        self.msg_queue = queue.Queue()

    def update(self, percent: float, message: str, phase: Optional[str] = None):
        """更新进度，可在任意线程调用。"""
        self.msg_queue.put(("update", percent, message, phase))


# 全局进度管理器实例
GUI_PROGRESS = GuiProgressManager()

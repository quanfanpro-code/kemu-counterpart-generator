# -*- coding: utf-8 -*-
"""进度条组件（终端版 + GUI 版 + 管理器）"""
import sys
import time
import queue
from typing import Optional

import tkinter as tk

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    USE_CTK = False
    ctk = None

# 进度条刷新频率(秒)
PROGRESS_UPDATE_FREQ = 0.5


class TerminalProgressBar:
    """终端进度条组件 (简化同步版)。"""

    def __init__(self, update_freq: float = PROGRESS_UPDATE_FREQ):
        self.update_freq = update_freq
        self.last_update_time = 0.0

    def update(self, percent: float, message: str, phase: Optional[str] = None):
        """更新进度状态。"""
        now = time.time()
        if now - self.last_update_time < self.update_freq and percent < 100:
            return

        self.last_update_time = now
        self._print_line(percent, message, phase)

        if percent >= 100:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def stop(self):
        """停止/完成。"""
        sys.stdout.write("\n")

    def _print_line(self, percent: float, message: str, phase: Optional[str]):
        """打印单行进度条。"""
        bar_len = 30
        filled = int(bar_len * percent / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        phase_str = f"[{phase}]" if phase else ""

        status_line = (
            f"\r{phase_str:<15} "
            f"{bar} "
            f"{percent:>5.1f}% | "
            f"{message:<20}"
        )
        try:
            sys.stdout.write(status_line)
            sys.stdout.flush()
        except Exception:
            pass


TERM_BAR = TerminalProgressBar(update_freq=PROGRESS_UPDATE_FREQ)


class CTkProgressBar:
    """CustomTkinter 进度条组件。"""

    def __init__(self, parent=None):
        self.parent = parent
        self.window = None
        self.progress = None
        self.label = None
        self.phase_label = None

    def show(self, title: str = "处理中"):
        """显示进度条窗口。"""
        if not USE_CTK:
            return

        self.window = ctk.CTkToplevel() if self.parent else ctk.CTk()
        self.window.title(title)
        self.window.geometry("500x150")
        if self.parent:
            self.window.transient(self.parent)
        self.window.grab_set()

        self.phase_label = ctk.CTkLabel(self.window, text="准备中...", font=("微软雅黑", 12))
        self.phase_label.pack(pady=(20, 5))

        self.progress = ctk.CTkProgressBar(self.window, width=400)
        self.progress.pack(pady=10)
        self.progress.set(0)

        self.label = ctk.CTkLabel(self.window, text="正在初始化...", font=("微软雅黑", 10))
        self.label.pack(pady=5)

        self.window.update()

    def update(self, percent: float, message: str, phase: Optional[str] = None):
        """更新进度。"""
        if self.window and USE_CTK:
            if phase:
                self.phase_label.configure(text=phase)
            self.label.configure(text=message)
            self.progress.set(percent / 100.0)
            self.window.update()

    def close(self):
        """关闭进度条。"""
        if self.window:
            self.window.destroy()
            self.window = None


class GuiProgressManager:
    """GUI 进度条管理器 (线程安全)。"""

    def __init__(self):
        self.progress_bar = None
        self.use_gui = USE_CTK or tk
        self.msg_queue = queue.Queue()
        self._gui_callback = None

    def set_gui_callback(self, callback):
        """设置GUI回调函数，用于主线程更新。"""
        self._gui_callback = callback

    def create_progress_bar(self, parent=None):
        # 在主线程中创建，或者由外部管理
        pass

    def update(self, percent: float, message: str, phase: Optional[str] = None):
        """更新进度 (可在任意线程调用)。"""
        if self._gui_callback:
            self.msg_queue.put(("update", percent, message, phase))
        else:
            TERM_BAR.update(percent, message, phase)

    def stop(self):
        """停止/完成。"""
        if self._gui_callback:
            self.msg_queue.put(("stop", None, None, None))
        else:
            TERM_BAR.stop()

    def close(self):
        self.stop()


# 全局进度管理器实例
GUI_PROGRESS = GuiProgressManager()

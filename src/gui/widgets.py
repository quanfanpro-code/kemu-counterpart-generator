# -*- coding: utf-8 -*-
"""GUI 组件（适配器模式，自动选择 ctk/tk）"""
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    USE_CTK = False
    ctk = None


def _make_label(parent, text, **kw):
    """统一标签创建"""
    font = kw.pop('font', ("微软雅黑", 11))
    if USE_CTK:
        # CTkLabel 使用 text_color，不接受 fg；清理 tkinter 专属参数
        kw.pop('fg', None)
        kw.pop('anchor', None)
        return ctk.CTkLabel(parent, text=text, font=font, **kw)
    else:
        fg = kw.pop('text_color', None) or kw.pop('fg', None)
        kw.pop('anchor', None)
        return tk.Label(parent, text=text, font=font, fg=fg, **kw)


def _make_button(parent, text, command, **kw):
    """统一按钮创建"""
    font = kw.pop('font', ("微软雅黑", 11))
    width = kw.pop('width', 10)
    if USE_CTK:
        return ctk.CTkButton(parent, text=text, command=command, font=font, width=width, **kw)
    else:
        return tk.Button(parent, text=text, command=command, font=font, width=width, **kw)


def _make_entry(parent, **kw):
    """统一输入框创建"""
    font = kw.pop('font', ("微软雅黑", 11))
    width = kw.pop('width', 20)
    if USE_CTK:
        return ctk.CTkEntry(parent, font=font, width=width, **kw)
    else:
        return tk.Entry(parent, font=font, width=width, **kw)


def _make_combobox(parent, values, **kw):
    """统一下拉框创建"""
    font = kw.pop('font', ("微软雅黑", 10))
    width = kw.pop('width', 25)
    if USE_CTK:
        return ctk.CTkComboBox(parent, values=values, font=font, width=width, **kw)
    else:
        cb = ttk.Combobox(parent, values=values, font=font, width=width, state="readonly")
        return cb


def _make_frame(parent, **kw):
    """统一框架创建"""
    if USE_CTK:
        fg = kw.pop('fg_color', "transparent")
        return ctk.CTkFrame(parent, fg_color=fg, **kw)
    else:
        return tk.Frame(parent, **kw)


def _make_toplevel(parent=None, title="", geometry="", grab=True):
    """统一顶层窗口创建"""
    if USE_CTK:
        win = ctk.CTkToplevel(parent) if parent else ctk.CTk()
    else:
        win = tk.Toplevel(parent) if parent else tk.Tk()
    win.title(title)
    if geometry:
        win.geometry(geometry)
    if parent:
        win.transient(parent)
    if grab:
        win.grab_set()
    return win


class CustomInputDialog:
    """自定义输入对话框，支持数字输入（适配器模式）。"""

    def __init__(self, parent, title: str, prompt: str,
                 initial_value: float = 0.0,
                 min_value: float = None, max_value: float = None):
        self.result = None
        self.window = None

        self.window = _make_toplevel(parent, title, "400x200")
        _make_label(self.window, text=prompt, font=("微软雅黑", 12)).pack(pady=20)

        self.entry = _make_entry(self.window, width=250, font=("微软雅黑", 12))
        self.entry.insert(0, str(initial_value))
        self.entry.pack(pady=10)

        # 最小值/最大值提示
        if min_value is not None or max_value is not None:
            hint_text = ""
            if min_value is not None:
                hint_text += f"最小值: {min_value}"
            if max_value is not None:
                hint_text += f", 最大值: {max_value}"
            if USE_CTK:
                _make_label(self.window, text=hint_text, font=("微软雅黑", 9),
                            text_color="gray").pack(pady=5)
            else:
                _make_label(self.window, text=hint_text, font=("微软雅黑", 9),
                            fg="gray").pack(pady=5)

        # 确定/取消按钮
        btn_frame = _make_frame(self.window)
        btn_frame.pack(pady=20)
        _make_button(btn_frame, text="确定", command=self._on_ok, width=80).pack(side="left", padx=10)
        _make_button(btn_frame, text="取消", command=self._on_cancel, width=80).pack(side="left", padx=10)

        self.entry.focus()
        self.entry.bind("<Return>", lambda e: self._on_ok())
        self.window.wait_window()

    def _on_ok(self):
        try:
            value = float(self.entry.get())
            self.result = value
            self.window.destroy()
        except ValueError:
            messagebox.showwarning("输入错误", "请输入有效的数字！")

    def _on_cancel(self):
        self.result = None
        self.window.destroy()

    def get_result(self):
        return self.result


class CustomMessageBox:
    """自定义消息框（适配器模式）。"""

    @staticmethod
    def _show_dialog(parent, title, message, kind):
        """通用对话框显示（ctk 模式）。"""
        dialog = ctk.CTkToplevel(parent) if parent else ctk.CTk()
        dialog.title(title)
        dialog.geometry("420x180")
        if parent:
            dialog.transient(parent)
        dialog.grab_set()

        color = {"error": "#FF6B6B", "warning": "#FFB020"}.get(kind, "#3B8ED0")

        ctk.CTkLabel(dialog, text=title, font=("微软雅黑", 14, "bold"),
                      text_color=color).pack(pady=(18, 8), padx=16)
        ctk.CTkLabel(dialog, text=message, font=("微软雅黑", 11),
                      wraplength=380, justify="left").pack(pady=(0, 12), padx=16)

        btn = ctk.CTkButton(dialog, text="确定", width=90, command=dialog.destroy)
        btn.pack(pady=(0, 16))
        btn.focus_set()

        dialog.bind("<Return>", lambda _e: dialog.destroy())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.wait_window()

    @staticmethod
    def showinfo(title, message, parent=None):
        if USE_CTK and parent is not None:
            CustomMessageBox._show_dialog(parent, title, message, kind="info")
        else:
            messagebox.showinfo(title, message)

    @staticmethod
    def showwarning(title, message, parent=None):
        if USE_CTK and parent is not None:
            CustomMessageBox._show_dialog(parent, title, message, kind="warning")
        else:
            messagebox.showwarning(title, message)

    @staticmethod
    def showerror(title, message, parent=None):
        if USE_CTK and parent is not None:
            CustomMessageBox._show_dialog(parent, title, message, kind="error")
        else:
            messagebox.showerror(title, message)

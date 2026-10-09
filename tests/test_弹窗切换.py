"""验证设置弹窗切出后可重新激活，关闭后主窗口恢复操作。"""
import ctypes
import tkinter as tk

import customtkinter as ctk
import pandas as pd
import pytest


@pytest.mark.parametrize("kind", ["列名", "筛选"])
def test_弹窗使用系统模态且切回可操作(monkeypatch, kind):
    from src.gui import 批处理设置, 筛选设置
    root = ctk.CTk()
    other = tk.Tk()
    other.title("模拟切换到其他窗口")
    root.update()
    other.update()
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    parent_handle = ctypes.c_void_p(user32.GetParent(root.winfo_id()))
    observations = []
    cls = 批处理设置.BatchMappingDialog if kind == "列名" else 筛选设置.ScreeningDialog
    original = cls.__init__

    def create(self, *args):
        original(self, *args)
        def switch_and_accept():
            try:
                observations.append(("disabled", not user32.IsWindowEnabled(parent_handle)))
                observations.append(("topmost", not bool(self.attributes("-topmost"))))
                other.focus_force()
                other.update()
                observations.append(("other", other.focus_get() == other))
                self.deiconify()
                self.lift()
                self.focus_force()
                self.update()
                observations.append(("visible", bool(self.winfo_ismapped())))
                observations.append(("focus", self.focus_get() == self))
                if kind == "列名":
                    self.choices["会计月"].set("期间")
                    self.accept()
                else:
                    self.skip()
            finally:
                if self.winfo_exists():
                    self.destroy()
        self.after(100, switch_and_accept)
    monkeypatch.setattr(cls, "__init__", create)
    try:
        if kind == "列名":
            result = 批处理设置.ask_batch_mapping(root, ["期间"], ["会计月"])
            assert result == {"会计月": "期间"}
        else:
            result = 筛选设置.ask_screening_options(
                root, pd.DataFrame({"日期": ["2026-10-09"]}), True, False)
            assert result == {}
        assert all(value for _, value in observations), observations
        assert user32.IsWindowEnabled(parent_handle)
        assert root.grab_current() is None
    finally:
        other.destroy()
        root.destroy()

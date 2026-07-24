# -*- coding: utf-8 -*-
"""列映射对话框（适配器模式，自动选择 ctk/tk）"""
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Dict, Optional

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    USE_CTK = False
    ctk = None

from .widgets import (
    _make_label, _make_button, _make_combobox, _make_frame,
    _make_toplevel, CustomMessageBox,
)


def show_column_mapping_dialog(all_columns: List[str], required_columns: List[str],
                                parent=None) -> Optional[Dict[str, str]]:
    """显示列映射对话框，返回映射字典（适配器模式，自动选择 ctk/tk）。"""
    if not USE_CTK and not tk:
        return None

    dialog = _make_toplevel(parent, title="列映射配置", geometry="550x450")

    # 提示标签
    if USE_CTK:
        _make_label(dialog, text="检测到输入文件缺少必要列，请手动建立映射关系：",
                    font=("微软雅黑", 12), text_color="#FF6B6B").pack(pady=10, padx=10)
    else:
        _make_label(dialog, text="检测到输入文件缺少必要列，请手动建立映射关系：",
                    font=("微软雅黑", 11), fg="red").pack(pady=10, padx=10)

    # 滚动容器
    frame_container = _make_frame(dialog)
    frame_container.pack(fill="both", expand=True, padx=10, pady=5)

    canvas = tk.Canvas(frame_container)
    scrollbar = tk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
    if USE_CTK:
        scrollable_frame = ctk.CTkFrame(canvas, fg_color="transparent")
    else:
        scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # 自动匹配关键词
    auto_match_keywords = {
        '账套': ['账套', '核算账套', '公司账套', '账套名', '公司', '核算主体', '主体'],
        '会计月': ['月', '日期', 'date', '期间', 'time', '制单日期', '业务日期'],
        '凭证种类': ['种类', '类型', 'type', 'category', '凭证字'],
        '凭证编号': ['编号', '凭证号', 'number', 'no'],
        '一级科目': ['科目', 'subject', '一级', '名称'],
        '借方发生额': ['借方', 'debit', '借', 'jf'],
        '贷方发生额': ['贷方', 'credit', '贷', 'df']
    }

    comboboxes = {}
    for idx, req_col in enumerate(required_columns):
        row_frame = _make_frame(scrollable_frame)
        row_frame.pack(fill="x", pady=5)

        display_name = req_col
        if req_col == '会计月':
            display_name = '会计月/日期'

        _make_label(row_frame, text=f"{display_name} 对应:",
                    font=("微软雅黑", 11)).pack(side="left")

        combo_values = list(all_columns)
        if req_col == '凭证种类':
            combo_values = ["无/不适用"] + combo_values

        cb = _make_combobox(row_frame, values=combo_values, width=250, font=("微软雅黑", 11))
        cb.pack(side="left", padx=10)

        # 自动匹配
        matched = False
        if req_col in all_columns:
            cb.set(req_col)
            matched = True
        else:
            keywords = auto_match_keywords.get(req_col, [])
            for col in all_columns:
                col_lower = str(col).lower()
                for kw in keywords:
                    if kw in col_lower:
                        cb.set(col)
                        matched = True
                        break
                if matched:
                    break
        comboboxes[req_col] = cb

    result = [None]

    def on_confirm():
        current_mapping = {}
        missing_selections = []
        for req_col, cb in comboboxes.items():
            val = cb.get()
            if not val:
                missing_selections.append(req_col)
            else:
                current_mapping[req_col] = val
        if missing_selections:
            CustomMessageBox.showwarning("提示",
                                         f"请为以下列选择映射：\n{', '.join(missing_selections)}")
            return
        result[0] = current_mapping
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    # 确认/取消按钮
    btn_frame = _make_frame(dialog)
    btn_frame.pack(pady=10)
    _make_button(btn_frame, text="确定", command=on_confirm, width=80,
                 font=("微软雅黑", 11)).pack(side="left", padx=20)
    _make_button(btn_frame, text="取消", command=on_cancel, width=80,
                 font=("微软雅黑", 11)).pack(side="left", padx=20)

    dialog.wait_window()
    return result[0]

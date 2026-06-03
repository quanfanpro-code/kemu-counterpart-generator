# -*- coding: utf-8 -*-
"""GUI 应用主入口（适配器模式，自动选择 ctk/tk）"""
import sys
import os
import traceback
import threading
import queue
from typing import List, Dict, Optional

import tkinter as tk
from tkinter import filedialog, ttk

import pandas as pd

try:
    import customtkinter as ctk
    USE_CTK = True
except ImportError:
    USE_CTK = False
    ctk = None

from .widgets import (
    _make_label, _make_button, _make_entry, _make_combobox, _make_frame,
    CustomMessageBox,
)
from .progress import GUI_PROGRESS
from .log_redirector import GuiLogRedirector, GUI_LOG_QUEUE
from .column_mapper import show_column_mapping_dialog


def run_gui():
    """运行 GUI 应用程序（适配器模式，自动选择 ctk/tk）。"""
    global progress_bar

    # 重定向日志到 GUI 队列
    log_redirector = GuiLogRedirector(GUI_LOG_QUEUE)
    sys.stdout = log_redirector
    sys.stderr = log_redirector

    # 创建主窗口
    if USE_CTK:
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        app = ctk.CTk()
        app.title("对方科目生成工具 v1.8.0")
        app.geometry("640x550")
        app.resizable(True, True)
    else:
        app = tk.Tk()
        app.title("对方科目生成工具 v1.7.0")
        app.geometry("600x520")
        app.resizable(True, True)

    # 主框架
    main_frame = _make_frame(app)
    main_frame.pack(fill="both", expand=True, padx=10, pady=8)

    mapping_container = None
    mapping_comboboxes: Dict[str, object] = {}
    current_input_path = [None]
    current_output_path = [None]
    current_df: List[Optional[pd.DataFrame]] = [None]
    confirm_btn_widget = [None]

    auto_match_keywords = {
        '账套': ['账套', '核算账套', '公司账套', '账套名', '公司', '核算主体', '主体'],
        '会计月': ['月', '日期', 'date', '期间', 'time', '制单日期', '业务日期'],
        '凭证种类': ['种类', '类型', 'type', 'category', '凭证字'],
        '凭证编号': ['编号', '凭证号', 'number', 'no'],
        '一级科目': ['科目', 'subject', '一级', '名称'],
        '借方发生额': ['借方', 'debit', '借', 'jf'],
        '贷方发生额': ['贷方', 'credit', '贷', 'df']
    }

    def show_mapping_config(file_columns: List[str], missing_cols: List[str]):
        nonlocal mapping_container, mapping_comboboxes

        if mapping_container:
            mapping_container.destroy()

        mapping_container = _make_frame(main_frame)
        mapping_container.pack(fill="x", padx=3, pady=3)

        # 提示标签
        if USE_CTK:
            _make_label(mapping_container, text="⚠️ 缺少必要列，请配置映射：",
                        font=("微软雅黑", 10), text_color="#FF6B6B").grid(
                row=0, column=0, columnspan=3, pady=(3, 2), sticky="w")
        else:
            _make_label(mapping_container, text="⚠️ 缺少必要列，请配置映射：",
                        font=("微软雅黑", 10), fg="red").grid(
                row=0, column=0, columnspan=3, pady=(3, 2), sticky="w")

        mapping_comboboxes.clear()

        for idx, req_col in enumerate(missing_cols):
            row = (idx // 3) + 1
            col = idx % 3

            display_name = req_col

            _make_label(mapping_container, text=f"{display_name}:",
                        font=("微软雅黑", 9)).grid(
                row=row, column=col * 2, padx=(5, 0), pady=1, sticky="e")

            combo_values = list(file_columns)
            if req_col == '凭证种类':
                combo_values = ["无/不适用"] + combo_values

            cb = _make_combobox(mapping_container, values=combo_values, width=120,
                                font=("微软雅黑", 9))
            cb.grid(row=row, column=col * 2 + 1, padx=(0, 5), pady=1, sticky="w")

            # 自动匹配
            matched = False
            if req_col in file_columns:
                cb.set(req_col)
                matched = True
            else:
                keywords = auto_match_keywords.get(req_col, [])
                for col_name in file_columns:
                    col_lower = str(col_name).lower()
                    for kw in keywords:
                        if kw in col_lower:
                            cb.set(col_name)
                            matched = True
                            break
                    if matched:
                        break
            mapping_comboboxes[req_col] = cb

        if confirm_btn_widget[0]:
            confirm_btn_widget[0].pack(pady=5)

        app.update_idletasks()

    def confirm_mapping():
        nonlocal mapping_container
        mapping = {}
        missing = []
        for req_col, cb in mapping_comboboxes.items():
            val = cb.get()
            if not val:
                missing.append(req_col)
            mapping[req_col] = val

        if missing:
            CustomMessageBox.showwarning("提示",
                                         f"请为以下列选择映射：\n{', '.join(missing)}",
                                         parent=app)
            return

        try:
            import python_calamine
            engine = 'calamine'
        except ImportError:
            engine = 'openpyxl'

        df = pd.read_excel(current_input_path[0], engine=engine)

        # 应用列映射
        from src.pipeline.data_loader import apply_column_mapping
        df = apply_column_mapping(df, mapping)

        required_after = ['会计月', '凭证编号', '一级科目', '借方发生额', '贷方发生额']
        still_missing = [col for col in required_after if col not in df.columns]
        if still_missing:
            CustomMessageBox.showerror("错误",
                                       f"映射后仍缺少必要列: {still_missing}",
                                       parent=app)
            return

        current_df[0] = df
        if mapping_container:
            mapping_container.destroy()
            mapping_container = None
        if confirm_btn_widget[0]:
            confirm_btn_widget[0].pack_forget()

        start_processing()

    def start_processing():
        if current_df[0] is None:
            return

        df = current_df[0]
        output_path = current_output_path[0]

        try:
            anomaly_threshold = float(threshold_entry.get())
        except ValueError:
            anomaly_threshold = 10000.0
        print(f"异常分录筛选阈值设定为: {anomaly_threshold}")

        progress_label.configure(text="正在处理...")
        if USE_CTK:
            progress_bar.set(0)
        else:
            progress_bar['value'] = 0

        def worker():
            try:
                from src.pipeline.orchestrator import run_processing_pipeline
                run_processing_pipeline(df, anomaly_threshold, output_path)

                def show_success():
                    if USE_CTK:
                        progress_bar.set(1.0)
                    else:
                        progress_bar['value'] = 100
                    if os.path.exists(output_path):
                        progress_label.configure(
                            text=f"完成！输出: {os.path.basename(output_path)}")
                        print(f"处理完成！输出文件: {output_path}")
                    else:
                        progress_label.configure(text="完成！但未检测到输出文件")

                app.after(0, show_success)
            except Exception as e:
                def show_error_worker():
                    progress_label.configure(text="处理失败")
                    print(f"错误: {str(e)}")
                    traceback.print_exc()
                app.after(0, show_error_worker)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def select_file():
        nonlocal mapping_container
        input_path = filedialog.askopenfilename(
            title="请选择序时账 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )

        if not input_path:
            return

        current_input_path[0] = input_path
        selected_file_label.configure(text=f"已选择: {os.path.basename(input_path)}")
        print(f"已选择文件: {os.path.basename(input_path)}")

        dir_name = os.path.dirname(input_path)
        file_name = os.path.basename(input_path)
        name, ext = os.path.splitext(file_name)
        output_name = f"{name}生成对方科目{ext}"
        output_path = os.path.join(dir_name, output_name)
        current_output_path[0] = output_path

        if mapping_container:
            mapping_container.destroy()
            mapping_container = None
        if confirm_btn_widget[0]:
            confirm_btn_widget[0].pack_forget()

        from src.pipeline.data_loader import check_column_mapping_needed
        need_mapping, file_columns, missing_cols = check_column_mapping_needed(input_path)

        if need_mapping:
            progress_label.configure(text="请配置列映射...")
            print(f"检测到缺少必要列: {', '.join(missing_cols)}")
            show_mapping_config(file_columns, missing_cols)
        else:
            try:
                import python_calamine
                engine = 'calamine'
            except ImportError:
                engine = 'openpyxl'
            df = pd.read_excel(input_path, engine=engine)
            current_df[0] = df
            print("文件列名匹配成功，开始处理...")
            start_processing()

    # ---- 顶部信息栏 ----
    if USE_CTK:
        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_frame.pack(fill="x", pady=(0, 2))
        selected_file_label = ctk.CTkLabel(
            top_frame, text="请选择序时账Excel文件",
            font=("微软雅黑", 9), text_color="gray")
        selected_file_label.pack(side="left")

        def toggle_theme():
            current = ctk.get_appearance_mode()
            new_mode = "Dark" if current == "Light" else "Light"
            ctk.set_appearance_mode(new_mode)
            theme_btn.configure(text="☀️" if new_mode == "Light" else "🌙")

        current_mode = ctk.get_appearance_mode()
        theme_icon = "☀️" if current_mode == "Light" else "🌙"
        theme_btn = ctk.CTkButton(
            top_frame, text=theme_icon, width=30, height=24,
            font=("Segoe UI Emoji", 12), command=toggle_theme)
        theme_btn.pack(side="right")
    else:
        selected_file_label = tk.Label(
            main_frame, text="请选择序时账Excel文件",
            font=("微软雅黑", 9), fg="gray")
        selected_file_label.pack(pady=(0, 2))

    # ---- 选择文件按钮 ----
    _make_button(main_frame, text="📁 选择Excel文件", command=select_file,
                 width=160, font=("微软雅黑", 11)).pack(pady=3)

    # ---- 阈值输入 ----
    threshold_frame = _make_frame(main_frame)
    threshold_frame.pack(pady=3)
    _make_label(threshold_frame, text="异常金额阈值:", font=("微软雅黑", 9)).pack(
        side="left", padx=(0, 5))
    threshold_entry = _make_entry(threshold_frame, width=100, font=("微软雅黑", 10))
    threshold_entry.pack(side="left")
    threshold_entry.insert(0, "10000")

    # ---- 进度条 ----
    if USE_CTK:
        progress_bar = ctk.CTkProgressBar(main_frame, width=300, height=18)
        progress_bar.pack(pady=3)
        progress_bar.set(0)
        progress_label = ctk.CTkLabel(main_frame, text="等待操作...", font=("微软雅黑", 10))
        progress_label.pack()
    else:
        style = ttk.Style()
        style.configure("Custom.Horizontal.TProgressbar", thickness=18)
        progress_bar = ttk.Progressbar(
            main_frame, length=300, mode='determinate',
            style="Custom.Horizontal.TProgressbar")
        progress_bar.pack(pady=3)
        progress_bar['value'] = 0
        progress_label = tk.Label(main_frame, text="等待操作...", font=("微软雅黑", 10))
        progress_label.pack()

    # ---- 确认按钮（默认隐藏） ----
    confirm_btn_widget[0] = _make_button(
        main_frame, text="确认并开始处理", command=confirm_mapping,
        width=140, font=("微软雅黑", 11))
    confirm_btn_widget[0].pack_forget()

    # ---- 日志区域 ----
    if USE_CTK:
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill="both", expand=True, padx=3, pady=5)
        log_text = ctk.CTkTextbox(log_frame, height=120, font=("Consolas", 9))
        log_text.pack(fill="both", expand=True)
    else:
        log_frame = tk.Frame(main_frame)
        log_frame.pack(fill="both", expand=True, padx=3, pady=5)
        log_scroll = tk.Scrollbar(log_frame)
        log_scroll.pack(side="right", fill="y")
        log_text = tk.Text(log_frame, height=8, font=("Consolas", 9),
                           yscrollcommand=log_scroll.set)
        log_text.pack(fill="both", expand=True)
        log_scroll.config(command=log_text.yview)

    # ---- 队列轮询回调 ----
    def check_queue():
        try:
            while True:
                msg_type, percent, message, phase = GUI_PROGRESS.msg_queue.get_nowait()
                if msg_type == "update":
                    progress_label.configure(text=message)
                    if USE_CTK:
                        progress_bar.set(percent / 100.0)
                    else:
                        progress_bar['value'] = percent
                    app.update_idletasks()
                elif msg_type == "stop":
                    pass
        except queue.Empty:
            pass

        try:
            while True:
                log_msg = GUI_LOG_QUEUE.get_nowait()
                if USE_CTK:
                    log_text.configure(state="normal")
                    log_text.insert("end", log_msg + "\n")
                    log_text.see("end")
                    log_text.configure(state="disabled")
                else:
                    log_text.configure(state="normal")
                    log_text.insert("end", log_msg + "\n")
                    log_text.see("end")
                    log_text.configure(state="disabled")
        except queue.Empty:
            pass

        app.after(100, check_queue)

    GUI_PROGRESS.set_gui_callback(True)
    app.after(100, check_queue)

    # ---- 版本号 ----
    _make_label(main_frame, text="v1.8.0", font=("微软雅黑", 8),
                text_color="gray" if USE_CTK else None,
                fg="gray" if not USE_CTK else None).pack(side="bottom", pady=(0, 2))

    app.mainloop()

    # 恢复标准输出
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

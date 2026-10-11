# -*- coding: utf-8 -*-
"""GUI 应用主入口（适配器模式，自动选择 ctk/tk）"""
import sys
import os
import threading
import queue
import math
from typing import List, Optional

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
    _make_label, _make_button, _make_entry, _make_frame,
    CustomMessageBox,
)
from .progress import GUI_PROGRESS
from .log_redirector import GuiLogRedirector, GUI_LOG_QUEUE


def run_gui():
    """运行 GUI 应用程序（适配器模式，自动选择 ctk/tk）。"""
    import gc
    # 重复启动窗口时，在主线程回收上一窗口，避免后台分配触发其回收。
    gc.collect()
    # 重定向日志到 GUI 队列
    log_redirector = GuiLogRedirector(GUI_LOG_QUEUE)
    sys.stdout = log_redirector
    sys.stderr = log_redirector

    # 创建主窗口
    if USE_CTK:
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        app = ctk.CTk()
        app.title("对方科目生成工具 v2.3.0")
        app.geometry("640x550")
        app.resizable(True, True)
    else:
        app = tk.Tk()
        app.title("对方科目生成工具 v2.3.0")
        app.geometry("600x520")
        app.resizable(True, True)

    # 主框架
    main_frame = _make_frame(app)
    main_frame.pack(fill="both", expand=True, padx=10, pady=8)

    current_input_path = [None]
    current_folder = [None]
    current_output_path = [None]
    current_df: List[Optional[pd.DataFrame]] = [None]
    busy = [False]
    stop_event = threading.Event()
    progress_active = [False]
    operation_widgets = []
    ui_requests = queue.Queue()

    def set_busy(value):
        busy[0] = value
        for widget in operation_widgets:
            widget.configure(state="disabled" if value else "normal")
        start_button.configure(state="disabled" if value or (
            current_df[0] is None and current_folder[0] is None) else "normal")
        stop_button.configure(state="normal" if value and not stop_event.is_set() else "disabled")

    def stop_processing():
        if busy[0]:
            stop_event.set()
            stop_button.configure(state="disabled")
            progress_label.configure(text="正在停止：等待当前文件完成并保存...")
            print("已请求安全停止，当前文件完成后不再处理下一份。")

    def begin_processing():
        if busy[0]:
            return
        try:
            threshold = float(threshold_entry.get())
            if not math.isfinite(threshold) or threshold < 0:
                raise ValueError()
        except ValueError:
            CustomMessageBox.showwarning("阈值无效", "异常金额阈值必须为非负有限数字", parent=app)
            return
        stop_event.clear()
        if current_folder[0]:
            process_folder(current_folder[0], threshold)
        else:
            start_processing()

    def begin_progress():
        while not GUI_PROGRESS.msg_queue.empty():
            try:
                GUI_PROGRESS.msg_queue.get_nowait()
            except queue.Empty:
                break
        progress_active[0] = True
        if USE_CTK:
            progress_bar.set(0)
        else:
            progress_bar['value'] = 0

    def request_on_main(function, *args):
        response = queue.Queue(maxsize=1)
        ui_requests.put((function, args, response))
        ok, value = response.get()
        if not ok:
            raise value
        return value

    def start_processing():
        if current_df[0] is None or busy[0]:
            return

        df = current_df[0]
        output_path = current_output_path[0]
        set_busy(True)
        from .筛选设置 import ask_screening_options
        screening_options = ask_screening_options(app, df, time_screen_var.get(), split_screen_var.get())
        if screening_options is None:
            progress_label.configure(text="已取消本次处理")
            set_busy(False)
            return
        # 记录处理前的文件修改时间，避免把上次遗留的旧文件误判为本次成功
        prev_mtime = os.path.getmtime(output_path) if os.path.exists(output_path) else None

        anomaly_threshold = float(threshold_entry.get())
        print(f"异常分录筛选阈值设定为: {anomaly_threshold}")

        set_busy(True)
        begin_progress()
        progress_label.configure(text="正在处理...")

        def worker():
            try:
                from src.pipeline.orchestrator import run_processing_pipeline
                pipeline_ok = run_processing_pipeline(df, anomaly_threshold, output_path,
                                                      progress_callback=GUI_PROGRESS.update,
                                                      screening_options=screening_options)

                def show_success():
                    progress_active[0] = False
                    set_busy(False)
                    # 流水线返回成功 且 文件确实是本次新生成的，才算成功
                    file_fresh = (os.path.exists(output_path)
                                  and (prev_mtime is None or os.path.getmtime(output_path) > prev_mtime))
                    if pipeline_ok and file_fresh:
                        if USE_CTK:
                            progress_bar.set(1.0)
                        else:
                            progress_bar['value'] = 100
                        progress_label.configure(
                            text=(f"已停止，当前文件已保存: {os.path.basename(output_path)}"
                                  if stop_event.is_set() else
                                  f"完成！输出: {os.path.basename(output_path)}"))
                        print(f"处理完成！输出文件: {output_path}")
                    else:
                        progress_label.configure(text="处理失败，请查看日志")
                        print("处理失败：流水线未成功或未生成新的输出文件")

                ui_requests.put((show_success, (), None))
            except Exception as e:
                def show_error_worker(error=e):
                    progress_active[0] = False
                    set_busy(False)
                    progress_label.configure(text="处理失败")
                    print(f"错误: {error}")
                ui_requests.put((show_error_worker, (), None))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def select_file():
        if busy[0]:
            return
        input_path = filedialog.askopenfilename(
            title="请选择序时账 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )

        if not input_path:
            return
        progress_active[0] = False
        current_df[0] = None
        current_folder[0] = None
        set_busy(False)

        current_input_path[0] = input_path
        selected_file_label.configure(text=f"已选择: {os.path.basename(input_path)}")
        print(f"已选择文件: {os.path.basename(input_path)}")

        dir_name = os.path.dirname(input_path)
        file_name = os.path.basename(input_path)
        name, ext = os.path.splitext(file_name)
        output_name = f"{name}生成对方科目{ext}"
        output_path = os.path.join(dir_name, output_name)
        current_output_path[0] = output_path

        from src.io.reader import check_column_mapping_needed
        need_mapping, file_columns, missing_cols = check_column_mapping_needed(input_path)

        if need_mapping:
            from .批处理设置 import ask_batch_mapping
            mapping = ask_batch_mapping(
                app, file_columns,
                ["会计月", "凭证编号", "一级科目", "借方发生额", "贷方发生额", "凭证种类"],
                title="请确认列名对应",
                hint="确认列名后，请点击主界面的“开始处理”。取消不会开始处理。")
            if mapping is None:
                progress_label.configure(text="列映射已取消，请重新选择文件")
                return
            from src.io.reader import load_and_preprocess_data
            current_df[0] = load_and_preprocess_data(
                input_path, interactive=False, column_mapping_dialog=lambda cols, reqs: mapping)
        else:
            from src.io.reader import load_and_preprocess_data
            df = load_and_preprocess_data(input_path, interactive=False)
            if df is None:
                progress_label.configure(text="数据加载失败")
                return
            current_df[0] = df
        if current_df[0] is None:
            progress_label.configure(text="数据加载失败，请查看日志")
        else:
            progress_label.configure(text="文件已就绪，请点击开始处理")
            print("文件已就绪，等待开始处理。")
        set_busy(False)

    def select_folder():
        if busy[0]:
            return
        folder = filedialog.askdirectory(parent=app, title="请选择存放序时账的文件夹")
        if not folder:
            return
        current_folder[0] = folder
        current_df[0] = None
        current_input_path[0] = None
        progress_active[0] = False
        selected_file_label.configure(text=f"已选择文件夹: {os.path.basename(folder)}")
        progress_label.configure(text="文件夹已就绪，请点击开始处理")
        set_busy(False)

    def process_folder(folder, threshold):
        recursive = recursive_var.get()
        time_enabled, split_enabled = time_screen_var.get(), split_screen_var.get()
        current_df[0] = None
        selected_file_label.configure(text=f"已选择文件夹: {os.path.basename(folder)}")
        print(f"批处理输入文件夹: {folder}；包含子文件夹: {recursive}")
        set_busy(True)
        begin_progress()
        progress_label.configure(text="正在扫描文件夹...")

        def worker():
            try:
                from src.pipeline.批处理 import run_batch
                from .批处理设置 import ask_batch_mapping
                from .筛选设置 import ask_screening_options
                result = run_batch(
                    folder, recursive=recursive, anomaly_threshold=threshold,
                    mapping_dialog=lambda cols, reqs: request_on_main(ask_batch_mapping, app, cols, reqs),
                    screening_dialog=(lambda df: request_on_main(
                        ask_screening_options, app, df, time_enabled, split_enabled))
                    if time_enabled or split_enabled else None,
                    progress_callback=GUI_PROGRESS.update, stop_event=stop_event)
                def finish():
                    progress_active[0] = False
                    set_busy(False)
                    if result["output_dir"] is None:
                        progress_label.configure(text="没有找到可处理的序时账文件")
                        print("没有候选 Excel 文件，未创建结果目录。")
                        return
                    from collections import Counter
                    counts = Counter(row["状态"] for row in result["records"])
                    summary = "，".join(f"{name} {counts[name]}" for name in
                                       ("成功", "部分失败", "失败", "未处理"))
                    state = "批处理已停止" if stop_event.is_set() else "批处理完成"
                    progress_label.configure(text=f"{state}：{summary}")
                    if not stop_event.is_set():
                        if USE_CTK:
                            progress_bar.set(1)
                        else:
                            progress_bar['value'] = 100
                    print(f"{state}：{summary}\n结果文件夹: {result['output_dir']}\n请查看批处理清单.csv")
                ui_requests.put((finish, (), None))
            except Exception as exc:
                def fail(error=exc):
                    progress_active[0] = False
                    set_busy(False)
                    progress_label.configure(text="批处理失败，请查看日志")
                    print(f"批处理错误: {error}")
                ui_requests.put((fail, (), None))
        threading.Thread(target=worker, daemon=True).start()

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
    input_frame = _make_frame(main_frame)
    input_frame.pack(fill="x", padx=3, pady=3)
    file_button = _make_button(input_frame, text="📁 选择Excel文件", command=select_file,
                              width=160 if USE_CTK else 16, font=("微软雅黑", 11))
    file_button.grid(row=0, column=0, padx=4, pady=3)
    folder_button = _make_button(input_frame, text="选择文件夹", command=select_folder,
                                width=140 if USE_CTK else 14, font=("微软雅黑", 11))
    folder_button.grid(row=0, column=1, padx=4, pady=3)
    recursive_var = tk.BooleanVar(value=False)
    if USE_CTK:
        recursive_check = ctk.CTkCheckBox(input_frame, text="包含子文件夹", variable=recursive_var)
    else:
        recursive_check = ttk.Checkbutton(input_frame, text="包含子文件夹", variable=recursive_var)
    recursive_check.grid(row=0, column=2, padx=4, pady=3, sticky="w")
    operation_widgets.extend([file_button, folder_button, recursive_check])

    # ---- 阈值输入 ----
    threshold_frame = _make_frame(main_frame)
    threshold_frame.pack(pady=3)
    _make_label(threshold_frame, text="异常金额阈值:", font=("微软雅黑", 9)).pack(
        side="left", padx=(0, 5))
    threshold_entry = _make_entry(threshold_frame, width=100, font=("微软雅黑", 10))
    threshold_entry.pack(side="left")
    threshold_entry.insert(0, "10000")
    operation_widgets.append(threshold_entry)

    # 两项都默认关闭，开始处理时按实际列显示设置。
    time_screen_var = tk.BooleanVar(value=False)
    split_screen_var = tk.BooleanVar(value=False)
    optional_frame = _make_frame(main_frame)
    optional_frame.pack(fill="x", padx=8, pady=3)
    if USE_CTK:
        time_check = ctk.CTkCheckBox(optional_frame, text="按入账时间筛选（夜间、周末、节假日）", variable=time_screen_var)
        split_check = ctk.CTkCheckBox(optional_frame, text="疑似拆分审批筛选", variable=split_screen_var)
    else:
        time_check = ttk.Checkbutton(optional_frame, text="按入账时间筛选（夜间、周末、节假日）", variable=time_screen_var)
        split_check = ttk.Checkbutton(optional_frame, text="疑似拆分审批筛选", variable=split_screen_var)
    time_check.pack(anchor="w", pady=2)
    split_check.pack(anchor="w", pady=2)
    operation_widgets.extend([time_check, split_check])

    # ---- 常驻执行区 ----
    execution_frame = _make_frame(main_frame)
    execution_frame.pack(fill="x", padx=8, pady=6)
    start_button = _make_button(
        execution_frame, text="开始处理", command=begin_processing,
        width=150 if USE_CTK else 14, font=("微软雅黑", 14, "bold"), state="disabled")
    start_button.pack(side="left", padx=4)
    stop_button = _make_button(
        execution_frame, text="停止处理", command=stop_processing,
        width=130 if USE_CTK else 12, font=("微软雅黑", 13), state="disabled")
    stop_button.pack(side="left", padx=4)

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
                function, args, response = ui_requests.get_nowait()
                try:
                    value = function(*args)
                    if response is not None:
                        response.put((True, value))
                except Exception as exc:
                    if response is not None:
                        response.put((False, exc))
                    else:
                        print(f"界面更新失败: {exc}")
        except queue.Empty:
            pass
        try:
            while True:
                msg_type, percent, message, phase = GUI_PROGRESS.msg_queue.get_nowait()
                if msg_type == "update":
                    # 完成提示已显示时，忽略排队中的旧进度消息。
                    if not progress_active[0]:
                        continue
                    progress_label.configure(text="正在停止：等待当前文件完成并保存..."
                                             if stop_event.is_set() else message)
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

    app.after(100, check_queue)

    # ---- 版本号 ----
    _make_label(main_frame, text="v2.3.0", font=("微软雅黑", 8),
                text_color="gray").pack(side="bottom", pady=(0, 2))

    def close_window():
        if busy[0]:
            CustomMessageBox.showwarning("正在处理", "请等待本次处理完成后再关闭窗口", parent=app)
        else:
            app.destroy()
    app.protocol("WM_DELETE_WINDOW", close_window)
    app.mainloop()

    # 恢复标准输出
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

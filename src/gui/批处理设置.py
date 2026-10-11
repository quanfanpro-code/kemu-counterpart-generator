"""为新列名格式配置一次对应关系，相同格式在本批次复用。"""
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from .widgets import wait_modal_dialog, ctk


class BatchMappingDialog(tk.Toplevel):
    def __init__(self, parent, columns, required, *, title=None, hint=None):
        super().__init__(parent)
        self.title(title or "本批次新格式：请确认列名对应")
        self.transient(parent)
        self.result = None
        self.choices = {}
        # 普通 Tk 弹窗不沿用 CTk 控件缩放，显式按父窗口比例设置像素字号。
        scale = (ctk.ScalingTracker.get_widget_scaling(parent) if ctk and isinstance(parent, ctk.CTk)
                 else float(self.tk.call("tk", "scaling")) * 1.25)
        self.mapping_font = tkfont.Font(root=self, family="微软雅黑", size=-round(16 * scale))
        style = ttk.Style(self)
        style.configure("Mapping.TLabel", font=self.mapping_font)
        style.configure("Mapping.TCombobox", font=self.mapping_font, padding=round(5 * scale))
        style.configure("Mapping.TButton", font=self.mapping_font, padding=round(6 * scale))
        self.option_add("*TCombobox*Listbox.font", self.mapping_font)
        body = ttk.Frame(self, padding=round(12 * scale))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, style="Mapping.TLabel", wraplength=round(450 * scale),
                  text=hint or "相同列名格式只设置一次；取消后该格式记为失败，其他文件继续。").grid(
            row=0, column=0, columnspan=2, pady=(0, 8))
        for index, name in enumerate(required, 1):
            ttk.Label(body, text=name, style="Mapping.TLabel").grid(
                row=index, column=0, sticky="w", padx=(0, round(12 * scale)), pady=round(6 * scale))
            values = ["无/不适用"] + list(columns) if name == "凭证种类" else list(columns)
            var = tk.StringVar(value=name if name in columns else
                               "无/不适用" if name == "凭证种类" else "")
            ttk.Combobox(body, textvariable=var, values=values, state="readonly", width=28,
                         font=self.mapping_font, style="Mapping.TCombobox").grid(
                row=index, column=1, sticky="ew", pady=round(6 * scale))
            self.choices[name] = var
        self.status = ttk.Label(body, text="", style="Mapping.TLabel")
        self.status.grid(row=len(required) + 1, column=0, columnspan=2)
        actions = ttk.Frame(body)
        actions.grid(row=len(required) + 2, column=0, columnspan=2, sticky="e")
        ttk.Button(actions, text="取消" if title else "取消此格式", style="Mapping.TButton",
                   command=self.destroy).pack(side="left", padx=4)
        ttk.Button(actions, text="确认映射" if title else "确认并继续", style="Mapping.TButton",
                   command=self.accept).pack(side="left", padx=4)

    def accept(self):
        mapping = {name: var.get() for name, var in self.choices.items()}
        selected = [value for value in mapping.values() if value != "无/不适用"]
        if any(not value for value in selected):
            self.status.configure(text="请为每个必要字段选择对应列")
            return
        if len(set(selected)) != len(selected):
            self.status.configure(text="同一原始列不能对应多个字段")
            return
        self.result = mapping
        self.destroy()


def ask_batch_mapping(parent, columns, required, **kwargs):
    dialog = BatchMappingDialog(parent, columns, required, **kwargs)
    wait_modal_dialog(parent, dialog)
    return dialog.result

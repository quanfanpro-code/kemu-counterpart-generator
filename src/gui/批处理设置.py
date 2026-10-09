"""为新列名格式配置一次对应关系，相同格式在本批次复用。"""
import tkinter as tk
from tkinter import ttk

from .widgets import wait_modal_dialog


class BatchMappingDialog(tk.Toplevel):
    def __init__(self, parent, columns, required):
        super().__init__(parent)
        self.title("本批次新格式：请确认列名对应")
        self.transient(parent)
        self.result = None
        self.choices = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="相同列名格式只设置一次；取消后该格式记为失败，其他文件继续。").grid(
            row=0, column=0, columnspan=2, pady=(0, 8))
        for index, name in enumerate(required, 1):
            ttk.Label(body, text=name).grid(row=index, column=0, sticky="w", pady=3)
            values = ["无/不适用"] + list(columns) if name == "凭证种类" else list(columns)
            var = tk.StringVar(value=name if name in columns else
                               "无/不适用" if name == "凭证种类" else "")
            ttk.Combobox(body, textvariable=var, values=values, state="readonly", width=35).grid(
                row=index, column=1, sticky="ew", pady=3)
            self.choices[name] = var
        self.status = ttk.Label(body, text="")
        self.status.grid(row=len(required) + 1, column=0, columnspan=2)
        actions = ttk.Frame(body)
        actions.grid(row=len(required) + 2, column=0, columnspan=2, sticky="e")
        ttk.Button(actions, text="取消此格式", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(actions, text="确认并继续", command=self.accept).pack(side="left", padx=4)

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


def ask_batch_mapping(parent, columns, required):
    dialog = BatchMappingDialog(parent, columns, required)
    wait_modal_dialog(parent, dialog)
    return dialog.result

"""按需显示筛选设置。选择文件之后，直接用该文件的列和科目供用户选择。"""
import threading
import tkinter as tk
from tkinter import ttk

from src.日历 import update_calendar


class ScreeningDialog(tk.Toplevel):
    def __init__(self, parent, df, time_enabled, split_enabled):
        super().__init__(parent)
        self.title("本次凭证筛选")
        self.resizable(True, True)
        self.result = None
        self.df = df
        self.time_enabled, self.split_enabled = time_enabled, split_enabled
        self.vars = {}
        self.subjects = None
        self.transient(parent)
        body=ttk.Frame(self,padding=12)
        body.pack(fill="both",expand=True)
        columns=[str(c) for c in df.columns]
        def choice(frame,key,label,values,default=""):
            row=ttk.Frame(frame);row.pack(fill="x",pady=3)
            ttk.Label(row,text=label,width=22).pack(side="left")
            var=tk.StringVar(value=default)
            box=ttk.Combobox(row,textvariable=var,values=values,state="readonly",width=36)
            box.pack(side="left",fill="x",expand=True)
            self.vars[key]=var
            return box
        def entry(frame,key,label,value=""):
            row=ttk.Frame(frame);row.pack(fill="x",pady=3)
            ttk.Label(row,text=label,width=22).pack(side="left")
            var=tk.StringVar(value=value);self.vars[key]=var
            ttk.Entry(row,textvariable=var,width=20).pack(side="left")
        def toggle(frame,key,label,value):
            var=tk.BooleanVar(value=value);self.vars[key]=var
            ttk.Checkbutton(frame,text=label,variable=var).pack(anchor="w",pady=2)
        if time_enabled:
            group=ttk.LabelFrame(body,text="按入账时间筛选",padding=8);group.pack(fill="x",pady=4)
            choice(group,"date","账里哪一列是日期或时间",columns)
            toggle(group,"weekend","普通周末，排除调休补班",True)
            toggle(group,"holiday","法定节假日和调休放假",True)
            toggle(group,"night","正常工作时段以外",True)
            entry(group,"start","正常工作开始时间","08:00")
            entry(group,"end","正常工作结束时间","18:00")
            ttk.Label(group,text="只有日期、没有真实时分秒时，不查夜间。").pack(anchor="w")
            ttk.Button(group,text="更新放假调休日历",command=self.refresh_calendar).pack(anchor="w",pady=4)
        if split_enabled:
            group=ttk.LabelFrame(body,text="疑似拆分审批筛选",padding=8);group.pack(fill="x",pady=4)
            ttk.Label(group,text="例如查银行付款，选银行存款和贷方，读取原始付款金额。").pack(anchor="w")
            suggested=next((x for x in ("一级科目","科目名称","科目编号") if x in columns),"")
            box=choice(group,"subject_column","科目在哪一列",columns,suggested)
            ttk.Label(group,text="选择要查的科目，可以多选").pack(anchor="w")
            list_frame=ttk.Frame(group);list_frame.pack(fill="x")
            self.subjects=tk.Listbox(list_frame,selectmode="extended",exportselection=False,height=5)
            self.subjects.pack(side="left",fill="x",expand=True)
            scroll=ttk.Scrollbar(list_frame,command=self.subjects.yview);scroll.pack(side="right",fill="y")
            self.subjects.configure(yscrollcommand=scroll.set)
            box.bind("<<ComboboxSelected>>",lambda _:self.refresh_subjects())
            self.refresh_subjects()
            choice(group,"direction","读取哪个方向的金额",["借方","贷方"])
            entry(group,"limit","审批限额")
            entry(group,"minimum","接近限额的最低金额")
            choice(group,"split_date","按哪一列日期归集",["不归集"]+columns,"不归集")
            choice(group,"party","交易对方在哪一列",["不归集"]+columns,"不归集")
            ttk.Label(group,text="选了日期和对方后，将同账套、同日、同对方的候选放在一起。").pack(anchor="w")
        self.status=ttk.Label(body,text="");self.status.pack(fill="x",pady=3)
        actions=ttk.Frame(body);actions.pack(fill="x")
        ttk.Button(actions,text="开始处理",command=self.accept).pack(side="right",padx=4)
        ttk.Button(actions,text="本次只做原有分析",command=self.skip).pack(side="right",padx=4)
        ttk.Button(actions,text="取消",command=self.destroy).pack(side="right",padx=4)

    def refresh_subjects(self):
        self.subjects.delete(0,"end")
        col=self.vars["subject_column"].get()
        if col in self.df:
            for value in sorted(set(self.df[col].dropna().astype(str).str.strip())-{""}):
                self.subjects.insert("end",value)

    def options(self):
        result={}
        if self.time_enabled:
            result["time"]={key:self.vars[var].get() for key,var in
                           (("column","date"),("night","night"),("weekend","weekend"),("holiday","holiday"),("start","start"),("end","end"))}
        if self.split_enabled:
            result["split"]={key:self.vars[var].get() for key,var in
                            (("subject_column","subject_column"),("direction","direction"),("limit","limit"),
                             ("minimum","minimum"),("date_column","split_date"),("party_column","party"))}
            result["split"]["subjects"]=[self.subjects.get(i) for i in self.subjects.curselection()]
        return result

    def accept(self):
        from datetime import time
        from decimal import Decimal, InvalidOperation
        options=self.options()
        if "time" in options:
            opt=options["time"]
            try:
                if not opt["column"] or not any(opt[k] for k in ("night","holiday","weekend")):
                    raise ValueError("请选择日期列和至少一种时间条件")
                if opt["night"]:
                    start, end = time.fromisoformat(opt["start"]), time.fromisoformat(opt["end"])
                    if start == end:
                        raise ValueError("正常工作时间的起止不能相同")
            except ValueError as exc:
                self.status.configure(text=f"请检查时间设置 {exc}");return
        if "split" in options:
            opt=options["split"]
            try:
                lo,hi=Decimal(opt["minimum"]),Decimal(opt["limit"])
                if not lo.is_finite() or not hi.is_finite() or not 0<lo<hi or not opt["subjects"] or not opt["direction"]:
                    raise ValueError()
            except (InvalidOperation,ValueError):
                self.status.configure(text="请选择科目和借贷方向，并填写正数金额，最低金额须小于审批限额");return
        self.result=options
        self.destroy()

    def skip(self):
        self.result={}
        self.destroy()

    def refresh_calendar(self):
        self.status.configure(text="正在读取项目提供的日历更新")
        def worker():
            try:
                years=update_calendar()
                message="日历已更新，包含 "+ "、".join(years)+" 年"
            except Exception as exc:
                message=f"更新未成功，保留现有日历 {exc}"
            try:
                self.after(0,lambda:self.status.configure(text=message))
            except (RuntimeError, tk.TclError):
                pass
        threading.Thread(target=worker,daemon=True).start()


def ask_screening_options(parent,df,time_enabled,split_enabled):
    if not time_enabled and not split_enabled:
        return {}
    dialog=ScreeningDialog(parent,df,time_enabled,split_enabled)
    dialog.grab_set()
    parent.wait_window(dialog)
    return dialog.result

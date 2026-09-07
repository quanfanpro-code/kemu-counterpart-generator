from datetime import date, datetime
from decimal import Decimal
import subprocess
import sys
from pathlib import Path

import pandas as pd


def frame():
    return pd.DataFrame([
        {"账套":"甲", "会计月":"2026-01", "凭证种类":"记", "凭证编号":str(i+1),
         "一级科目":"银行存款", "借方发生额":0, "贷方发生额":98000,
         "记账时间":d, "对方单位":"供应商甲"}
        for i,d in enumerate(["2026-01-02 10:00:00", "2026-01-04 10:00:00", "2026-01-04 23:00:00", "2026-01-10"])
    ])


def test_默认关闭不增加输出():
    from src.pipeline.凭证筛选 import run_screening
    assert run_screening(frame(), None) == {}


def test_节假日补班夜间分别判断():
    from src.pipeline.凭证筛选 import run_screening
    df=frame()
    sheets=run_screening(df, {"time":{"column":"记账时间", "weekend":True, "holiday":True, "night":True, "start":"08:00", "end":"18:00"}})
    out=sheets["入账时间筛选"]
    assert list(out["凭证编号"]) == ["1","3","4"]
    assert "夜间" not in out.loc[out["凭证编号"]=="4","筛选原因"].iloc[0]
    assert "夜间" in out.loc[out["凭证编号"]=="3","筛选原因"].iloc[0]
    assert "未提供真实时分秒" in str(sheets["筛选说明"].to_dict())


def test_跨年与缺失年份不能写成没有发现():
    from src.pipeline.凭证筛选 import run_screening
    df=frame()
    df["记账时间"]=["2025-01-26","2025-01-29","2026-01-02","2030-01-01"]
    sheets=run_screening(df, {"time":{"column":"记账时间","holiday":True,"weekend":True}})
    assert list(sheets["入账时间筛选"]["凭证编号"]) == ["2","3"]
    assert "2030" in str(sheets["筛选说明"].to_dict())


def test_金额只取所选方向且不串账套():
    from src.pipeline.凭证筛选 import run_screening
    df=frame()
    df["记账时间"]="2026-01-05"
    df.loc[2,"账套"]="乙"
    df.loc[3,"贷方发生额"]=-98000
    debit=df.iloc[[0]].copy()
    debit["一级科目"]="应付账款"
    debit["借方发生额"]=98000
    debit["贷方发生额"]=0
    df=pd.concat([df,debit],ignore_index=True)
    df.attrs["ledger_column"]="账套"
    opts={"split":{"subject_column":"一级科目","subjects":["银行存款"],"direction":"贷方",
                  "limit":"100000","minimum":"90000","date_column":"记账时间","party_column":"对方单位"}}
    result=run_screening(df,opts)
    out=result["拆分审批筛选"]
    assert len(out)==3
    assert list(out["筛选金额"]) == [Decimal("98000")]*3
    assert list(out["同组金额"])[:2] == [Decimal("196000")]*2
    assert out.iloc[2]["同组金额"] == Decimal("98000")
    assert "红字" in str(result["筛选说明"].to_dict())


def test_无对方只能金额候选_参数不全也不影响其他功能():
    from src.pipeline.凭证筛选 import run_screening
    opts={"split":{"subject_column":"一级科目","subjects":["银行存款"],"direction":"贷方",
                  "limit":"100000","minimum":"90000"}}
    result=run_screening(frame(),opts)
    assert all(result["拆分审批筛选"]["同组金额"].isna())
    result=run_screening(frame(),{"time":{"column":"不存在","holiday":True},**opts})
    assert len(result["拆分审批筛选"])==4
    assert "不存在" in str(result["筛选说明"].to_dict())


def test_真实Excel日期单元格不当午夜(tmp_path):
    from openpyxl import Workbook
    from src.io.reader import load_and_preprocess_data
    from src.pipeline.凭证筛选 import run_screening
    p=tmp_path/"日期样例.xlsx"
    w=Workbook();s=w.active
    s.append(["会计月","凭证种类","凭证编号","一级科目","借方发生额","贷方发生额","时间"])
    for i in range(3):
        s.append(["2026-01","记",str(i),"银行存款",1,0,datetime(2026,1,5)])
    s["G2"].number_format="yyyy-mm-dd"
    s["G3"].number_format="yyyy-mm-dd hh:mm:ss"
    s["G4"].number_format="[$-zh-CN]yyyy-mm-dd"
    w.save(p)
    df=load_and_preprocess_data(str(p))
    assert df.attrs["source_sheet"] == "Sheet"
    out=run_screening(df,{"time":{"column":"时间","night":True,"start":"08:00","end":"18:00"}})
    assert list(out["入账时间筛选"]["凭证编号"].astype(str))==["1"]


def test_主入口和独立命令行均输出可选表(tmp_path):
    root=Path(__file__).resolve().parents[1]
    df=frame()
    df["借方发生额"]=df["贷方发生额"]
    inp=tmp_path/"输入.xlsx";df.to_excel(inp,index=False)
    for entry,extra in [("main.py",[]),("cli/序时账分析器命令行版.py",["--mode","summary"])]:
        out=tmp_path/(Path(entry).stem+".xlsx")
        result=subprocess.run([sys.executable,'-X','utf8',str(root/entry),str(inp),str(out),*extra,
            "--screen-date","记账时间","--screen-holiday","--screen-weekend"],cwd=root,capture_output=True,text=True,encoding="utf-8")
        assert result.returncode==0,result.stderr
        book=pd.ExcelFile(out)
        assert "入账时间筛选" in book.sheet_names

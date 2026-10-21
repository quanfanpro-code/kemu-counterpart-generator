# -*- coding: utf-8 -*-
"""图表随一次成型写入生成，全程不再经过 openpyxl 保存。"""
import openpyxl
import pandas as pd
from openpyxl import load_workbook
from make_excel import make_excel


def test_图表字段一次成型生成折线图(tmp_path, monkeypatch):
    original_save = openpyxl.Workbook.save
    saves = []

    def track_save(book, path):
        saves.append(path)
        return original_save(book, path)

    monkeypatch.setattr(openpyxl.Workbook, 'save', track_save)

    stats = pd.DataFrame({
        "首位数": list(range(1, 10)),
        "出现次数": [10, 8, 6, 5, 4, 3, 3, 2, 2],
        "出现比率": [0.244, 0.195, 0.146, 0.122, 0.098, 0.073, 0.073, 0.049, 0.049],
        "班福比率": [0.301, 0.176, 0.125, 0.097, 0.079, 0.067, 0.058, 0.051, 0.046],
    })

    def 加图(plans):
        for tp in plans:
            if tp.名称 == "班福分析":
                tp.图表 = [{"类型": "折线", "位置": "H2",
                            "标题": "班福定律分析 - 首位数分布",
                            "X轴标题": "首位数", "Y轴标题": "比率",
                            "分类引用": "'班福分析'!B2:B10",
                            "系列": ["'班福分析'!D1:D10", "'班福分析'!E1:E10"]}]

    out = make_excel([("班福分析", stats)], str(tmp_path / "o.xlsx"), postprocess=加图)
    assert saves == []                     # 全程无 openpyxl 保存
    book = load_workbook(out)
    charts = book["班福分析"]._charts
    assert len(charts) == 1 and charts[0].tagname == "lineChart"
    book.close()

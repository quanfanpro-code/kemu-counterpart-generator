"""大型结果的图表应在首次保存前加入。"""

import openpyxl
import pandas as pd
import pytest

from src.io import writer


def test_图表排版只保存一次(tmp_path, monkeypatch):
    """输出全程不经过 openpyxl 保存，图表随一次成型写入生成。"""
    original_save = openpyxl.Workbook.save
    saves = []

    def track_save(book, path):
        saves.append(path)
        return original_save(book, path)

    monkeypatch.setattr(openpyxl.Workbook, "save", track_save)
    rows = pd.DataFrame({"记账时间": ["2025-01-01"], "科目名称": ["现金"]})
    stats = pd.DataFrame({
        "首位数": range(1, 10),
        "出现次数": [10] * 9,
        "出现比率": [0.1] * 9,
        "班福比率": [0.1] * 9,
    })
    target = tmp_path / "结果.xlsx"
    assert writer.save_output_file(
        str(target), rows, rows, pd.DataFrame(), pd.DataFrame(), stats, []
    )
    assert saves == []
    book = openpyxl.load_workbook(target)
    assert len(book["班福分析"]._charts) == 1
    book.close()

# -*- coding: utf-8 -*-
"""容差配对不改写原行金额、零头单独成行的金额守恒验收。"""
import pandas as pd

from src.pipeline.group_processor import GroupProcessor, process_group

KEY = ("2026-01", "记", "1")


def _凭证(行):
    return pd.DataFrame(行, columns=["一级科目", "借方发生额", "贷方发生额", "摘要"])


def _合计(rows):
    借 = sum(r["借方发生额"] for r in rows)
    贷 = sum(r["贷方发生额"] for r in rows)
    return round(借, 2), round(贷, 2)


def test_一对容差配对保留原金额():
    source = _凭证([
        ("应收账款", 0.58, 0, "销售"),
        ("主营业务收入", 0, 0.57, "销售"),
    ])
    rows, warnings = process_group((KEY, source))
    assert warnings == []
    金额 = sorted((r["借方发生额"], r["贷方发生额"]) for r in rows)
    assert 金额 == [(0.0, 0.57), (0.58, 0.0)]
    assert {r["对方科目"] for r in rows} == {"主营业务收入", "应收账款"}
    assert _合计(rows) == (0.58, 0.57)


def test_尾差行单独成行():
    source = _凭证([
        ("应收账款", 0.58, 0, "销售"),
        ("主营业务收入", 0, 0.57, "销售"),
    ])
    processor = GroupProcessor((KEY, source))
    processor._prepare_data()
    item = processor.debit_items[0]
    processor._append_tail_row(item, 0.01)
    assert len(processor.output_rows) == 1
    尾差 = processor.output_rows[0]
    assert 尾差["借方发生额"] == 0.01 and 尾差["贷方发生额"] == 0
    assert 尾差["对方科目"] == "未找到匹配"
    assert 尾差["匹配类型"] == "容差调整"


def test_凑数凭证金额守恒():
    source = _凭证([
        ("无形资产", 40, 0, "购入"),
        ("无形资产", 59.99, 0, "购入"),
        ("无形资产", 0.01, 0, "购入"),
        ("长期借款", 0, 100, "购入"),
    ])
    rows, warnings = process_group((KEY, source))
    assert _合计(rows) == (100.0, 100.0)
    输入合计 = 40 + 59.99 + 0.01 + 100
    输出合计 = sum(
        r["借方发生额"] if r["借方发生额"] else r["贷方发生额"] for r in rows)
    assert round(输出合计, 2) == round(输入合计, 2)

"""摘要明确引用原凭证时，逐行核对后隔开冲销和新业务。"""

import pandas as pd
import pytest

from src.pipeline.orchestrator import perform_processing
from src.pipeline.group_processor import process_group
from src.pipeline import orchestrator


def 样例账():
    rows = [
        ("2026-02-01", "7", "旧业务", "甲", "1001", 100, 0),
        ("2026-02-01", "7", "旧业务", "乙", "2001", 0, 100),
        ("2026-07-01", "2", "[冲销2026.02.01 记-0007号凭证]旧业务", "甲", "1001", -100, 0),
        ("2026-07-01", "2", "新业务", "丙", "3001", 100, 0),
        ("2026-07-01", "2", "[冲销2026.02.01 记-0007号凭证]旧业务", "乙", "2001", 0, -100),
        ("2026-07-01", "2", "新业务", "丁", "4001", 0, 100),
    ]
    return pd.DataFrame(rows, columns=[
        "会计月", "凭证编号", "业务说明", "一级科目", "科目编号", "借方发生额", "贷方发生额",
    ]).assign(凭证种类="记")


def test_引用原凭证的冲销分录与同凭证新业务分开():
    source = 样例账()
    result, failed = perform_processing(source)

    assert failed == []
    assert list(result.loc[result["一级科目"] == "甲", "对方科目"]) == ["乙", "乙"]
    assert list(result.loc[result["一级科目"] == "乙", "对方科目"]) == ["甲", "甲"]
    assert result.loc[result["一级科目"] == "丙", "对方科目"].tolist() == ["丁"]
    assert result.loc[result["一级科目"] == "丁", "对方科目"].tolist() == ["丙"]
    assert set(result.loc[result["业务说明"].str.startswith("[冲销"), "匹配类型"]) == {"原凭证冲销"}
    assert result["借方发生额"].sum() == source["借方发生额"].sum()
    assert result["贷方发生额"].sum() == source["贷方发生额"].sum()


def test_原行拆成两笔时冲销行也逐笔反向且总额不变():
    rows = [
        ("2026-02-01", "7", "旧业务", "甲", "1001", 100, 0),
        ("2026-02-01", "7", "旧业务", "乙", "2001", 0, 60),
        ("2026-02-01", "7", "旧业务", "丙", "3001", 0, 40),
        ("2026-07-01", "2", "[冲销2026.02.01 记-0007号凭证]旧业务", "甲", "1001", -100, 0),
        ("2026-07-01", "2", "新业务", "丁", "4001", 100, 0),
        ("2026-07-01", "2", "[冲销2026.02.01 记-0007号凭证]旧业务", "乙", "2001", 0, -60),
        ("2026-07-01", "2", "新业务", "戊", "5001", 0, 100),
        ("2026-07-01", "2", "[冲销2026.02.01 记-0007号凭证]旧业务", "丙", "3001", 0, -40),
    ]
    source = pd.DataFrame(rows, columns=[
        "会计月", "凭证编号", "业务说明", "一级科目", "科目编号", "借方发生额", "贷方发生额",
    ]).assign(凭证种类="记")
    result, failed = perform_processing(source)
    assert failed == []
    reverse = result[result["业务说明"].str.startswith("[冲销")]
    assert sorted(zip(reverse.loc[reverse["一级科目"] == "甲", "对方科目"],
                      reverse.loc[reverse["一级科目"] == "甲", "借方发生额"])) == [
                          ("丙", -40), ("乙", -60)]
    assert reverse["借方发生额"].sum() == -100
    assert reverse["贷方发生额"].sum() == -100
    assert result.loc[result["一级科目"] == "丁", "对方科目"].tolist() == ["戊"]


def test_有冲销引用时串行与多进程结果相同(monkeypatch):
    source = 样例账()
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 10)
    serial, serial_failed = perform_processing(source)
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 1)
    monkeypatch.setattr(orchestrator.os, "cpu_count", lambda: 2)
    parallel, parallel_failed = perform_processing(source)
    assert serial_failed == parallel_failed == []
    pd.testing.assert_frame_equal(serial, parallel)


def test_结转损益原有最高优先级不受冲销反查影响():
    source = 样例账()
    extra = pd.DataFrame([
        {"会计月": "2026-07-01", "凭证编号": "2", "凭证种类": "记", "业务说明": "结转",
         "一级科目": "本年利润", "科目编号": "4103", "借方发生额": 50, "贷方发生额": 0},
        {"会计月": "2026-07-01", "凭证编号": "2", "凭证种类": "记", "业务说明": "结转",
         "一级科目": "主营业务收入", "科目编号": "6001", "借方发生额": 0, "贷方发生额": 50},
    ])
    source = pd.concat([source, extra], ignore_index=True)
    target = source[source["凭证编号"] == "2"]
    expected, _ = process_group((("2026-07-01", "记", "2"), target))
    result, failed = perform_processing(source)
    assert failed == []
    actual = result[result["凭证编号"] == "2"]
    assert sorted((r["一级科目"], r["对方科目"], r["匹配类型"]) for r in actual.to_dict("records")) == sorted(
        (r["一级科目"], r["对方科目"], r["匹配类型"]) for r in expected)


@pytest.mark.parametrize("change", ["日期", "摘要", "科目", "一级科目", "缺一级科目", "金额", "缺明细科目", "重复原行"])
def test_原凭证不能唯一核对时保持原流程(change):
    source = 样例账()
    if change == "日期":
        source.loc[0:1, "会计月"] = "2026-02"
    elif change == "摘要":
        source.loc[2, "业务说明"] = "[冲销2026.02.01 记-0007号凭证]另一业务"
    elif change == "科目":
        source.loc[0, "科目编号"] = "9999"
    elif change == "一级科目":
        source.loc[2, "一级科目"] = "另一科目"
    elif change == "缺一级科目":
        source.loc[2, "一级科目"] = ""
    elif change == "金额":
        source.loc[2, "借方发生额"] = -99
    elif change == "缺明细科目":
        source = source.drop(columns="科目编号")
    else:
        source = pd.concat([source, source.iloc[[0]].assign(一级科目="甲", 科目编号="1001"),
                            source.iloc[[1]].assign(一级科目="戊", 科目编号="5001")], ignore_index=True)
    result, failed = perform_processing(source)
    assert failed == []
    assert "原凭证冲销" not in set(result["匹配类型"])
    target = source[source["凭证编号"] == "2"]
    expected, _ = process_group((("2026-07-01", "记", "2"), target))
    columns = ("一级科目", "借方发生额", "贷方发生额", "对方科目", "匹配类型")
    def values(row):
        return tuple(None if pd.isna(row[column]) else row[column] for column in columns)
    assert sorted(values(row) for row in expected) == sorted(
        values(row) for row in result[result["凭证编号"] == "2"].to_dict("records"))


def test_摘要和业务说明同时记录相同引用也能核对():
    source = 样例账()
    source["摘要"] = source["业务说明"]
    result, failed = perform_processing(source)
    assert failed == []
    assert set(result.loc[result["业务说明"].str.startswith("[冲销"), "匹配类型"]) == {"原凭证冲销"}


def test_同一凭证另有查不实的冲销时整张保留原处理():
    source = 样例账()
    extra = pd.DataFrame([
        {"会计月": "2026-07-01", "凭证编号": "2", "凭证种类": "记",
         "业务说明": "[冲销2026.02.01 记-0099号凭证]另一旧业务",
         "一级科目": "戊", "科目编号": "5001", "借方发生额": -50, "贷方发生额": 0},
        {"会计月": "2026-07-01", "凭证编号": "2", "凭证种类": "记",
         "业务说明": "[冲销2026.02.01 记-0099号凭证]另一旧业务",
         "一级科目": "己", "科目编号": "6001", "借方发生额": 0, "贷方发生额": -50},
    ])
    result, failed = perform_processing(pd.concat([source, extra], ignore_index=True))
    assert failed == []
    assert "原凭证冲销" not in set(result["匹配类型"])


def test_不同账套的同号凭证不能作为原凭证():
    source = 样例账()
    source["账套"] = ["甲公司", "甲公司", "乙公司", "乙公司", "乙公司", "乙公司"]
    source.attrs["ledger_column"] = "账套"
    result, failed = perform_processing(source)
    assert failed == []
    assert "原凭证冲销" not in set(result["匹配类型"])

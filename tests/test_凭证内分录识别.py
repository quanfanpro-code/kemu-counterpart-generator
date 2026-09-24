"""凭证内多笔分录识别的行为验收。"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.group_processor import GroupProcessor, process_group
from src.pipeline.orchestrator import perform_processing
from src.pipeline import orchestrator


VOUCHER = ("2026-01", "记", "1")
ROOT = Path(__file__).resolve().parents[1]


def voucher(*entries):
    return pd.DataFrame([
        {
            "会计月": "2026-01",
            "凭证种类": "记",
            "凭证编号": "1",
            "一级科目": subject,
            "借方发生额": debit,
            "贷方发生额": credit,
        }
        for subject, debit, credit in entries
    ])


def subject_rows(rows, subject):
    return [row for row in rows if row["一级科目"] == subject]


def test_连续平衡的两笔分录不跨组匹配():
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60),
    )
    rows, warnings = process_group((VOUCHER, source))

    assert warnings == []
    assert {(r["对方科目"], r["借方发生额"]) for r in subject_rows(rows, "甲")} == {
        ("乙", 60), ("丙", 40),
    }
    assert [(r["对方科目"], r["借方发生额"]) for r in subject_rows(rows, "丁")] == [
        ("戊", 60),
    ]
    assert {(r["对方科目"], r["贷方发生额"]) for r in subject_rows(rows, "乙")} == {
        ("甲", 60),
    }
    assert sum(r["借方发生额"] for r in rows) == 160
    assert sum(r["贷方发生额"] for r in rows) == 160


def test_混合结转只处理所属的平衡分录():
    source = voucher(
        ("本年利润", 100, 0), ("主营业务收入", 0, 100),
        ("管理费用", 50, 0), ("银行存款", 0, 50),
    )
    rows, warnings = process_group((VOUCHER, source))

    assert warnings == []
    assert [r["对方科目"] for r in subject_rows(rows, "本年利润")] == ["主营业务收入"]
    assert [r["对方科目"] for r in subject_rows(rows, "管理费用")] == ["银行存款"]
    assert [r["对方科目"] for r in subject_rows(rows, "银行存款")] == ["管理费用"]
    assert [r["对方科目"] for r in subject_rows(rows, "主营业务收入")] == ["本年利润"]
    assert subject_rows(rows, "本年利润")[0]["匹配类型"] == "结转损益规则(拆分)"


def test_多条利润科目继续由整凭证旧流程处理():
    source = voucher(
        ("本年利润", 100, 0), ("主营业务收入", 0, 100),
        ("利润分配", 60, 0), ("银行存款", 0, 60),
    )
    rows, warnings = process_group((VOUCHER, source))

    assert warnings == []
    assert [(r["一级科目"], r["对方科目"], r["匹配类型"]) for r in rows] == [
        ("本年利润", "主营业务收入", "算法生成"),
        ("主营业务收入", "本年利润", "算法生成"),
        ("利润分配", "银行存款", "算法生成"),
        ("银行存款", "利润分配", "算法生成"),
    ]


def test_纯损益结转仍按整凭证旧流程处理():
    source = voucher(
        ("本年利润", 150, 0), ("主营业务收入", 0, 100),
        ("其他业务收入", 0, 50),
    )
    assert process_group((VOUCHER, source)) == GroupProcessor((VOUCHER, source)).process()


def test_重复金额的连续分录不跨组():
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 100),
        ("丙", 100, 0), ("丁", 0, 100),
    )
    rows, warnings = process_group((VOUCHER, source))
    assert warnings == []
    assert [(r["一级科目"], r["对方科目"]) for r in rows] == [
        ("甲", "乙"), ("乙", "甲"), ("丙", "丁"), ("丁", "丙"),
    ]


def test_多借一贷的连续分录不跨组():
    source = voucher(
        ("甲", 60, 0), ("乙", 40, 0), ("丙", 0, 100),
        ("丁", 50, 0), ("戊", 0, 50),
    )
    rows, warnings = process_group((VOUCHER, source))
    assert warnings == []
    assert [r["对方科目"] for r in subject_rows(rows, "丁")] == ["戊"]
    assert {r["对方科目"] for r in subject_rows(rows, "丙")} == {"甲", "乙"}


@pytest.mark.parametrize("extra", [
    ("红字科目", -10, 0),
    ("同行借贷", 5, 5),
    ("", 5, 0),
    ("零金额", 0, 0),
])
def test_异常行整凭证保留旧处理结果(extra):
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60), extra,
    )
    expected = GroupProcessor((VOUCHER, source)).process()
    actual = process_group((VOUCHER, source))
    assert actual == expected


def test_含不平衡尾段时整凭证保留旧处理结果():
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 100),
        ("丙", 50, 0), ("丁", 0, 40),
    )
    assert process_group((VOUCHER, source)) == GroupProcessor((VOUCHER, source)).process()


def test_极小金额不能形成单边平衡分录组():
    source = voucher(
        ("极小金额", 0.00001, 0),
        ("甲", 100, 0), ("乙", 0, 100),
        ("丙", 50, 0), ("丁", 0, 50),
    )
    assert process_group((VOUCHER, source)) == GroupProcessor((VOUCHER, source)).process()


def test_文字形式的空科目不能参与新分组():
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60),
        ("nan", 5, 0), ("己", 0, 5),
    )
    assert process_group((VOUCHER, source)) == GroupProcessor((VOUCHER, source)).process()


def test_单笔复杂分录没有内部平衡边界时结果不变():
    source = voucher(
        ("甲", 100, 0), ("丙", 50, 0),
        ("乙", 0, 100), ("丁", 0, 50),
    )
    assert process_group((VOUCHER, source)) == GroupProcessor((VOUCHER, source)).process()


def test_结果按原始行次恢复且不丢金额():
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60),
    )
    result, failed = perform_processing(source)

    assert failed == []
    assert list(result["一级科目"]) == ["甲", "甲", "乙", "丙", "丁", "戊"]
    assert result["借方发生额"].sum() == source["借方发生额"].sum()
    assert result["贷方发生额"].sum() == source["贷方发生额"].sum()
    assert set(result.columns) == set(source.columns) | {"对方科目", "匹配类型"}


def test_串行和多进程生成同一结果(monkeypatch):
    sample = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60),
    )
    source = pd.concat([sample.assign(凭证编号=str(i)) for i in range(201)], ignore_index=True)
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 1000)
    serial, serial_failed = perform_processing(source)
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 200)
    monkeypatch.setattr(orchestrator.os, "cpu_count", lambda: 2)
    parallel, parallel_failed = perform_processing(source)

    assert serial_failed == parallel_failed == []
    pd.testing.assert_frame_equal(serial, parallel)


@pytest.mark.parametrize("entry,mode", [
    ("main.py", None),
    ("cli/序时账分析器命令行版.py", "summary"),
    ("cli/序时账分析器命令行版.py", "full"),
])
def test_真实命令行入口生成的对方科目不跨组(tmp_path, entry, mode):
    source = voucher(
        ("甲", 100, 0), ("乙", 0, 60), ("丙", 0, 40),
        ("丁", 60, 0), ("戊", 0, 60),
    )
    input_path = tmp_path / "输入.xlsx"
    output_path = tmp_path / "结果.xlsx"
    source.to_excel(input_path, index=False)
    command = [sys.executable, "-B", "-X", "utf8", str(ROOT / entry),
               str(input_path), str(output_path), "--log-level", "ERROR"]
    command += ["--mode", mode] if mode else ["--no-gui"]
    finished = subprocess.run(command, cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=90)

    assert finished.returncode == 0, finished.stderr
    assert output_path.is_file()
    with pd.ExcelFile(output_path) as book:
        assert "生成结果" in book.sheet_names
        assert ("班福分析" in book.sheet_names) == (mode != "summary")
        result = pd.read_excel(book, sheet_name="生成结果")
    assert list(result.loc[result["一级科目"] == "丁", "对方科目"]) == ["戊"]
    assert set(result.loc[result["一级科目"] == "甲", "对方科目"]) == {"乙", "丙"}
    assert result["借方发生额"].sum() == source["借方发生额"].sum()
    assert result["贷方发生额"].sum() == source["贷方发生额"].sum()

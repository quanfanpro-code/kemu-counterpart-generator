"""三维候选、金额硬条件及真实共同入口的验收。"""
from itertools import permutations
import pandas as pd
import pytest

from src.pipeline.group_processor import GroupProcessor, process_group, _split_contiguous_balanced_groups


KEY = ("2026-01", "记", "1")


def sample(sign=1):
    return pd.DataFrame([
        ("管理费用", 100 * sign, 0, "支付办公费"),
        ("库存商品", 0, 100 * sign, "结转销售成本"),
        ("主营业务成本", 100 * sign, 0, "结转销售成本"),
        ("银行存款", 0, 100 * sign, "支付办公费"),
    ], columns=["一级科目", "借方发生额", "贷方发生额", "摘要"])


def decision(source):
    from src.pipeline.分录判断 import choose_voucher_groups
    baseline = _split_contiguous_balanced_groups(GroupProcessor((KEY, source)), source)
    return choose_voucher_groups(source, baseline)


@pytest.mark.parametrize("sign", [1, -1])
def test_摘要和标准关系两票改正交错业务(sign):
    result = decision(sample(sign))
    assert result.groups == ((0, 3), (1, 2))
    assert result.complete and result.reason == "三维多数胜出"


def test_共同入口不再把办公费配库存商品():
    source = sample()
    rows, warnings = process_group((KEY, source))
    assert warnings == []
    assert {(r["一级科目"], r["对方科目"]) for r in rows} == {
        ("管理费用", "银行存款"), ("银行存款", "管理费用"),
        ("主营业务成本", "库存商品"), ("库存商品", "主营业务成本"),
    }
    for i in source.index:
        for col in ("借方发生额", "贷方发生额"):
            assert sum(r[col] for r in rows if r["_orig_idx"] == i) == source.loc[i, col]


def test_没有摘要标准票不足时仍保留连续分法():
    result = decision(sample().drop(columns="摘要"))
    assert result.groups == ((0, 1), (2, 3))


def test_全部同摘要不能额外投摘要支持票():
    source = sample().assign(摘要="本月业务")
    assert decision(source).groups == ((0, 1), (2, 3))


def test_多候选不能依赖遍历顺序():
    from src.pipeline.分录判断 import majority_winner
    scores = [(1, 0, 0), (0, 1, 1), (0.5, 0.5, 0.5)]
    for order in permutations(range(3)):
        winner = majority_winner([scores[i] for i in order])
        assert order[winner] == 1


@pytest.mark.parametrize("scores", [
    [(1, 0, 0), (0, 1, 0)],
    [(2, 1, 0), (0, 2, 1), (1, 0, 2)],
    [(1, 1, 1), (1, 1, 1)],
])
def test_平票或循环胜负没有胜出者(scores):
    from src.pipeline.分录判断 import majority_winner
    assert majority_winner(scores) is None


def test_标准科目伙伴存在但容量不够不能算整组标准():
    from src.pipeline.分录判断 import standard_group_supported
    rows = pd.DataFrame([
        ("管理费用", 20, 0), ("销售费用", 80, 0),
        ("银行存款", 0, 20), ("长期待摊费用", 0, 80),
    ], columns=["一级科目", "借方发生额", "贷方发生额"])
    assert not standard_group_supported(rows)


def test_标准关系需要重分配容量而非贪心选首个():
    from src.pipeline.分录判断 import standard_group_supported
    rows = pd.DataFrame([
        ("管理费用", 20, 0), ("销售费用", 80, 0),
        ("银行存款", 0, 80), ("长期待摊费用", 0, 20),
    ], columns=["一级科目", "借方发生额", "贷方发生额"])
    assert standard_group_supported(rows)


def test_不平衡即使摘要相同也不能拆():
    source = sample()
    source.loc[3, "贷方发生额"] = 99
    assert decision(source).groups is None


def test_重复业务搜索超预算仍保留连续分法():
    source = pd.concat([sample() for _ in range(4)], ignore_index=True)
    result = decision(source)
    assert not result.complete
    assert result.groups == tuple((i, i + 1) for i in range(0, 16, 2))


def test_只有摘要一票且无连续基线不强行采用交错分法():
    source = pd.DataFrame([
        ("甲", 100, 0, "支付办公费"), ("乙", 60, 0, "结转销售成本"),
        ("丙", 0, 100, "支付办公费"), ("丁", 0, 60, "结转销售成本"),
    ], columns=["一级科目", "借方发生额", "贷方发生额", "摘要"])
    assert decision(source).groups is None


def test_借方集中排列但摘要和标准关系支持可拆():
    source = sample().iloc[[0, 2, 1, 3]].reset_index(drop=True)
    assert decision(source).groups == ((0, 3), (1, 2))


def test_科目判断仅依赖一级科目不受明细科目影响():
    source = sample().assign(科目名称="错误明细", 二级科目="任意内容")
    assert decision(source).groups == ((0, 3), (1, 2))


def test_摘要空白可使用业务说明():
    source = sample().rename(columns={"摘要": "业务说明"}).assign(摘要=" ")
    assert decision(source).groups == ((0, 3), (1, 2))


def test_缺失一整组摘要不把另一组摘要当全凭证支持():
    source = sample()
    source.loc[[1, 2], "摘要"] = ""
    assert decision(source).groups == ((0, 1), (2, 3))


def test_泛化摘要不同写法不让标准关系单票替换():
    source = sample().assign(摘要=["本期业务", "本月业务", "本月业务", "本期业务"])
    assert decision(source).groups == ((0, 1), (2, 3))


def test_摘要相似链不能绕过整组冲突():
    from src.pipeline import 分录判断 as module
    from src.core.摘要判断 import SummaryRelation
    source = pd.DataFrame([
        ("甲", 60, 0, "A"), ("乙", 40, 0, "B"), ("丙", 0, 100, "C"),
        ("丁", 50, 0, "D"), ("戊", 0, 50, "D"),
    ], columns=["一级科目", "借方发生额", "贷方发生额", "摘要"])
    from unittest.mock import patch
    def relation(a, b):
        if {a, b} == {"A", "C"}:
            return SummaryRelation(-1, True, True)
        return SummaryRelation(0.9, True)
    with patch.object(module, "compare_summaries", relation):
        result = decision(source)
    assert result.groups == ((0, 1, 2), (3, 4))
    assert len(result.candidates) == 2


def test_候选超界不从截断结果选多数(monkeypatch):
    from src.pipeline import 分录判断 as module
    monkeypatch.setattr(module, "MAX_PLANS", 1)
    result = decision(sample())
    assert not result.complete and result.groups == ((0, 1), (2, 3))


def test_新增判断异常保留原连续匹配(monkeypatch):
    from src.pipeline import 分录判断 as module
    def fail(*args):
        raise ValueError("测试异常")
    monkeypatch.setattr(module, "choose_voucher_groups", fail)
    rows, warnings = process_group((KEY, sample()))
    assert not warnings
    assert [r["对方科目"] for r in rows] == ["库存商品", "管理费用", "银行存款", "主营业务成本"]


def test_有摘要的201张凭证串行和多进程一致(monkeypatch):
    from src.pipeline import orchestrator
    source = pd.concat([
        sample().assign(会计月="2026-01", 凭证种类="记", 凭证编号=str(i))
        for i in range(201)
    ], ignore_index=True)
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 1000)
    serial, failed = orchestrator.perform_processing(source)
    monkeypatch.setattr(orchestrator, "SMALL_INPUT_SERIAL_THRESHOLD", 200)
    monkeypatch.setattr(orchestrator.os, "cpu_count", lambda: 2)
    parallel, other_failed = orchestrator.perform_processing(source)
    assert failed == other_failed == []
    pd.testing.assert_frame_equal(serial, parallel)
    assert set(serial.loc[serial["一级科目"] == "管理费用", "对方科目"]) == {"银行存款"}


@pytest.mark.parametrize("entry,mode", [
    ("main.py", None),
    ("cli\\序时账分析器命令行版.py", "summary"),
    ("cli\\序时账分析器命令行版.py", "full"),
])
def test_真实入口使用摘要三维判断(tmp_path, entry, mode):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source = sample().assign(会计月="2026-01", 凭证种类="记", 凭证编号="1")
    input_path, output_path = tmp_path / "摘要输入.xlsx", tmp_path / "摘要结果.xlsx"
    source.to_excel(input_path, index=False)
    command = [sys.executable, "-B", "-X", "utf8", str(root / entry),
               str(input_path), str(output_path), "--log-level", "ERROR"]
    command += ["--mode", mode] if mode else ["--no-gui"]
    finished = subprocess.run(command, cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=90)
    assert finished.returncode == 0, finished.stdout + finished.stderr
    with pd.ExcelFile(output_path) as book:
        result = pd.read_excel(book, sheet_name="生成结果")
        assert ("班福分析" in book.sheet_names) == (mode != "summary")
    assert list(result.loc[result["一级科目"] == "管理费用", "对方科目"]) == ["银行存款"]
    assert list(result.loc[result["一级科目"] == "主营业务成本", "对方科目"]) == ["库存商品"]
    expected = set(source.columns) | {"对方科目", "匹配类型"}
    # 主入口原有索引输出继续保留，独立命令行不输出索引。
    assert set(result.columns) == expected | ({"Unnamed: 0"} if mode is None else set())


def test_候选金额和原始行必须完整唯一覆盖():
    from src.core.precision import PrecisionEngine
    source = sample()
    result = decision(source)
    for plan in result.candidates:
        flattened = [i for part in plan for i in part]
        assert sorted(flattened) == list(range(len(source)))
        for part in plan:
            assert sum(PrecisionEngine.to_integer_li(source.iloc[i]["借方发生额"]) -
                       PrecisionEngine.to_integer_li(source.iloc[i]["贷方发生额"])
                       for i in part) == 0
    winner = result.candidates.index(result.groups)
    assert all(v >= 2 for i, v in enumerate(result.votes[winner]) if i != winner)

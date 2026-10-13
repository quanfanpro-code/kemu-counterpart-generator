"""结转最高优先与共享截止时间的行为检查。"""
import pytest

from src.pipeline.group_processor import GroupProcessor, process_group
from tests.test_三维分录判断 import sample
from tests.test_凭证内分录识别 import voucher, VOUCHER


def test_混合损益也先走整凭证原规则():
    source = voucher(
        ("本年利润", 100, 0), ("主营业务收入", 0, 100),
        ("管理费用", 50, 0), ("银行存款", 0, 50),
    )
    rows, warnings = process_group((VOUCHER, source))
    assert warnings == []
    assert {r["对方科目"] for r in rows if r["一级科目"] == "管理费用"} == {"本年利润"}
    assert (rows, warnings) == GroupProcessor((VOUCHER, source)).process()


def test_折半展开途中截止不能返回部分候选():
    from src.core.algorithms import find_balanced_subsets
    calls = 0
    def check():
        nonlocal calls
        calls += 1
        if calls >= 10:
            raise TimeoutError("到时")
    with pytest.raises(TimeoutError):
        find_balanced_subsets(list(enumerate([1, -1] * 10)),
                              max_iterations=None, check_time=check)


def test_摘要比较超时保留基线并警告(monkeypatch):
    from src.pipeline import 分录判断 as module
    clock = [0.0]
    original = module.compare_summaries
    def slow(a, b):
        clock[0] += 10
        return original(a, b)
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module, "compare_summaries", slow)
    source = sample()
    base = [source.iloc[:2], source.iloc[2:]]
    result = module.choose_voucher_groups(source, base)
    assert not result.complete and result.groups == ((0, 1), (2, 3))
    assert "30秒" in result.reason and "未完成" in result.reason
    clock[0] = 0
    rows, warnings = process_group((VOUCHER, source))
    assert warnings and "未完成" in warnings[0]
    assert sum(r["借方发生额"] for r in rows) == 200
    assert sum(r["贷方发生额"] for r in rows) == 200


def test_超时无连续基线也保留整凭证金额(monkeypatch):
    from src.pipeline import 分录判断 as module
    monkeypatch.setattr(module, "SPLIT_TIME_LIMIT_SECONDS", 0)
    source = sample().iloc[[0, 2, 1, 3]].reset_index(drop=True)
    rows, warnings = process_group((VOUCHER, source))
    assert warnings and "未完成" in warnings[0]
    assert sum(r["借方发生额"] for r in rows) == 200
    assert sum(r["贷方发生额"] for r in rows) == 200

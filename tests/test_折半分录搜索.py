"""共享折半搜索与大凭证预筛的真实行为测试。"""
from itertools import combinations
import pandas as pd
import pytest


@pytest.mark.parametrize("values", [
    [5, -8, 3], [100, -100, 50, -50], [-60, -40, 100],
    [2, 3, -5, 7, -7, -2], [0, 1, -1], [1, 2, 4],
])
def test_有符号零和多解与小规模穷举一致(values):
    from src.core.algorithms import find_balanced_subsets
    expected = {part for size in range(2, len(values) + 1)
                for part in combinations(range(len(values)), size)
                if sum(values[i] for i in part) == 0}
    parts, used, complete = find_balanced_subsets(list(enumerate(values)), 20000)
    assert complete and set(parts) == expected
    assert used <= 20000


def test_搜索超预算不返回伪完整结果():
    from src.core.algorithms import find_balanced_subsets
    parts, used, complete = find_balanced_subsets(list(enumerate([1, -1] * 20)), 100)
    assert not complete and not parts and used <= 100


def test_共享半区保留红字先超额后抵销():
    from src.core.algorithms import _generate_left_combos
    parts, used = _generate_left_combos([(0, 5), (1, -8), (2, 3)], 0, 0)
    assert (0, [0, 1, 2]) in parts


def large_voucher(count, sign=1):
    rows = []
    for i in range(count):
        subject = "管理费用" if i % 2 == 0 else "主营业务成本"
        summary = ("支付办公费" if i % 2 == 0 else "结转销售成本") + f" 合同号HT-{i:03}"
        rows.append((subject, (100 + i) * sign, 0, summary))
    for i in range(count):
        subject = "银行存款" if i % 2 == 0 else "库存商品"
        rows.append((subject, 0, (100 + i) * sign, rows[i][3]))
    return pd.DataFrame(rows, columns=["一级科目", "借方发生额", "贷方发生额", "摘要"])


@pytest.mark.parametrize("count,sign", [(10, 1), (20, 1), (10, -1)])
def test_超14行交错凭证按业务预筛仍能拆(count, sign):
    from src.pipeline.分录判断 import choose_voucher_groups
    result = choose_voucher_groups(large_voucher(count, sign), None)
    assert result.complete
    assert result.groups == tuple((i, i + count) for i in range(count))


def test_关系比较预算耗尽保留连续基线(monkeypatch):
    from src.pipeline import 分录判断 as module
    from src.pipeline.group_processor import GroupProcessor, _split_contiguous_balanced_groups
    from tests.test_三维分录判断 import sample
    source = sample()
    base = _split_contiguous_balanced_groups(GroupProcessor((None, source)), source)
    monkeypatch.setattr(module, "MAX_SEARCH_STATES", 1)
    result = module.choose_voucher_groups(source, base)
    assert not result.complete and result.groups == ((0, 1), (2, 3))


def test_随机小集合逐项穷举核对不漏组合():
    import random
    from src.core.algorithms import find_balanced_subsets
    rng = random.Random(42)
    for _ in range(100):
        values = [rng.randint(-9, 9) for _ in range(8)]
        expected = {part for size in range(2, 9)
                    for part in combinations(range(8), size)
                    if sum(values[i] for i in part) == 0}
        parts, _, complete = find_balanced_subsets(list(enumerate(values)), 20000)
        assert complete and set(parts) == expected


def test_旧单解匹配接口仍保留金额容差():
    from src.core.algorithms import solve_subset_sum
    candidates = [("甲", {"amount": 60}), ("乙", {"amount": 40})]
    result = solve_subset_sum(100.005, candidates)
    assert result is not None
    assert {item[0] for item in result} == {"甲", "乙"}


@pytest.mark.parametrize("values", [[], [1], [1, -1]])
def test_零预算不递归展开(values):
    from src.core.algorithms import find_balanced_subsets
    parts, used, complete = find_balanced_subsets(list(enumerate(values)), 0)
    assert used == 0 and parts == []
    assert complete == (len(values) < 2)


def test_大凭证真实命令行输出完整金额(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    source = large_voucher(20).assign(会计月="2026-01", 凭证种类="记", 凭证编号="1")
    source.to_excel(tmp_path / "输入.xlsx", index=False)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([
        sys.executable, "-B", "-X", "utf8", str(root / "cli" / "序时账分析器命令行版.py"),
        str(tmp_path / "输入.xlsx"), str(tmp_path / "输出.xlsx"), "--mode", "summary",
        "--log-level", "ERROR",
    ], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    output = pd.read_excel(tmp_path / "输出.xlsx", sheet_name="生成结果")
    assert len(output) == 40
    assert output["借方发生额"].sum() == source["借方发生额"].sum()
    assert output["贷方发生额"].sum() == source["贷方发生额"].sum()
    assert set(output.loc[output["一级科目"] == "管理费用", "对方科目"]) == {"银行存款"}
    assert set(output.loc[output["一级科目"] == "主营业务成本", "对方科目"]) == {"库存商品"}

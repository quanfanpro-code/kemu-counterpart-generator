"""完整原始行候选的三维判断，搜索不完整时保留连续分法。"""
from collections import deque
from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from time import monotonic

import pandas as pd

from ..core.precision import PrecisionEngine
from ..core.rules import check_rule_match
from ..core.algorithms import find_balanced_subsets
from ..core.摘要判断 import compare_summaries, extract_summary, RELATION_THRESHOLD


SPLIT_TIME_LIMIT_SECONDS = 30
SCORE_MARGIN = 0.05


@dataclass(frozen=True)
class SplitDecision:
    groups: tuple | None
    candidates: tuple = ()
    scores: tuple = ()
    complete: bool = True
    reason: str = "保留连续分法"
    votes: tuple = ()


def _votes(left, right):
    return sum(a is not None and b is not None and a > b + SCORE_MARGIN
               for a, b in zip(left, right))


def majority_winner(scores, check_time=None):
    """只有对其他每个候选均取得两票的方案胜出；相同及未知弃权。"""
    for i, left in enumerate(scores):
        wins = True
        for j, right in enumerate(scores):
            if check_time:
                check_time()
            if j != i and _votes(left, right) < 2:
                wins = False
                break
        if wins:
            return i
    return None


def _net(row):
    return (PrecisionEngine.to_integer_li(row["借方发生额"]) -
            PrecisionEngine.to_integer_li(row["贷方发生额"]))


def standard_group_supported(group):
    """标准关系的整数容量流：不能仅凭每行存在科目伙伴认定整组标准。"""
    return _standard_rows_supported(group.to_dict("records"))


def _standard_rows_supported(rows, check_time=None):
    amounts = [_net(row) for row in rows]
    if not amounts or sum(amounts) or any(not amount for amount in amounts):
        return False
    n, source, sink = len(rows), len(rows), len(rows) + 1
    capacity = [[0] * (n + 2) for _ in range(n + 2)]
    total = sum(x for x in amounts if x > 0)
    for i, value in enumerate(amounts):
        if check_time:
            check_time()
        if value > 0:
            capacity[source][i] = value
            for j, other in enumerate(amounts):
                if check_time:
                    check_time()
                if other < 0 and check_rule_match(rows[i]["一级科目"], rows[j]["一级科目"]):
                    capacity[i][j] = total
        else:
            capacity[i][sink] = -value
    flow = 0
    while flow < total:
        if check_time:
            check_time()
        parents = [-1] * (n + 2)
        parents[source] = source
        queue = deque([source])
        while queue and parents[sink] == -1:
            if check_time:
                check_time()
            u = queue.popleft()
            for v, available in enumerate(capacity[u]):
                if check_time:
                    check_time()
                if available > 0 and parents[v] == -1:
                    parents[v] = u
                    queue.append(v)
        if parents[sink] == -1:
            return False
        value, v = total - flow, sink
        while v != source:
            u = parents[v]
            value = min(value, capacity[u][v])
            v = u
        v = sink
        while v != source:
            u = parents[v]
            capacity[u][v] -= value
            capacity[v][u] += value
            v = u
        flow += value
    return True


def _summary(row):
    first, second = row.get("摘要"), row.get("业务说明")
    a, b = extract_summary(first), extract_summary(second)
    if a.text and b.text and compare_summaries(first, second).conflict:
        return ""
    return a.raw if a.text or a.identifiers else b.raw


def choose_voucher_groups(group, baseline, deadline=None):
    """每张凭证共享30秒，超时不采用未完整比较的候选。"""
    if deadline is None:
        deadline = monotonic() + SPLIT_TIME_LIMIT_SECONDS
    def check_time():
        if monotonic() >= deadline:
            raise TimeoutError("拆分分录计算到时")
    try:
        return _choose_voucher_groups(group, baseline, check_time)
    except TimeoutError:
        position_of = {idx: pos for pos, idx in enumerate(group.index)}
        base = (tuple(tuple(position_of[idx] for idx in part.index) for part in baseline)
                if baseline else None)
        return SplitDecision(base, complete=False,
                             reason="拆分未完成：达到每张凭证30秒上限，保留原处理")


def _choose_voucher_groups(group, baseline, check_time):
    """返回位置分法及依据；原始索引只用于验证及恢复，不改输入。"""
    check_time()
    position_of = {idx: pos for pos, idx in enumerate(group.index)}
    base = tuple(tuple(position_of[idx] for idx in part.index) for part in baseline) if baseline else None
    def fallback(reason, complete=True):
        return SplitDecision(base, complete=complete, reason=reason)
    if not group.index.is_unique or not group.index.is_monotonic_increasing or len(group) < 4:
        return fallback("原始行序或行数不满足保护条件")
    rows = group.to_dict("records")
    # 与共同处理器复用利润科目语义，不让新增候选绕过旧保护。
    from .group_processor import GroupProcessor
    profit_check = GroupProcessor((None, group))._is_profit_subject
    profits = 0
    for row in rows:
        check_time()
        subject = row["一级科目"]
        if pd.isna(subject) or str(subject).strip().lower() in {"", "nan"}:
            return fallback("空科目保护")
        profits += profit_check(str(subject))
        d, c = float(row["借方发生额"]), float(row["贷方发生额"])
        if not isfinite(d) or not isfinite(c) or (d == 0) == (c == 0) or not _net(row):
            return fallback("金额或同行借贷保护")
    amounts = tuple(_net(row) for row in rows)
    if profits or sum(amounts):
        return SplitDecision(None, reason="结转损益优先或不平衡保护")
    n = len(rows)
    summaries = []
    for row in rows:
        check_time()
        summaries.append(_summary(row))
    summary_useful = len({extract_summary(s).raw for s in summaries if s}) > 1
    if not summary_useful:
        return fallback("摘要无法区分方案，保留连续分法")
    relations, standard_edges = {}, set()
    neighbors = [set() for _ in rows]
    for i, j in combinations(range(n), 2):
        check_time()
        relation = compare_summaries(summaries[i], summaries[j])
        relations[i, j] = relation
        debit, credit = (i, j) if amounts[i] > 0 else (j, i)
        legal = amounts[debit] > 0 > amounts[credit] and check_rule_match(
            str(rows[debit]["一级科目"]), str(rows[credit]["一级科目"]))
        if legal:
            standard_edges.add((debit, credit))
        # 未知不是反对；明确冲突只剪掉新增跨业务联系，基线仍保留。
        if not relation.conflict and (legal or relation.known and relation.score >= RELATION_THRESHOLD):
            neighbors[i].add(j)
            neighbors[j].add(i)
    pools, unseen = [], set(range(n))
    while unseen:
        check_time()
        todo, pool = [min(unseen)], set()
        while todo:
            check_time()
            current = todo.pop()
            if current in pool:
                continue
            pool.add(current)
            todo.extend(neighbors[current] - pool)
        unseen -= pool
        if len(pool) >= 2:
            pools.append(tuple(sorted(pool)))
    supported, densities = {}, {}
    def standard(indices):
        key = tuple(indices)
        if key not in supported:
            check_time()
            supported[key] = _standard_rows_supported([rows[i] for i in key], check_time)
            possible = sum(amounts[i] > 0 > amounts[j] for i in key for j in key)
            densities[key] = (sum((i, j) in standard_edges for i in key for j in key) /
                              possible if possible else 0)
        return supported[key]
    subsets = []
    for pool in pools:
        parts, _, _ = find_balanced_subsets(
            [(i, amounts[i]) for i in pool], max_iterations=None, check_time=check_time)
        for indices in parts:
            pairs = []
            for pair in combinations(indices, 2):
                check_time()
                pairs.append(relations[pair])
            coherent = summary_useful and all(
                r.known and not r.conflict and r.score >= RELATION_THRESHOLD for r in pairs)
            if coherent or standard(indices):
                subsets.append(indices)
    candidates = {base} if base else set()
    candidates.add((tuple(range(n)),))
    by_first = {i: [] for i in range(n)}
    for part in subsets:
        for i in part:
            check_time()
            by_first[i].append(part)
    def cover(remaining, path):
        check_time()
        if not remaining:
            candidates.add(tuple(sorted(path)))
            return
        first = min(remaining)
        # 剩余任一行已无完整候选承接时，立即剪去该覆盖分支。
        for i in remaining:
            found = False
            for part in by_first[i]:
                check_time()
                if set(part) <= remaining:
                    found = True
                    break
            if not found:
                return
        for part in by_first[first]:
            check_time()
            if set(part) <= remaining:
                cover(remaining - set(part), (*path, part))
    cover(set(range(n)), ())
    candidates = tuple(sorted(candidates))
    scores = []
    for plan in candidates:
        check_time()
        links = sum(b == a + 1 for part in plan for a, b in zip(part, part[1:]))
        possible_links = sum(len(part) - 1 for part in plan)
        order_score = links / possible_links if possible_links else 0
        group_evidence = []
        for part in plan:
            evidence = []
            for pair in combinations(part, 2):
                check_time()
                if relations[pair].known:
                    evidence.append(relations[pair].score)
            group_evidence.append(evidence)
        known = [value for values in group_evidence for value in values]
        # 缺失不补票，单组强关联不能抵消另一组的明确矛盾。
        summary_score = (min(known) if all(group_evidence) and summary_useful else None)
        standard_score = (sum(len(part) * densities[part] for part in plan if standard(part)) / n
                          if standard_edges else None)
        scores.append((order_score, summary_score, standard_score))
    winner = majority_winner(scores, check_time)
    votes = []
    for left in scores:
        row_votes = []
        for right in scores:
            check_time()
            row_votes.append(_votes(left, right))
        votes.append(tuple(row_votes))
    votes = tuple(votes)
    check_time()
    if winner is not None and len(candidates[winner]) > 1:
        return SplitDecision(candidates[winner], candidates, tuple(scores), True, "三维多数胜出", votes)
    return SplitDecision(base, candidates, tuple(scores), True, "无全面多数，保留连续分法", votes)

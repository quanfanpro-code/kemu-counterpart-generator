# -*- coding: utf-8 -*-
# 折半枚举算法（Meet-in-the-Middle）

import bisect
from typing import Any, Dict, List, Optional, Tuple

from .precision import PrecisionEngine

# 折半枚举算法（MITM）安全常量 - 取值依据说明：
# MAX_CANDIDATE_POOL_SIZE = 36: 单边18个元素，最大组合数2^18≈26万，计算可控
MAX_CANDIDATE_POOL_SIZE = 36
# MITM_ITERATION_LIMIT = 300000: 略大于2^18，作为兜底保护
MITM_ITERATION_LIMIT = 300000


def _generate_left_combos(
    candidates: List[Tuple[Any, int]],
    target_li: int,
    tolerance_li: int,
    max_iterations: int = MITM_ITERATION_LIMIT,
    lower_bound: Optional[int] = None,
    check_time=None
) -> Tuple[List[Tuple[int, List[Any]]], int]:
    """
    生成左半区所有合法组合。

    :param candidates: 左半区候选列表 [(对象, 金额厘), ...]
    :param target_li: 目标金额（厘）
    :param tolerance_li: 容差（厘）
    :param max_iterations: 最大迭代次数
    :return: (组合列表, 迭代次数) - 组合列表按金额排序
    """
    n = len(candidates)
    if n == 0:
        return [(0, [])], 0

    combos: List[Tuple[int, List[Any]]] = []
    iterations = 0
    upper_bound = target_li + tolerance_li
    remaining_min = [0] * (n + 1)
    remaining_max = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        if check_time:
            check_time()
        remaining_min[i] = remaining_min[i + 1] + min(0, candidates[i][1])
        remaining_max[i] = remaining_max[i + 1] + max(0, candidates[i][1])

    def dfs(idx: int, current_sum: int, path: List[Any]):
        nonlocal iterations
        if check_time:
            check_time()
        iterations += 1
        if max_iterations is not None and iterations > max_iterations:
            return

        # 正负金额均用剩余可达区间剪枝，不能把暂时超额的红字组合丢掉。
        if current_sum + remaining_min[idx] > upper_bound:
            return
        if lower_bound is not None and current_sum + remaining_max[idx] < lower_bound:
            return

        if idx == n:
            combos.append((current_sum, path.copy()))
            return

        obj, amt_li = candidates[idx]

        path.append(obj)
        dfs(idx + 1, current_sum + amt_li, path)
        path.pop()

        dfs(idx + 1, current_sum, path)

    dfs(0, 0, [])
    if check_time:
        check_time()
    combos.sort(key=lambda x: x[0])
    if check_time:
        check_time()
    return combos, iterations


def find_balanced_subsets(candidates, max_iterations=MITM_ITERATION_LIMIT, check_time=None):
    """在预筛范围内返回全部严格零和原始行集合及完整标志；不截行。"""
    n = len(candidates)
    if n < 2:
        return [], 0, True
    mid = n // 2
    # 预计半区叶子数已超预算时提前退出，避免递归深度及指数展开。
    if max_iterations is not None and (
            mid >= max_iterations.bit_length() or n - mid >= max_iterations.bit_length()):
        return [], 0, False
    left_raw, right_raw = candidates[:mid], candidates[mid:]
    def half(items, other, remaining):
        low = -sum(max(0, value) for _, value in other)
        high = -sum(min(0, value) for _, value in other)
        return _generate_left_combos(items, high, 0, remaining, low, check_time)
    left, used = half(left_raw, right_raw, max_iterations)
    if max_iterations is not None and used > max_iterations:
        return [], max_iterations, False
    right, right_used = half(right_raw, left_raw,
                            None if max_iterations is None else max_iterations - used)
    used += right_used
    if max_iterations is not None and used > max_iterations:
        return [], max_iterations, False
    values = [value for value, _ in left]
    parts = []
    for value, path in right:
        if check_time:
            check_time()
        start, end = bisect.bisect_left(values, -value), bisect.bisect_right(values, -value)
        for pos in range(start, end):
            if check_time:
                check_time()
            used += 1
            if max_iterations is not None and used > max_iterations:
                return [], max_iterations, False
            indices = tuple(sorted(left[pos][1] + path))
            if len(indices) >= 2:
                parts.append(indices)
    return parts, used, True


def solve_subset_sum(
    target: float,
    candidates: List[Tuple[Any, Dict[str, Any]]],
    tolerance: float = 0.01
) -> Optional[List[Any]]:
    """
    使用折半枚举（Meet-in-the-Middle）算法求解子集和问题。

    时间复杂度：O(2^(N/2) * log(2^(N/2)))，相比回溯法O(2^N)大幅优化。
    适用于候选数量较多的"长尾发票凑单"场景。

    :param target: 目标金额（元）
    :param candidates: 候选列表，每个元素为 (item_obj, {'amount': 金额})
    :param tolerance: 容差（元），默认0.01元=1分
    :return: 匹配的 item_obj 列表，如果无解返回 None
    """
    target_li = PrecisionEngine.to_integer_li(target)
    tolerance_li = PrecisionEngine.to_integer_li(tolerance)

    if not candidates:
        return None

    valid_candidates = []
    for cand in candidates:
        if len(cand) < 2 or not isinstance(cand[1], dict):
            continue
        amt = cand[1].get('amount', 0)
        amt_li = PrecisionEngine.to_integer_li(amt)
        if amt_li <= target_li + tolerance_li and amt_li > 0:
            valid_candidates.append((cand, amt_li))

    if not valid_candidates:
        return None

    valid_candidates.sort(key=lambda x: x[1], reverse=True)

    total_li = sum(x[1] for x in valid_candidates)
    if total_li < target_li - tolerance_li:
        return None

    if len(valid_candidates) > MAX_CANDIDATE_POOL_SIZE:
        valid_candidates = valid_candidates[:MAX_CANDIDATE_POOL_SIZE]

    n = len(valid_candidates)
    mid = n // 2

    left_raw = valid_candidates[:mid]
    right_raw = valid_candidates[mid:]

    left_combos, left_iters = _generate_left_combos(
        [(c[0], c[1]) for c in left_raw],
        target_li,
        tolerance_li
    )

    if not left_combos:
        return None

    left_values = [c[0] for c in left_combos]

    right_iterations = 0

    def search_right(idx: int, current_sum: int, path: List[Any]) -> Optional[List[Any]]:
        nonlocal right_iterations
        right_iterations += 1
        if right_iterations > MITM_ITERATION_LIMIT:
            return None

        if current_sum > target_li + tolerance_li:
            return None

        lower_bound = target_li - current_sum - tolerance_li
        upper_bound = target_li - current_sum + tolerance_li

        left_idx = bisect.bisect_left(left_values, lower_bound)
        right_idx = bisect.bisect_right(left_values, upper_bound)

        if left_idx < right_idx:
            return left_combos[left_idx][1] + path

        if idx == len(right_raw):
            return None

        obj, amt_li = right_raw[idx]

        path.append(obj)
        result = search_right(idx + 1, current_sum + amt_li, path)
        if result is not None:
            return result
        path.pop()

        return search_right(idx + 1, current_sum, path)

    result = search_right(0, 0, [])
    return result

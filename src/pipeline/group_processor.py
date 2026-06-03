# -*- coding: utf-8 -*-
"""凭证分组处理模块"""
from typing import Any, Dict, List, Tuple

import pandas as pd

from ..core.precision import PrecisionEngine
from ..core.algorithms import solve_subset_sum
from ..core.rules import check_rule_match

# 浮点数相等判断阈值
FLOAT_EPSILON = 1e-9


class GroupProcessor:
    """
    封装凭证分组处理逻辑，提高可读性和维护性。
    """
    def __init__(self, group_data: Tuple[Any, pd.DataFrame]):
        self.name, self.group = group_data
        self.output_rows: List[Dict[str, Any]] = []
        self.debit_items: List[Dict[str, Any]] = []
        self.credit_items: List[Dict[str, Any]] = []
        self.all_items: List[Dict[str, Any]] = []

    def process(self) -> List[Dict[str, Any]]:
        # 0. 预处理：转换数据
        self._prepare_data()

        # 1. 阶段零：结转损益特殊规则
        if self._process_profit_loss():
            return self.output_rows

        # 2. 阶段一：标准模板优先匹配
        self._match_standard_rules()

        # 3. 阶段二：算法金额匹配
        self._match_algo()

        # 4. 阶段三：兜底处理
        self._match_fallback()

        return self.output_rows

    def _prepare_data(self):
        records = self.group.to_dict('records')
        for row in records:
            d = row['借方发生额']
            c = row['贷方发生额']
            subject = str(row['一级科目'])
            item = {
                'row_data': row.copy(),
                'subject': subject,
                'matched': False
            }
            if d > 0:
                item['amount'] = float(PrecisionEngine.to_decimal(d))
                item['amount_li'] = PrecisionEngine.to_integer_li(d)
                item['side'] = 'debit'
                self.debit_items.append(item)
            elif c < 0:
                item['amount'] = float(PrecisionEngine.to_decimal(abs(c)))
                item['amount_li'] = PrecisionEngine.to_integer_li(abs(c))
                item['side'] = 'debit'
                self.debit_items.append(item)
            elif c > 0:
                item['amount'] = float(PrecisionEngine.to_decimal(c))
                item['amount_li'] = PrecisionEngine.to_integer_li(c)
                item['side'] = 'credit'
                self.credit_items.append(item)
            elif d < 0:
                item['amount'] = float(PrecisionEngine.to_decimal(abs(d)))
                item['amount_li'] = PrecisionEngine.to_integer_li(abs(d))
                item['side'] = 'credit'
                self.credit_items.append(item)
            else:
                item['amount'] = 0
                item['amount_li'] = 0
                item['side'] = 'skip'
                row_out = row.copy()
                row_out['对方科目'] = None
                row_out['匹配类型'] = '无发生额'
                self.output_rows.append(row_out)

        self.debit_items.sort(key=lambda x: x['amount_li'], reverse=True)
        self.credit_items.sort(key=lambda x: x['amount_li'], reverse=True)
        self.all_items = self.debit_items + self.credit_items

    def _add_match(self, item1: Dict, item2_list: List[Dict], match_type: str = "算法生成"):
        for match_item in item2_list:
            row_out = item1['row_data'].copy()
            row_out['对方科目'] = match_item['subject']
            row_out['匹配类型'] = match_type
            amt = match_item['amount']
            if item1['side'] == 'debit':
                if row_out['借方发生额'] > 0: row_out['借方发生额'] = amt
                else: row_out['贷方发生额'] = -amt
            else:
                if row_out['贷方发生额'] > 0: row_out['贷方发生额'] = amt
                else: row_out['借方发生额'] = -amt
            self.output_rows.append(row_out)

            row_out_2 = match_item['row_data'].copy()
            row_out_2['对方科目'] = item1['subject']
            row_out_2['匹配类型'] = match_type
            self.output_rows.append(row_out_2)

    def _is_profit_subject(self, subj: str) -> bool:
        s = str(subj).strip()
        if any(x in s for x in ["费用", "成本", "折旧", "减值", "摊销"]):
            return False
        return s.startswith("本年利润") or s.startswith("利润分配")

    def _process_profit_loss(self) -> bool:
        profit_items = [x for x in self.all_items if self._is_profit_subject(x['subject'])]
        if not profit_items:
            return False

        other_items = [x for x in self.all_items if x not in profit_items]
        if not other_items:
            return False

        for item in self.all_items: item['matched'] = True

        p_debit_sum = sum(p['amount'] for p in profit_items if p['side'] == 'debit')
        p_credit_sum = sum(p['amount'] for p in profit_items if p['side'] == 'credit')
        p_net = p_debit_sum - p_credit_sum

        target_col = '借方发生额' if p_net >= -FLOAT_EPSILON else '贷方发生额'
        calc_p_net = 0

        for o_item in other_items:
            row_o = o_item['row_data'].copy()
            row_o['对方科目'] = profit_items[0]['subject']
            row_o['匹配类型'] = '结转损益规则'
            self.output_rows.append(row_o)

            row_p = profit_items[0]['row_data'].copy()
            row_p['对方科目'] = o_item['subject']
            row_p['匹配类型'] = '结转损益规则(拆分)'
            row_p['借方发生额'] = 0
            row_p['贷方发生额'] = 0

            val = o_item['amount']
            is_o_debit = (o_item['side'] == 'debit')
            should_be_debit = not is_o_debit

            if should_be_debit: calc_p_net += val
            else: calc_p_net -= val

            is_target_debit = (target_col == '借方发生额')
            final_val = 0
            if is_target_debit:
                final_val = val if should_be_debit else -val
            else:
                final_val = -val if should_be_debit else val
            row_p[target_col] = final_val
            self.output_rows.append(row_p)

        diff = p_net - calc_p_net
        if not PrecisionEngine.amounts_match(diff, 0, tolerance_li=100):
            row_diff = profit_items[0]['row_data'].copy()
            row_diff['对方科目'] = '损益结转误差调整'
            row_diff['匹配类型'] = '结转损益规则(调整)'
            row_diff['借方发生额'] = 0
            row_diff['贷方发生额'] = 0
            if target_col == '借方发生额': row_diff['借方发生额'] = diff
            else: row_diff['贷方发生额'] = -diff
            self.output_rows.append(row_diff)
        return True

    def _match_standard_rules(self):
        # 1.1 一对一
        for d in self.debit_items:
            if d['matched']: continue
            for c in self.credit_items:
                if c['matched']: continue
                if PrecisionEngine.amounts_match(d['amount'], c['amount']) and check_rule_match(d['subject'], c['subject']):
                    d['matched'] = True
                    c['matched'] = True
                    self._add_match(d, [c], match_type="标准模板")
                    break
        # 1.2 一对多
        for d in self.debit_items:
            if d['matched']: continue
            candidates = [(i, c) for i, c in enumerate(self.credit_items)
                          if not c['matched'] and PrecisionEngine.compare_amounts(c['amount'], d['amount']) <= 0
                          and check_rule_match(d['subject'], c['subject'])]
            match = solve_subset_sum(d['amount'], candidates)
            if match:
                d['matched'] = True
                matched_credits = []
                for idx, c in match:
                    c['matched'] = True
                    matched_credits.append(c)
                self._add_match(d, matched_credits, match_type="标准模板")
        # 1.3 多对一
        for c in self.credit_items:
            if c['matched']: continue
            candidates = [(i, d) for i, d in enumerate(self.debit_items)
                          if not d['matched'] and PrecisionEngine.compare_amounts(d['amount'], c['amount']) <= 0
                          and check_rule_match(d['subject'], c['subject'])]
            match = solve_subset_sum(c['amount'], candidates)
            if match:
                c['matched'] = True
                matched_debits = []
                for idx, d in match:
                    d['matched'] = True
                    matched_debits.append(d)
                self._add_match(c, matched_debits, match_type="标准模板")

    def _match_algo(self):
        # 2.1 一对一
        for d in self.debit_items:
            if d['matched']: continue
            for c in self.credit_items:
                if c['matched']: continue
                if PrecisionEngine.amounts_match(d['amount'], c['amount']):
                    d['matched'] = True
                    c['matched'] = True
                    self._add_match(d, [c], match_type="算法生成")
                    break
        # 2.2 一对多
        for d in self.debit_items:
            if d['matched']: continue
            candidates = [(i, c) for i, c in enumerate(self.credit_items)
                          if not c['matched'] and PrecisionEngine.compare_amounts(c['amount'], d['amount']) <= 0]
            match = solve_subset_sum(d['amount'], candidates)
            if match:
                d['matched'] = True
                matched_credits = []
                for idx, c in match:
                    c['matched'] = True
                    matched_credits.append(c)
                self._add_match(d, matched_credits, match_type="算法生成")
        # 2.3 多对一
        for c in self.credit_items:
            if c['matched']: continue
            candidates = [(i, d) for i, d in enumerate(self.debit_items)
                          if not d['matched'] and PrecisionEngine.compare_amounts(d['amount'], c['amount']) <= 0]
            match = solve_subset_sum(c['amount'], candidates)
            if match:
                c['matched'] = True
                matched_debits = []
                for idx, d in match:
                    d['matched'] = True
                    matched_debits.append(d)
                self._add_match(c, matched_debits, match_type="算法生成")

    def _match_fallback(self):
        unmatched_debit = [d for d in self.debit_items if not d['matched']]
        unmatched_credit = [c for c in self.credit_items if not c['matched']]
        d_idx = 0
        c_idx = 0

        while d_idx < len(unmatched_debit) and c_idx < len(unmatched_credit):
            d_item = unmatched_debit[d_idx]
            c_item = unmatched_credit[c_idx]
            if 'rem_amount' not in d_item: d_item['rem_amount'] = d_item['amount']
            if 'rem_amount' not in c_item: c_item['rem_amount'] = c_item['amount']
            val_d = d_item['rem_amount']
            val_c = c_item['rem_amount']
            matched_val = min(val_d, val_c)

            def set_split_amount(row_data, val):
                d_orig = row_data.get('借方发生额', 0)
                c_orig = row_data.get('贷方发生额', 0)
                if abs(d_orig) > FLOAT_EPSILON:
                    sign = 1 if d_orig > 0 else -1
                    row_data['借方发生额'] = val * sign
                elif abs(c_orig) > FLOAT_EPSILON:
                    sign = 1 if c_orig > 0 else -1
                    row_data['贷方发生额'] = val * sign

            row_d = d_item['row_data'].copy()
            row_d['对方科目'] = c_item['subject']
            row_d['匹配类型'] = '算法生成(兜底拆分)'
            set_split_amount(row_d, matched_val)
            self.output_rows.append(row_d)

            row_c = c_item['row_data'].copy()
            row_c['对方科目'] = d_item['subject']
            row_c['匹配类型'] = '算法生成(兜底拆分)'
            set_split_amount(row_c, matched_val)
            self.output_rows.append(row_c)

            if PrecisionEngine.amounts_match(val_d, matched_val): d_idx += 1
            else: d_item['rem_amount'] -= matched_val
            if PrecisionEngine.amounts_match(val_c, matched_val): c_idx += 1
            else: c_item['rem_amount'] -= matched_val

        for i in range(d_idx, len(unmatched_debit)):
            d = unmatched_debit[i]
            row = d['row_data'].copy()
            row['对方科目'] = '未找到匹配'
            row['匹配类型'] = '算法生成(异常剩余)'
            rem = d.get('rem_amount', d['amount'])
            d_orig = row.get('借方发生额', 0)
            c_orig = row.get('贷方发生额', 0)
            if abs(d_orig) > FLOAT_EPSILON:
                sign = 1 if d_orig > 0 else -1
                row['借方发生额'] = rem * sign
            elif abs(c_orig) > FLOAT_EPSILON:
                sign = 1 if c_orig > 0 else -1
                row['贷方发生额'] = rem * sign
            self.output_rows.append(row)

        for i in range(c_idx, len(unmatched_credit)):
            c = unmatched_credit[i]
            row = c['row_data'].copy()
            row['对方科目'] = '未找到匹配'
            row['匹配类型'] = '算法生成(异常剩余)'
            rem = c.get('rem_amount', c['amount'])
            d_orig = row.get('借方发生额', 0)
            c_orig = row.get('贷方发生额', 0)
            if abs(d_orig) > FLOAT_EPSILON:
                sign = 1 if d_orig > 0 else -1
                row['借方发生额'] = rem * sign
            elif abs(c_orig) > FLOAT_EPSILON:
                sign = 1 if c_orig > 0 else -1
                row['贷方发生额'] = rem * sign
            self.output_rows.append(row)


def process_group(group_data: Tuple[Any, pd.DataFrame]) -> List[Dict[str, Any]]:
    """处理单个凭证分组（用于并行计算入口）。"""
    processor = GroupProcessor(group_data)
    return processor.process()

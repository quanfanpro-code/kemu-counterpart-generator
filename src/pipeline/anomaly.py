# -*- coding: utf-8 -*-
"""异常分录检测与班福定律分析模块"""
import math
from typing import Any, Optional, Tuple

import pandas as pd

from ..core.rules import check_rule_match
from ..utils.logger import logger

# 发生额有效值判断阈值
AMOUNT_VALID_THRESHOLD = 1e-6


def get_leading_digit(n: Any) -> Optional[int]:
    """提取数字的首位数（用于班福定律分析）。"""
    try:
        if pd.isna(n): return None
        if isinstance(n, (int, float)):
            if n == 0: return None
            s = f"{abs(n):.15g}".lower() # 使用科学计数法格式化，避免浮点精度问题
        else:
            s = str(n).replace(',', '').strip().lower()

        if 'e' in s:
            base = s.split('e')[0]
            base = base.replace('.', '').replace('-', '')
            for char in base:
                if char.isdigit() and char != '0':
                    return int(char)
        else:
            s = s.replace('.', '').replace('-', '')
            for char in s:
                if char.isdigit() and char != '0':
                    return int(char)
        return None
    except (ValueError, TypeError, AttributeError):
        return None


def detect_anomalies(out_df: pd.DataFrame, threshold: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    检测异常分录。

    :param out_df: 生成结果数据
    :param threshold: 异常金额阈值
    :return: (异常分录明细DataFrame, 异常分录汇总DataFrame)
    """
    logger.info("正在检测异常分录...")
    anomaly_rows = []
    anomaly_patterns = []

    if not out_df.empty:
        logger.info("正在逐行扫描异常...")
        for row in out_df.itertuples(index=False):
            d_amt = abs(getattr(row, '借方发生额', 0))
            c_amt = abs(getattr(row, '贷方发生额', 0))
            # 取较大值作为该行金额，避免借贷同行相反时金额翻倍
            total_amt = max(d_amt, c_amt)
            if total_amt <= threshold: continue

            match_type = str(getattr(row, '匹配类型', ''))
            if '标准模板' in match_type or '结转损益' in match_type: continue

            subj = str(getattr(row, '一级科目', ''))
            contra = str(getattr(row, '对方科目', ''))

            if not contra or contra == 'nan' or contra == 'None':
                anomaly_rows.append(row._asdict())
                continue

            debit_subj = ""
            credit_subj = ""
            if d_amt > AMOUNT_VALID_THRESHOLD:
                debit_subj = subj
                credit_subj = contra
            elif c_amt > AMOUNT_VALID_THRESHOLD:
                credit_subj = subj
                debit_subj = contra
            else:
                continue

            if check_rule_match(debit_subj, credit_subj): continue

            row_with_keys = row._asdict()
            row_with_keys['__debit_key'] = debit_subj
            row_with_keys['__credit_key'] = credit_subj
            anomaly_rows.append(row_with_keys)

            # 只在借方行时记录聚合 pattern，避免同一笔分录的借贷两行都被计数导致金额翻倍
            if d_amt <= AMOUNT_VALID_THRESHOLD:
                continue

            desc = str(getattr(row, '摘要', getattr(row, '业务说明', '')))
            try:
                raw_m = getattr(row, '会计月', '')
                m_str = str(raw_m)
                if hasattr(raw_m, 'strftime'): m_str = raw_m.strftime('%Y-%m')
                elif ' ' in m_str: m_str = m_str.split(' ')[0][:7]
                t_str = str(getattr(row, '凭证种类', '')).strip()
                n_str = str(getattr(row, '凭证编号', '')).strip()
                if t_str and t_str != 'nan':
                    full_voucher = f"{m_str}-{t_str}-{n_str}"
                else:
                    full_voucher = f"{m_str}-{n_str}"
            except Exception:
                full_voucher = f"{getattr(row, '会计月', '')}-{getattr(row, '凭证编号', '')}"

            anomaly_patterns.append({
                "借方科目": debit_subj,
                "贷方科目": credit_subj,
                "业务描述": desc,
                "金额": total_amt,
                "完整凭证": full_voucher
            })

    if anomaly_rows:
        anomaly_df = pd.DataFrame(anomaly_rows)
        if '会计月' in anomaly_df.columns and '凭证编号' in anomaly_df.columns:
             anomaly_df.sort_values(by=['会计月', '凭证编号'], ascending=[False, False], inplace=True)
        logger.info(f"检测到 {len(anomaly_rows)} 笔异常分录 (金额 > {threshold})")
    else:
        anomaly_df = pd.DataFrame(columns=out_df.columns)
        logger.info("未检测到符合条件的异常分录。")

    aggregated_patterns = pd.DataFrame()
    if anomaly_patterns:
        pat_df = pd.DataFrame(anomaly_patterns)
        pat_df.sort_values(by='金额', ascending=False, kind='mergesort', inplace=True)
        agg_rules = {'金额': 'sum', '业务描述': 'first', '完整凭证': 'first'}
        grouped_pat = pat_df.groupby(['借方科目', '贷方科目'], as_index=False).agg(agg_rules)
        grouped_pat['异常类型编号'] = range(1, len(grouped_pat) + 1)
        grouped_pat.rename(columns={'完整凭证': '凭证编号'}, inplace=True)
        cols_order = ['借方科目', '贷方科目', '业务描述', '金额', '凭证编号', '异常类型编号']
        aggregated_patterns = grouped_pat[cols_order]
    else:
        aggregated_patterns = pd.DataFrame(columns=['借方科目', '贷方科目', '业务描述', '金额', '凭证编号', '异常类型编号'])

    if not anomaly_df.empty and not aggregated_patterns.empty:
        mapping_df = aggregated_patterns[['借方科目', '贷方科目', '异常类型编号']]
        anomaly_df = pd.merge(
            anomaly_df,
            mapping_df,
            left_on=['__debit_key', '__credit_key'],
            right_on=['借方科目', '贷方科目'],
            how='left'
        )
        drop_cols = ['__debit_key', '__credit_key', '借方科目', '贷方科目']
        anomaly_df.drop(columns=[c for c in drop_cols if c in anomaly_df.columns], inplace=True)

    return anomaly_df, aggregated_patterns


def analyze_benford(df: pd.DataFrame) -> pd.DataFrame:
    """班福定律分析。"""
    logger.info("正在计算原始数据的首位数...")
    temp_amount = df['借方发生额'].abs() + df['贷方发生额'].abs()
    # 将首位数写入 df，用于原始数据 sheet 输出（writer.py 中已从生成结果 sheet 排除）
    df['首位数'] = temp_amount.apply(get_leading_digit)

    stats_data = []
    valid_digits = df['首位数'].dropna()
    total_count = len(valid_digits)
    for d in range(1, 10):
        count = (valid_digits == d).sum()
        actual_pct = count / total_count if total_count > 0 else 0
        benford_pct = math.log10(1 + 1/d)
        stats_data.append({
            "首位数": d,
            "出现次数": count,
            "出现比率": actual_pct,
            "班福比率": benford_pct
        })
    stats_df = pd.DataFrame(stats_data)
    sum_row = pd.DataFrame([{
        "首位数": "合计",
        "出现次数": stats_df["出现次数"].sum(),
        "出现比率": stats_df["出现比率"].sum(),
        "班福比率": stats_df["班福比率"].sum()
    }])
    stats_df = pd.concat([stats_df, sum_row], ignore_index=True)
    return stats_df

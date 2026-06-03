# -*- coding: utf-8 -*-
"""数据校验模块"""
import pandas as pd

from ..utils.logger import logger

# 金额校验阈值
AMOUNT_CHECK_THRESHOLD = 0.01
# 发生额有效值判断阈值
AMOUNT_VALID_THRESHOLD = 1e-6
REQUIRED_OUTPUT_COLUMNS = ['借方发生额', '贷方发生额', '对方科目']


def validate_results(df: pd.DataFrame, out_df: pd.DataFrame,
                     progress_callback=None):
    """
    验证结果的完整性。

    :param df: 原始数据
    :param out_df: 生成结果
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    """
    logger.info("正在进行数据完整性校验...")
    if progress_callback:
        progress_callback(95, "正在校验数据...", "数据校验")

    if out_df is None:
        out_df = pd.DataFrame()
    for col in REQUIRED_OUTPUT_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = pd.Series(dtype='object' if col == '对方科目' else 'float64')

    orig_debit_sum = df['借方发生额'].sum()
    orig_credit_sum = df['贷方发生额'].sum()
    out_debit_sum = out_df['借方发生额'].sum()
    out_credit_sum = out_df['贷方发生额'].sum()
    diff_debit = abs(orig_debit_sum - out_debit_sum)
    diff_credit = abs(orig_credit_sum - out_credit_sum)

    logger.info(f"原借方合计: {orig_debit_sum:,.2f}, 新借方合计: {out_debit_sum:,.2f}, 差额: {diff_debit:,.2f}")
    logger.info(f"原贷方合计: {orig_credit_sum:,.2f}, 新贷方合计: {out_credit_sum:,.2f}, 差额: {diff_credit:,.2f}")

    if diff_debit > AMOUNT_CHECK_THRESHOLD or diff_credit > AMOUNT_CHECK_THRESHOLD:
        logger.warning("严重警告：金额合计不一致！请检查生成逻辑。")
        if progress_callback:
            progress_callback(96, "警告：金额校验失败", "校验失败")
    else:
        logger.info("金额校验通过。")

    valid_rows = out_df[(abs(out_df['借方发生额']) > AMOUNT_VALID_THRESHOLD) | (abs(out_df['贷方发生额']) > AMOUNT_VALID_THRESHOLD)]
    empty_contra = valid_rows[valid_rows['对方科目'].isnull() | (valid_rows['对方科目'] == '')]
    if not empty_contra.empty:
        logger.warning(f"警告：发现 {len(empty_contra)} 行有发生额但无对方科目！")
        if progress_callback:
            progress_callback(96, "警告：对方科目缺失", "校验失败")

    multi_contra = valid_rows[valid_rows['对方科目'].astype(str).str.contains(',')]
    if not multi_contra.empty:
        logger.warning(f"警告：发现 {len(multi_contra)} 行包含多个对方科目（含逗号）！")
        if progress_callback:
            progress_callback(96, "警告：对方科目未拆分", "校验失败")

    if empty_contra.empty and multi_contra.empty:
        logger.info("对方科目格式校验通过。")

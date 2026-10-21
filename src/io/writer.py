# -*- coding: utf-8 -*-
"""数据输出模块 — 摩根系 deep-navy 标准 + 班福图表"""
from typing import List, Dict, Callable, Optional

import pandas as pd

from make_excel import make_excel

from ..utils.logger import logger


def _col_letter(n):
    """1 基列号 -> 列字母。"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _benford_chart_def(col_base=2):
    """班福折线图定义：分类=首位数列，系列=比率两列（首行为名称）。"""
    col = _col_letter(col_base)
    ratio = _col_letter(col_base + 2)
    bench = _col_letter(col_base + 3)
    return {"类型": "折线", "位置": "H2",
            "标题": "班福定律分析 - 首位数分布",
            "X轴标题": "首位数", "Y轴标题": "比率",
            "分类引用": "'班福分析'!%s2:%s10" % (col, col),
            "系列": ["'班福分析'!%s1:%s10" % (ratio, ratio),
                     "'班福分析'!%s1:%s10" % (bench, bench)]}


def save_output_file(output_path: str, df: pd.DataFrame, out_df: pd.DataFrame,
                     anomaly_df: pd.DataFrame, aggregated_patterns: pd.DataFrame,
                     stats_df: pd.DataFrame, failed_groups: List[Dict],
                     progress_callback: Optional[Callable] = None, screening_sheets=None) -> bool:
    """
    保存结果到 Excel（摩根系 deep-navy 标准格式）。

    :param output_path: 输出文件路径
    :param df: 原始数据
    :param out_df: 生成结果
    :param anomaly_df: 异常分录明细
    :param aggregated_patterns: 异常分录汇总
    :param stats_df: 班福分析数据
    :param failed_groups: 失败分组列表
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    :return: 是否保存成功
    """
    logger.info(f"正在保存文件到: {output_path}")
    if progress_callback:
        progress_callback(92, "正在保存Excel文件...", "文件输出")

    try:
        logger.info("正在写入Excel文件(包含多个Sheet及图表)...")

        # ── 整理列顺序（账套列如果存在则放在最前面）──
        ledger_col = df.attrs.get('ledger_column', None)
        cols = []
        if ledger_col and ledger_col in out_df.columns:
            cols.append(ledger_col)
        cols.extend(['记账时间', '会计月', '凭证种类', '凭证编号', '编号', '业务说明', '一级编号', '一级科目', '科目编号', '科目名称', '借方发生额', '贷方发生额', '对方科目', '匹配类型'])
        for c in df.columns:
            if c not in cols and c != '首位数': cols.append(c)
        final_cols = [c for c in cols if c in out_df.columns]
        out_df = out_df[final_cols]

        # ── 构建多 Sheet 数据 ──
        sheets = [
            ('生成结果', out_df),
            ('原始数据', df),
        ]

        if not anomaly_df.empty:
            sheets.append(('异常分录明细', anomaly_df))
        else:
            sheets.append(('异常分录明细', pd.DataFrame({"提示": ["未检测到符合阈值的异常分录"]})))

        if isinstance(aggregated_patterns, pd.DataFrame) and not aggregated_patterns.empty:
            sheets.append(('异常分录', aggregated_patterns))
        else:
            # make_excel 会跳过空表，用提示行保证 sheet 一定存在
            sheets.append(('异常分录', pd.DataFrame({"提示": ["未检测到符合阈值的异常分录"]})))

        if failed_groups:
            sheets.append(('失败分组', pd.DataFrame(failed_groups)))

        sheets.append(('班福分析', stats_df))
        sheets.extend((screening_sheets or {}).items())

        # ── 使用 make_excel 生成摩根系标准格式，班福图随写入一次成型 ──
        def add_benford_chart(plans):
            for tp in plans:
                if tp.名称 == '班福分析':
                    tp.图表 = [_benford_chart_def(2)]

        make_excel(sheets, output_path, postprocess=add_benford_chart)

        logger.info("完成。")
        if progress_callback:
            progress_callback(100, "处理完成", "完成")
        return True
    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        if progress_callback:
            progress_callback(0, "保存失败", "错误")
        return False

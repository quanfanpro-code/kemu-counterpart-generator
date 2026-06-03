# -*- coding: utf-8 -*-
"""数据输出模块"""
from typing import List, Dict, Callable, Optional

import pandas as pd

try:
    from openpyxl.chart import LineChart, Reference
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    LineChart = Reference = get_column_letter = None

from ..utils.logger import logger


def save_output_file(output_path: str, df: pd.DataFrame, out_df: pd.DataFrame,
                     anomaly_df: pd.DataFrame, aggregated_patterns: pd.DataFrame,
                     stats_df: pd.DataFrame, failed_groups: List[Dict],
                     progress_callback: Optional[Callable] = None):
    """
    保存结果到 Excel。

    :param output_path: 输出文件路径
    :param df: 原始数据
    :param out_df: 生成结果
    :param anomaly_df: 异常分录明细
    :param aggregated_patterns: 异常分录汇总
    :param stats_df: 班福分析数据
    :param failed_groups: 失败分组列表
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    """
    logger.info(f"正在保存文件到: {output_path}")
    if progress_callback:
        progress_callback(92, "正在保存Excel文件...", "文件输出")

    if not OPENPYXL_AVAILABLE:
        logger.error("错误: openpyxl库未安装，无法生成Excel文件。请运行: pip install openpyxl")
        if progress_callback:
            progress_callback(0, "保存失败", "错误")
        return

    try:
        logger.info("正在写入Excel文件(包含多个Sheet及图表)...")
        # 整理列顺序（账套列如果存在则放在最前面）
        ledger_col = df.attrs.get('ledger_column', None)
        cols = []
        if ledger_col and ledger_col in out_df.columns:
            cols.append(ledger_col)
        cols.extend(['记账时间', '会计月', '凭证种类', '凭证编号', '编号', '业务说明', '一级编号', '一级科目', '科目编号', '科目名称', '借方发生额', '贷方发生额', '对方科目', '匹配类型'])
        for c in df.columns:
            if c not in cols and c != '首位数': cols.append(c)
        final_cols = [c for c in cols if c in out_df.columns]
        out_df = out_df[final_cols]

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            out_df.to_excel(writer, sheet_name='生成结果', index=False)
            df.to_excel(writer, sheet_name='原始数据', index=False)

            if not anomaly_df.empty:
                anomaly_df.to_excel(writer, sheet_name='异常分录明细', index=False)
            else:
                pd.DataFrame({"提示": ["未检测到符合阈值的异常分录"]}).to_excel(writer, sheet_name='异常分录明细', index=False)

            if isinstance(aggregated_patterns, pd.DataFrame) and not aggregated_patterns.empty:
                aggregated_patterns.to_excel(writer, sheet_name='异常分录', index=False)
            else:
                pd.DataFrame(columns=['借方科目', '贷方科目', '业务描述', '金额', '凭证编号', '异常类型编号']).to_excel(writer, sheet_name='异常分录', index=False)

            if failed_groups:
                pd.DataFrame(failed_groups).to_excel(writer, sheet_name='失败分组', index=False)

            stats_sheet_name = '班福分析'
            stats_df.to_excel(writer, sheet_name=stats_sheet_name, index=False)
            stats_ws = writer.sheets[stats_sheet_name]

            for row in range(2, 12):
                for col in (3, 4):
                    cell = stats_ws.cell(row=row, column=col)
                    cell.number_format = '0.00%'

            chart = LineChart()
            chart.title = "班福定律分析 - 首位数分布"
            chart.style = 13
            chart.y_axis.title = "比率"
            chart.x_axis.title = "首位数"
            cats = Reference(stats_ws, min_col=1, min_row=2, max_row=10)
            data = Reference(stats_ws, min_col=3, min_row=1, max_row=10, max_col=4)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(cats)
            stats_ws.add_chart(chart, "F2")

        logger.info("完成。")
        if progress_callback:
            progress_callback(100, "处理完成", "完成")
    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        if progress_callback:
            progress_callback(0, "保存失败", "错误")

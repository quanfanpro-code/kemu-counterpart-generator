# -*- coding: utf-8 -*-
"""序时账分析器 - 纯命令行版（给 agent / 脚本自动调用，不依赖图形界面）。

用法：
    序时账分析器命令行版.py 输入.xlsx 输出.xlsx [--threshold 10000] [--mode summary|full]

说明：
    - 复用项目 src 核心算法，不修改任何现有代码。
    - summary 模式（默认）：只输出一张"生成结果"表（含对方科目、匹配类型列）。
    - full 模式：输出全部 sheet（普通格式，无图表、无美化）。
    - 不依赖 customtkinter 等 GUI 库。
    - 非交互：列识别失败直接报错退出，退出码 1。
"""
import sys
import argparse
import logging
from pathlib import Path

# 开发模式下把项目根加入搜索路径；打包成 exe 后 PyInstaller 已处理依赖
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.utils.logger import setup_logger, logger
from src.io.reader import load_and_preprocess_data
from src.pipeline.orchestrator import perform_processing
from src.pipeline.validator import validate_results
from src.pipeline.anomaly import detect_anomalies, analyze_benford


def _整理生成结果列(out_df: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """整理"生成结果"表的列顺序（账套列置首），与原版保持一致。"""
    ledger_col = df.attrs.get('ledger_column')
    cols = []
    if ledger_col and ledger_col in out_df.columns:
        cols.append(ledger_col)
    for c in ['记账时间', '会计月', '凭证种类', '凭证编号', '编号', '业务说明',
              '一级编号', '一级科目', '科目编号', '科目名称',
              '借方发生额', '贷方发生额', '对方科目', '匹配类型']:
        if c not in cols:
            cols.append(c)
    for c in df.columns:
        if c not in cols and c != '首位数':
            cols.append(c)
    return out_df[[c for c in cols if c in out_df.columns]]


def _保存精简模式(output_path: str, df: pd.DataFrame, out_df: pd.DataFrame) -> None:
    """summary：只输出一张"生成结果"表，普通格式。"""
    _整理生成结果列(out_df, df).to_excel(
        output_path, sheet_name='生成结果', index=False, engine='openpyxl')


def _保存完整模式(output_path: str, df: pd.DataFrame, out_df: pd.DataFrame,
                  anomaly_df: pd.DataFrame, aggregated_patterns: pd.DataFrame,
                  stats_df: pd.DataFrame, failed_groups: list) -> None:
    """full：输出全部 sheet，普通格式，无图表。"""
    out_df = _整理生成结果列(out_df, df)
    sheets = [('生成结果', out_df), ('原始数据', df)]
    if not anomaly_df.empty:
        sheets.append(('异常分录明细', anomaly_df))
    else:
        sheets.append(('异常分录明细', pd.DataFrame({"提示": ["未检测到符合阈值的异常分录"]})))
    if isinstance(aggregated_patterns, pd.DataFrame) and not aggregated_patterns.empty:
        sheets.append(('异常分录', aggregated_patterns))
    else:
        sheets.append(('异常分录', pd.DataFrame({"提示": ["未检测到符合阈值的异常分录"]})))
    if failed_groups:
        sheets.append(('失败分组', pd.DataFrame(failed_groups)))
    sheets.append(('班福分析', stats_df))
    with pd.ExcelWriter(output_path, engine='openpyxl') as w:
        for name, sdf in sheets:
            sdf.to_excel(w, sheet_name=name, index=False)


def _交互选单(all_columns, required_columns, mapping):
    """命令行交互式列映射：对自动匹配不上的列逐列让用户选。"""
    print("\n" + "=" * 50)
    print("输入文件列名与所需列不完全匹配，请手动配置列映射。")
    print("文件中检测到的列：")
    for i, col in enumerate(all_columns, 1):
        print(f"  {i}. {col}")
    print("=" * 50)

    used = {v for v in mapping.values() if v != "无/不适用"}
    for req in required_columns:
        if req in mapping:
            continue
        while True:
            print(f"\n请为 [{req}] 选择对应的列：")
            for i, col in enumerate(all_columns, 1):
                mark = " (已用)" if col in used else ""
                print(f"  {i}. {col}{mark}")
            print("  0. 无/不适用")
            choice = input("> 输入序号: ").strip()
            try:
                idx = int(choice)
            except ValueError:
                print("请输入数字。")
                continue
            if idx == 0:
                mapping[req] = "无/不适用"
                break
            if 1 <= idx <= len(all_columns):
                col = all_columns[idx - 1]
                if col in used:
                    print(f"[{col}] 已被其他列使用，请重选。")
                    continue
                mapping[req] = col
                used.add(col)
                break
            print("序号超出范围。")
    return mapping


def _列映射(all_columns, required_columns, interactive):
    """先自动同名匹配，凭证种类缺失标不适用；仍缺的列在交互模式下逐列选。"""
    mapping = {}
    missing = []
    for req in required_columns:
        if req in all_columns:
            mapping[req] = req
        elif req == '凭证种类':
            mapping[req] = "无/不适用"
        else:
            missing.append(req)
    if not missing:
        return mapping
    logger.warning(f"输入文件缺少必要列: {missing}")
    if not interactive:
        for req in missing:
            logger.error(f"无法自动匹配列 [{req}]，加 -i / --interactive 手动选择。")
        return None
    return _交互选单(all_columns, required_columns, mapping)


def _处理(input_path: str, output_path: str, threshold: float, mode: str,
         interactive: bool = False) -> bool:
    """执行处理流水线并按模式输出。"""

    def _dialog(all_columns, required_columns):
        return _列映射(all_columns, required_columns, interactive)

    df = load_and_preprocess_data(input_path, interactive=False,
                                  column_mapping_dialog=_dialog)
    if df is None:
        logger.error("数据加载失败，退出。")
        return False

    out_df, failed_groups = perform_processing(df)
    validate_results(df, out_df)

    if mode == 'summary':
        _保存精简模式(output_path, df, out_df)
    else:
        anomaly_df, aggregated_patterns = detect_anomalies(out_df, threshold)
        stats_df = analyze_benford(df)
        _保存完整模式(output_path, df, out_df, anomaly_df, aggregated_patterns,
                     stats_df, failed_groups)

    logger.info(f"处理完成，结果已保存到: {output_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description='序时账分析器 - 纯命令行版 v2.0.8')
    parser.add_argument('input', help='输入 Excel 文件路径')
    parser.add_argument('output', help='输出 Excel 文件路径')
    parser.add_argument('--threshold', type=float, default=10000,
                        help='异常分录筛选阈值（默认10000）')
    parser.add_argument('--mode', choices=['summary', 'full'], default='summary',
                        help='输出模式：summary 只输出生成结果表（默认），full 输出全部 sheet')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别')
    parser.add_argument('-i', '--interactive', action='store_true',
                        help='列识别不出时弹命令行选单逐列选择（默认缺列直接报错）')
    args = parser.parse_args()

    setup_logger(level=getattr(logging, args.log_level))
    ok = _处理(args.input, args.output, args.threshold, args.mode, args.interactive)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()

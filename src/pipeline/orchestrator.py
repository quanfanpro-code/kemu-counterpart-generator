# -*- coding: utf-8 -*-
"""处理流水线编排模块"""
import os
import time
import traceback
from typing import Dict, List, Tuple, Callable, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from .group_processor import process_group
from .validator import validate_results
from .anomaly import detect_anomalies, analyze_benford
from ..io.reader import load_and_preprocess_data
from ..io.writer import save_output_file
from ..utils.logger import logger


def perform_processing(df: pd.DataFrame,
                       progress_callback: Optional[Callable] = None) -> Tuple[pd.DataFrame, List[Dict]]:
    """
    执行并行计算处理。

    :param df: 预处理后的数据
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    :return: (结果DataFrame, 失败分组列表)
    """
    group_cols = ['会计月', '凭证编号']
    type_stats = ""
    if '凭证种类' in df.columns:
        group_cols.insert(1, '凭证种类')
        type_stats = f", 凭证种类({df['凭证种类'].nunique()}个)"

    # 检测并添加账套列到分组条件
    ledger_col = df.attrs.get('ledger_column', None)
    if ledger_col and ledger_col in df.columns:
        group_cols.insert(0, ledger_col)
        type_stats = f", 账套({df[ledger_col].nunique()}个)" + type_stats

    logger.info(f"分组字段唯一值统计: 会计月({df['会计月'].nunique()}个){type_stats}, 凭证编号({df['凭证编号'].nunique()}个)")
    grouped = df.groupby(group_cols)
    total_groups = len(grouped)

    if df['会计月'].nunique() < 2 and total_groups > 10:
        logger.warning("警告：检测到【会计月】列只有一个唯一值，如果您的数据包含多个月份，说明月份列可能被错误修改或覆盖！")

    tasks = [(name, group) for name, group in grouped]
    output_rows = []
    failed_groups = []
    processed_count = 0
    start_pct = 15
    end_pct = 90
    max_workers = max(1, (os.cpu_count() or 4) - 1)
    logger.info(f"启动 {max_workers} 个进程进行并行计算...")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_group, task): task for task in tasks}
        for future in as_completed(futures):
            try:
                result = future.result()
                output_rows.extend(result)
            except Exception as e:
                task_name = futures[future][0]
                logger.error(f"处理分组 {task_name} 失败: {e}")
                traceback.print_exc()
                failed_groups.append({
                    "分组键": str(task_name),
                    "错误": str(e),
                    "堆栈": traceback.format_exc()
                })

            processed_count += 1
            if processed_count % 100 == 0 or processed_count == total_groups:
                current_pct = start_pct + (processed_count / total_groups) * (end_pct - start_pct)
                if progress_callback:
                    progress_callback(current_pct, f"已处理 {processed_count}/{total_groups}", "并行计算中")

    logger.info(f"生成输出数据，共 {len(output_rows)} 行...")
    out_df = pd.DataFrame(output_rows)
    return out_df, failed_groups


def run_processing_pipeline(df: pd.DataFrame, anomaly_threshold: float, output_path: str,
                            progress_callback: Optional[Callable] = None):
    """
    执行核心处理流水线（适合在工作线程中运行）。

    :param df: 预处理后的数据
    :param anomaly_threshold: 异常金额阈值
    :param output_path: 输出文件路径
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    """
    # 3. 执行处理
    pipeline_start = time.time()
    out_df, failed_groups = perform_processing(df, progress_callback=progress_callback)

    # 4. 验证结果
    validate_results(df, out_df, progress_callback=progress_callback)

    # 5. 检测异常
    anomaly_df, aggregated_patterns = detect_anomalies(out_df, anomaly_threshold)

    # 6. 班福分析
    stats_df = analyze_benford(df)

    # 7. 保存结果
    save_output_file(output_path, df, out_df, anomaly_df, aggregated_patterns, stats_df, failed_groups,
                     progress_callback=progress_callback)

    # 8. 输出统计摘要
    pipeline_elapsed = time.time() - pipeline_start
    total_input_rows = len(df)
    total_output_rows = len(out_df)
    matched_count = len(out_df[out_df['匹配类型'] == '标准模板']) if '匹配类型' in out_df.columns else 0
    algo_count = len(out_df[out_df['匹配类型'] == '算法生成']) if '匹配类型' in out_df.columns else 0
    fallback_count = len(out_df[(out_df['匹配类型'].str.contains('兜底拆分|异常剩余', na=False))]) if '匹配类型' in out_df.columns else 0

    logger.info("=" * 50)
    logger.info(f"📊 处理统计摘要")
    logger.info(f"  输入数据行数: {total_input_rows}")
    logger.info(f"  输出数据行数: {total_output_rows}")
    logger.info(f"  标准模板匹配: {matched_count} 行")
    logger.info(f"  算法金额匹配: {algo_count} 行")
    logger.info(f"  兜底/异常处理: {fallback_count} 行")
    logger.info(f"  失败分组数: {len(failed_groups)}")
    logger.info(f"  总耗时: {pipeline_elapsed:.2f} 秒")
    logger.info("=" * 50)


def generate_contra_account(input_path: str, output_path: str,
                            interactive: bool = False,
                            anomaly_threshold: float = 10000):
    """
    CLI 入口函数：从文件读取 → 处理 → 保存结果。

    :param input_path: 输入 Excel 文件路径
    :param output_path: 输出 Excel 文件路径
    :param interactive: 是否交互模式（CLI 下为 False）
    :param anomaly_threshold: 异常金额阈值
    """
    df = load_and_preprocess_data(input_path, interactive=interactive)
    if df is None:
        logger.error("数据加载失败，退出。")
        return
    run_processing_pipeline(df, anomaly_threshold, output_path)

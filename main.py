# -*- coding: utf-8 -*-
"""对方科目生成工具 - 程序入口"""
import sys
import multiprocessing
import argparse


def _auto_column_mapping(all_columns, required_columns):
    """CLI 模式列映射：同名自动对应，凭证种类缺失按"无/不适用"处理。"""
    mapping = {}
    for req in required_columns:
        if req in all_columns:
            mapping[req] = req
        elif req == '凭证种类':
            mapping[req] = "无/不适用"
        else:
            return None
    return mapping


def main():
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='序时账对方科目生成工具 v2.2.1')
    parser.add_argument('input', nargs='?', help='输入 Excel 文件路径')
    parser.add_argument('output', nargs='?', help='输出 Excel 文件路径')
    parser.add_argument('--threshold', type=float, default=10000,
                        help='异常分录筛选阈值（默认10000）')
    parser.add_argument('--no-gui', action='store_true',
                        help='强制 CLI 模式（不启动图形界面）')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别')
    from src.pipeline.凭证筛选 import add_screening_arguments, options_from_args
    add_screening_arguments(parser)
    args = parser.parse_args()

    if args.input and args.output:
        # CLI 模式
        from src.utils.logger import setup_logger, logger
        import logging
        setup_logger(level=getattr(logging, args.log_level))
        from src.io.reader import load_and_preprocess_data
        from src.pipeline.orchestrator import run_processing_pipeline
        df = load_and_preprocess_data(args.input, interactive=False,
                                      column_mapping_dialog=_auto_column_mapping)
        if df is None:
            logger.error("数据加载失败，退出。")
            ok = False
        else:
            ok = run_processing_pipeline(df, args.threshold, args.output, screening_options=options_from_args(args))
        sys.exit(0 if ok else 1)
    elif args.no_gui:
        parser.error('--no-gui 模式需要同时提供输入和输出文件路径')
    else:
        # GUI 模式
        from src.gui.app import run_gui
        run_gui()


if __name__ == "__main__":
    main()

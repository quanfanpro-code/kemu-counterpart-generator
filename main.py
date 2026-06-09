# -*- coding: utf-8 -*-
"""对方科目生成工具 - 程序入口"""
import sys
import multiprocessing
import argparse


def main():
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description='序时账对方科目生成工具 v2.0.5')
    parser.add_argument('input', nargs='?', help='输入 Excel 文件路径')
    parser.add_argument('output', nargs='?', help='输出 Excel 文件路径')
    parser.add_argument('--threshold', type=float, default=10000,
                        help='异常分录筛选阈值（默认10000）')
    parser.add_argument('--no-gui', action='store_true',
                        help='强制 CLI 模式（不启动图形界面）')
    parser.add_argument('--log-level', default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别')
    args = parser.parse_args()

    if args.input and args.output:
        # CLI 模式
        from src.utils.logger import setup_logger
        import logging
        setup_logger(level=getattr(logging, args.log_level))
        from src.pipeline.orchestrator import generate_contra_account
        generate_contra_account(args.input, args.output, interactive=False,
                                anomaly_threshold=args.threshold)
    else:
        # GUI 模式
        from src.gui.app import run_gui
        run_gui()


if __name__ == "__main__":
    main()

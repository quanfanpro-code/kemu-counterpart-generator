"""逐份处理文件夹内的序时账，原始资料不变，配置只在本批次复用。"""
import csv
import logging
import math
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from src.io.reader import load_and_preprocess_data
from src.pipeline.orchestrator import run_processing_pipeline
from src.utils.logger import logger


def scan_ledger_files(folder, recursive=False):
    """固定候选清单，排除临时文件和本工具历史输出，不跟随目录链接。"""
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError("请选择存在的文件夹")
    files = []
    def scan_error(error):
        raise error
    for directory, dirs, names in os.walk(root, onerror=scan_error, followlinks=False):
        dirs[:] = [name for name in dirs
                   if not re.fullmatch(r"批处理结果_\d{8}_\d{6}(?:_\d+)?", name)
                   and not (Path(directory) / name).is_symlink()
                   and not (Path(directory) / name).is_junction()]
        for name in names:
            path = Path(directory) / name
            if (path.suffix.lower() in (".xlsx", ".xls")
                    and not name.startswith("~$") and "生成对方科目" not in path.stem
                    and not path.is_symlink()):
                files.append(path)
        if not recursive:
            break
    return sorted(files, key=lambda p: str(p.relative_to(root)).casefold())


class _FileErrors(logging.Handler):
    """仅收集本工作线程的错误，作为逐文件失败原因。"""
    def __init__(self):
        super().__init__(logging.ERROR)
        self.thread_id = threading.get_ident()
        self.messages = []

    def emit(self, record):
        if record.thread == self.thread_id:
            self.messages.append(record.getMessage())


def _save_manifest(folder, records):
    """带签名 UTF-8 可由 Excel 打开，文本前缀防止被解释为公式。"""
    def safe_text(value):
        text = str(value)
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    temporary = folder / "~$批处理清单.csv"
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["来源文件", "状态", "结果文件", "原因"])
        writer.writeheader()
        writer.writerows({key: safe_text(value) for key, value in row.items()} for row in records)
    temporary.replace(folder / "批处理清单.csv")


def run_batch(folder, recursive=False, anomaly_threshold=10000, mapping_dialog=None,
              screening_dialog=None, progress_callback=None):
    """返回结果目录与逐文件记录；可选配置回调由桌面转交给主线程。"""
    if not math.isfinite(anomaly_threshold) or anomaly_threshold < 0:
        raise ValueError("异常金额阈值必须为非负有限数字")
    root = Path(folder).resolve()
    files = scan_ledger_files(root, recursive)
    if not files:
        return {"output_dir": None, "records": []}
    while True:
        output_dir = root / ("批处理结果_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        try:
            output_dir.mkdir()
            break
        except FileExistsError:
            continue
    records = [{"来源文件": str(p.relative_to(root)), "状态": "未处理",
                "结果文件": "", "原因": "尚未处理"} for p in files]
    _save_manifest(output_dir, records)
    mappings = {}
    used_targets = set()
    screening_options = {}
    screening_ready = screening_dialog is None
    errors = _FileErrors()
    logger.addHandler(errors)
    try:
        for index, source in enumerate(files):
            row = records[index]
            errors.messages.clear()
            relative = source.relative_to(root)
            def report(percent, message, phase=None):
                if progress_callback:
                    progress_callback((index + min(100, max(0, percent)) / 100) / len(files) * 100,
                                      f"{index + 1}/{len(files)} {relative}：{message}", phase)
            def mapping(columns, required):
                key = tuple(columns)
                if key not in mappings:
                    missing = [c for c in required if c not in columns and c != "凭证种类"]
                    if not missing:
                        mappings[key] = {c: c if c in columns else "无/不适用" for c in required}
                    else:
                        mappings[key] = mapping_dialog(columns, required) if mapping_dialog else None
                return mappings[key]
            try:
                report(0, "正在读取")
                df = load_and_preprocess_data(str(source), interactive=False,
                                              column_mapping_dialog=mapping, progress_callback=report)
                if df is None:
                    raise ValueError("；".join(errors.messages) or "列名对应未确认或读取预处理失败")
                if df.empty:
                    raise ValueError("没有可处理的数据行")
                if not screening_ready:
                    screening_options = screening_dialog(df)
                    if screening_options is None:
                        for pending in records[index:]:
                            pending["原因"] = "用户取消本批筛选设置，未处理"
                        _save_manifest(output_dir, records)
                        break
                    screening_ready = True
                target = output_dir / relative.parent / (source.stem + "生成对方科目.xlsx")
                # 按已分配路径去重，连输入名恰好带后缀的情况也不能碰撞。
                number = 2
                while str(target).casefold() in used_targets or target.exists():
                    target = target.with_name(f"{source.stem}生成对方科目_{number}.xlsx")
                    number += 1
                used_targets.add(str(target).casefold())
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name("~$未完成_" + target.name)
                ok = run_processing_pipeline(df, anomaly_threshold, str(temporary),
                                             progress_callback=report, screening_options=screening_options)
                if not ok or not temporary.is_file():
                    raise ValueError("；".join(errors.messages) or "结果保存失败")
                temporary.rename(target)
                row.update({"状态": "部分失败" if errors.messages else "成功",
                            "结果文件": str(target.relative_to(output_dir)),
                            "原因": "；".join(errors.messages)})
            except Exception as exc:
                row.update({"状态": "失败", "原因": str(exc)})
                logger.error(f"批处理文件 {relative} 失败：{exc}")
            _save_manifest(output_dir, records)
            report(100, row["状态"])
    finally:
        logger.removeHandler(errors)
        errors.close()
    return {"output_dir": output_dir, "records": records}

# -*- coding: utf-8 -*-
"""数据读取与预处理模块"""
import pandas as pd
from typing import Optional, Dict, List, Tuple

from ..utils.logger import logger

# 账套列识别关键词（用于多公司账套检测）
LEDGER_ACCOUNT_KEYWORDS = ['账套', '核算账套', '公司账套', '账套名', '公司名称', '核算主体', '主体名称']


def detect_ledger_account_column(columns: List[str]) -> Optional[str]:
    """
    检测账套列（支持多种列名变体）。

    :param columns: 文件列名列表
    :return: 检测到的账套列名，如果未找到返回 None
    """
    columns_lower = {str(col).lower().strip(): col for col in columns}
    for keyword in LEDGER_ACCOUNT_KEYWORDS:
        keyword_lower = keyword.lower()
        for col_lower, col_original in columns_lower.items():
            if keyword_lower in col_lower:
                return col_original
            if col_lower in keyword_lower:
                return col_original
        if keyword in columns:
            return keyword
    return None


def check_column_mapping_needed(input_path: str) -> Tuple[bool, List[str], List[str]]:
    """检查是否需要列映射，返回(是否需要映射, 文件列名, 缺少的列名)"""
    required_columns = ['会计月', '凭证种类', '凭证编号', '一级科目', '借方发生额', '贷方发生额']
    try:
        try:
            import python_calamine
            engine = 'calamine'
        except ImportError:
            engine = 'openpyxl'
        df = pd.read_excel(input_path, engine=engine, nrows=0)
        file_columns = list(df.columns)
        missing_cols = [col for col in required_columns if col not in file_columns]
        return len(missing_cols) > 0, file_columns, missing_cols
    except Exception as e:
        logger.warning(f"检查列名失败: {e}")
        return False, [], []


def apply_column_mapping(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    """应用列映射到DataFrame"""
    valid_mapping = {k: v for k, v in mapping.items() if v != "无/不适用"}
    df.rename(columns={v: k for k, v in valid_mapping.items()}, inplace=True)

    if mapping.get('凭证种类') == "无/不适用" and '凭证种类' in df.columns:
        df.drop(columns=['凭证种类'], inplace=True)

    return df


def load_and_preprocess_data(input_path: str, interactive: bool = False,
                              progress_callback=None,
                              column_mapping_dialog=None) -> Optional[pd.DataFrame]:
    """
    加载并预处理数据。

    :param input_path: 输入文件路径
    :param interactive: 是否交互模式
    :param progress_callback: 进度回调函数 callback(percent, message, phase)
    :param column_mapping_dialog: 列映射对话框函数，签名为
                                  f(all_columns, required_columns) -> Optional[Dict[str, str]]
    :return: 预处理后的 DataFrame，失败返回 None
    """
    if progress_callback:
        progress_callback(0, "初始化...", "准备阶段")
    logger.info(f"正在读取文件: {input_path}")
    if progress_callback:
        progress_callback(5, "正在读取Excel文件...", "数据读取")

    try:
        try:
            import python_calamine
            engine = 'calamine'
        except ImportError:
            engine = 'openpyxl'
        logger.info(f"使用读取引擎: {engine}")
        df = pd.read_excel(input_path, engine=engine)
        if progress_callback:
            progress_callback(15, "文件读取完成", "数据读取")
    except Exception as e:
        logger.error(f"读取Excel文件失败: {e}")
        if progress_callback:
            progress_callback(0, "读取失败", "错误")
        return None

    required_columns = ['会计月', '凭证种类', '凭证编号', '一级科目', '借方发生额', '贷方发生额']
    missing_cols = [col for col in required_columns if col not in df.columns]

    if missing_cols:
        logger.warning(f"输入文件缺少必要列: {missing_cols}")
        if column_mapping_dialog is not None:
            if progress_callback:
                progress_callback(16, "等待用户配置列映射...", "数据预处理")
            logger.info("等待用户手动配置列映射...")
            mapping = column_mapping_dialog(list(df.columns), required_columns)
            if mapping:
                logger.info(f"用户已配置列映射: {mapping}")
                valid_mapping = {k: v for k, v in mapping.items() if v != "无/不适用"}
                df.rename(columns={v: k for k, v in valid_mapping.items()}, inplace=True)

                if mapping.get('凭证种类') == "无/不适用" and '凭证种类' in df.columns:
                    logger.info("用户选择忽略凭证种类，正在移除该列...")
                    df.drop(columns=['凭证种类'], inplace=True)

                missing_cols = [col for col in required_columns if col not in df.columns]
                if '凭证种类' in missing_cols and mapping.get('凭证种类') == "无/不适用":
                    missing_cols.remove('凭证种类')

                if missing_cols:
                    logger.error(f"错误: 即使映射后仍缺少列: {missing_cols}")
                    return None
            else:
                logger.info("用户取消了列映射配置。")
                return None
        else:
            logger.error("错误: 缺少必要列且未启用交互模式或 GUI 不可用。")
            return None

    # 数据填充与清洗
    cols_to_ffill = ['会计月', '凭证种类', '凭证编号']

    # 检测账套列并加入填充列表
    ledger_col = detect_ledger_account_column(list(df.columns))
    if ledger_col:
        logger.info(f"检测到账套列: [{ledger_col}]，将作为分组条件之一")
        cols_to_ffill.insert(0, ledger_col)
        df.attrs['ledger_column'] = ledger_col
    else:
        df.attrs['ledger_column'] = None

    for col in cols_to_ffill:
        if col in df.columns:
            df[col] = df[col].replace(r'^\s*$', float('nan'), regex=True)
            if df[col].isnull().any():
                logger.info(f"检测到 [{col}] 列存在空值，正在尝试向下填充(处理合并单元格)...")
                df[col] = df[col].ffill()

    if '会计月' in df.columns:
        logger.info("注意：已禁用日期格式自动转换，将直接使用原文件中的[会计月]文本进行分组。")
        df['会计月'] = df['会计月'].astype(str).str.strip()

    df['借方发生额'] = pd.to_numeric(df['借方发生额'], errors='coerce').fillna(0)
    df['贷方发生额'] = pd.to_numeric(df['贷方发生额'], errors='coerce').fillna(0)

    logger.info("数据预处理完成。")
    return df

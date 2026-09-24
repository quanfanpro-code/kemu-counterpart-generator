"""主入口命令行模式对缺少可选列"凭证种类"的文件应与独立 CLI 行为一致。"""

import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def test_主命令行接受缺少凭证种类列的文件(tmp_path):
    source = pd.DataFrame([
        {"会计月": "2026-01", "凭证编号": "1", "一级科目": "银行存款", "借方发生额": 1000, "贷方发生额": 0},
        {"会计月": "2026-01", "凭证编号": "1", "一级科目": "主营业务收入", "借方发生额": 0, "贷方发生额": 1000},
    ])
    input_path = tmp_path / "无凭证种类.xlsx"
    output_path = tmp_path / "结果.xlsx"
    source.to_excel(input_path, index=False)

    finished = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"),
         str(input_path), str(output_path), "--no-gui", "--log-level", "ERROR"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=90,
    )

    assert finished.returncode == 0, finished.stderr
    assert output_path.is_file()
    result = pd.read_excel(output_path, sheet_name="生成结果")
    assert list(result["对方科目"]) == ["主营业务收入", "银行存款"]
    assert list(result["匹配类型"]) == ["标准模板", "标准模板"]


def test_主命令行对缺其他必需列仍然报错(tmp_path):
    source = pd.DataFrame([
        {"会计月": "2026-01", "凭证编号": "1", "一级科目": "银行存款", "贷方发生额": 1000},
    ])
    input_path = tmp_path / "缺借方列.xlsx"
    source.to_excel(input_path, index=False)

    finished = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(ROOT / "main.py"),
         str(input_path), str(tmp_path / "结果.xlsx"), "--no-gui", "--log-level", "ERROR"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=90,
    )

    assert finished.returncode == 1

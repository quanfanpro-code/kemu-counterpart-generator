# -*- coding: utf-8 -*-
"""冗余精简完成后必须满足的最小结构约束。"""
from __future__ import annotations

import inspect
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RedundancyContractTest(unittest.TestCase):
    def test_dead_column_mapper_removed(self):
        self.assertFalse((ROOT / "src/gui/column_mapper.py").exists())

    def test_legacy_precision_api_removed(self):
        import src.core.precision as precision

        for name in (
            "from_integer_li",
            "sum_amounts",
            "to_integer_cents",
            "from_integer_cents",
            "amounts_match_precision",
            "sum_amounts_precision",
        ):
            self.assertFalse(hasattr(precision, name), name)

    def test_single_subset_sum_entry(self):
        import src.core.algorithms as algorithms

        self.assertTrue(hasattr(algorithms, "solve_subset_sum"))
        self.assertFalse(hasattr(algorithms, "solve_subset_sum_mitm"))

    def test_old_pipeline_wrapper_removed(self):
        import src.pipeline.orchestrator as orchestrator

        self.assertFalse(hasattr(orchestrator, "generate_contra_account"))

    def test_make_excel_has_one_public_job(self):
        import make_excel

        self.assertFalse(hasattr(make_excel, "beautify"))
        self.assertFalse(hasattr(make_excel, "THEMES"))
        self.assertNotIn("theme", inspect.signature(make_excel.make_excel).parameters)

    def test_gui_duplicate_helpers_removed(self):
        import src.gui.log_redirector as log_redirector
        import src.gui.progress as progress

        self.assertFalse(hasattr(log_redirector, "GuiLogHandler"))
        self.assertFalse(hasattr(progress, "TerminalProgressBar"))
        self.assertFalse(hasattr(progress.GUI_PROGRESS, "set_gui_callback"))

    def test_processing_import_does_not_load_output_layer(self):
        code = (
            "import sys; "
            "from src.pipeline.orchestrator import perform_processing; "
            "assert 'make_excel' not in sys.modules; "
            "assert 'src.io.writer' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

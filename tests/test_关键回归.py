import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.pipeline.group_processor import process_group
from src.pipeline.orchestrator import run_processing_pipeline
from src.pipeline.validator import validate_results


class 关键回归测试(unittest.TestCase):
    def test_空输出校验不再崩溃(self):
        原始数据 = pd.DataFrame([{'借方发生额': 0.0, '贷方发生额': 0.0}])
        空输出 = pd.DataFrame()

        validate_results(原始数据, 空输出)

    def test_空输入流水线能够正常输出(self):
        空输入 = pd.DataFrame(columns=['会计月', '凭证编号', '一级科目', '借方发生额', '贷方发生额'])
        空输入['借方发生额'] = pd.Series(dtype='float64')
        空输入['贷方发生额'] = pd.Series(dtype='float64')

        with tempfile.TemporaryDirectory() as 临时目录:
            输出路径 = Path(临时目录) / '空输入结果.xlsx'
            run_processing_pipeline(空输入, 10000, str(输出路径))
            self.assertTrue(输出路径.exists())

    def test_多条损益科目不会再吞并到第一条(self):
        分组数据 = pd.DataFrame([
            {'会计月': '1月', '凭证编号': '001', '一级科目': '本年利润-甲', '借方发生额': 100.0, '贷方发生额': 0.0},
            {'会计月': '1月', '凭证编号': '001', '一级科目': '本年利润-乙', '借方发生额': 50.0, '贷方发生额': 0.0},
            {'会计月': '1月', '凭证编号': '001', '一级科目': '管理费用', '借方发生额': 0.0, '贷方发生额': 150.0},
        ])

        输出结果 = process_group((('1月', '001'), 分组数据))

        self.assertEqual(len(输出结果), 4)
        对方科目集合 = {(行['一级科目'], 行['对方科目']) for 行 in 输出结果}
        self.assertIn(('本年利润-甲', '管理费用'), 对方科目集合)
        self.assertIn(('本年利润-乙', '管理费用'), 对方科目集合)
        self.assertIn(('管理费用', '本年利润-甲'), 对方科目集合)
        self.assertIn(('管理费用', '本年利润-乙'), 对方科目集合)


if __name__ == '__main__':
    unittest.main()

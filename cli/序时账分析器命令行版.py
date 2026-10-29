# -*- coding: utf-8 -*-
"""主程序的无头入口，保留原源码路径供调用。"""
import sys
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import main


if __name__ == '__main__':
    sys.argv.append('--no-gui')
    main()

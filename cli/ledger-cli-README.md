# 主程序无头入口使用说明

当前源码版本：v2.5.0。

独立 CLI 已取消。`cli/序时账分析器命令行版.py` 现在只转调 `main.main()`，不再单独维护参数、处理或输出逻辑。**`cli/ledger-cli.exe` 是历史文件，不再维护，本次没有重新打包，也未加入本次源码改动。**

## 当前用法

在项目根目录运行：

```bash
python main.py 输入.xlsx 输出.xlsx --no-gui
python main.py 输入.xlsx 输出.xlsx --no-gui --mode summary
```

也可以通过旧源码路径转调主程序：

```bash
python cli/序时账分析器命令行版.py 输入.xlsx 输出.xlsx --mode summary
```

## 输出模式

| 参数 | 输出 | 默认值 |
|---|---|---|
| `--mode full` | 主程序完整结果，含美化和班福图表 | 是 |
| `--mode summary` | 普通“生成结果”表，无美化、无图表；显式启用筛选时追加筛选表 | 否 |

其他常用参数：

- `--threshold 50000`：异常分录筛选阈值，默认 `10000`。
- `--log-level ERROR`：减少日志输出，默认 `INFO`。
- 夜间、休息日、节假日和疑似拆分审批筛选参数见项目根 `README.md` 第 3.5 节。

处理成功返回退出码 `0`，处理失败返回 `1`；命令行参数错误由 argparse 返回 `2`。无头模式不会启动图形界面。

## 给 Agent 的注意事项

1. 日志和命令行参数按 UTF-8 处理。
2. 自动调用不要只给 `--no-gui` 而省略输入、输出路径，否则会收到参数错误。
3. 输入必需列和金额校验与主程序一致，不再有独立 CLI 的 `-i` 交互选单。
4. 不需要安装 Microsoft Excel；源码运行需要项目 `requirements.txt` 中的依赖。

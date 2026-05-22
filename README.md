# 对方科目生成工具 | Kemu Counterpart Generator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-v1.8.0-green.svg)](https://github.com/quanfanpro-code/kemu-counterpart-generator)

**[English](#english) | [中文](#中文)**

---

<a id="中文"></a>

## 这是什么？

一个**序时账对方科目自动生成工具**——给它一张序时账表格，它帮你把每一行分录的"对方科目"填上。

举个例子：

| 会计月 | 凭证编号 | 一级科目 | 借方发生额 | 贷方发生额 | 对方科目 | 匹配类型 |
|-------|---------|---------|-----------|-----------|---------|---------|
| 1月 | 记-001 | 银行存款 | 10000 | 0 | 应收账款 | 标准模板 |
| 1月 | 记-001 | 应收账款 | 0 | 10000 | 银行存款 | 标准模板 |

**多出来的"对方科目"列**，告诉你这笔钱的来龙去脉。

## 适合谁用？

| 人群 | 用途 |
|------|------|
| 审计人员 | 快速分析被审计单位的分录合理性 |
| 会计人员 | 检查自己做的账有没有问题 |
| 财务分析人员 | 分析资金流向和业务模式 |
| 税务稽查人员 | 发现可疑的异常分录 |

## 功能特性

- **自动匹配对方科目**：分析借贷关系，自动填上对方科目
- **异常分录检测**：找出金额大、不符合常规的可疑分录
- **班福定律分析**：检测数据是否被人为修改过
- **多公司账套支持**：一个文件包含多个公司的账也能处理
- **多核并行计算**：大数据量也能快速处理
- **折半枚举算法（MITM）**：核心算法复杂度从 O(2^N) 降至 O(2^(N/2))，支持36条候选分录

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行程序

```bash
python 对方科目生成.py
```

程序会弹出一个图形界面窗口，选择你的序时账 Excel 文件即可开始处理。

### 准备你的文件

你的序时账文件必须包含以下列：

| 列名 | 说明 |
|------|------|
| 会计月 | 月份（1月、1、2024-01 均可） |
| 凭证编号 | 凭证号（1、001、记-001） |
| 一级科目 | 会计科目名称 |
| 借方发生额 | 借方金额 |
| 贷方发生额 | 贷方金额 |

可选列：凭证种类、账套（多公司时使用）

### 输出结果

处理完成后，生成的新文件包含以下工作表：

| 工作表 | 内容 |
|--------|------|
| 生成结果 | 处理后的数据，多了"对方科目"和"匹配类型"两列 |
| 原始数据 | 原始数据备份 |
| 异常分录明细 | 金额大且不符合规则的分录 |
| 异常分录 | 异常分录按类型汇总 |
| 班福分析 | 数据造假分析，带折线图 |

## 算法原理

### 四阶段匹配流程

1. **阶段0：结转损益特殊规则**（最高优先级）——识别"本年利润""利润分配"等科目
2. **阶段1：标准模板匹配**——内置200+条常见会计分录规则
3. **阶段2：算法金额匹配**——纯金额配对，用凑数字算法找组合
4. **阶段3：兜底拆分**——剩余借贷方按顺序配对

### 折半枚举算法（MITM）

将候选数组从中间切开，左右两半分别穷举所有组合，再用二分查找匹配。时间复杂度从 O(2^N) 降至 O(2^(N/2) × log(2^(N/2)))，稳定支持36条候选分录。

### 金融级精度引擎

所有金额乘以10000转换为整数"厘"进行计算，避免浮点精度问题。默认容差0.01元（1分）。

## 匹配类型可信度

| 匹配类型 | 可信度 | 说明 |
|---------|-------|------|
| 标准模板 | 最高 | 符合会计准则的标准分录 |
| 结转损益规则 | 很高 | 识别为损益结转分录 |
| 算法生成 | 中等 | 金额配对成功，科目关系待确认 |
| 算法生成（兜底拆分） | 较低 | 复杂分录的拆分结果，建议复核 |
| 算法生成（异常剩余） | 最低 | 实在匹配不上，建议重点检查 |

## 详细文档

完整使用说明请参阅 [对方科目生成.md](对方科目生成.md)

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<a id="english"></a>

## What is this?

A **journal entry counterpart account generator** — feed it a chronological journal (序时账), and it automatically fills in the "counterpart account" (对方科目) for each entry line.

## Features

- **Auto-match counterpart accounts** based on debit-credit relationships
- **Anomalous entry detection** — flags large or unusual transactions
- **Benford's Law analysis** — detects potential data manipulation
- **Multi-company support** — handles files with multiple accounting entities
- **Multi-core parallel processing** for large datasets
- **Meet-in-the-Middle (MITM) algorithm** — O(2^(N/2)) complexity, handles up to 36 candidate entries

## Quick Start

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python 对方科目生成.py
```

A GUI window will open. Select your journal entry Excel file to begin processing.

### Input file requirements

Your journal file must contain these columns:

| Column | Description |
|--------|-------------|
| 会计月 (Period) | Month/period (e.g., 1月, 1, 2024-01) |
| 凭证编号 (Voucher No.) | Voucher number |
| 一级科目 (Account) | Account name |
| 借方发生额 (Debit) | Debit amount |
| 贷方发生额 (Credit) | Credit amount |

Optional: 凭证种类 (Voucher Type), 账套 (Company/Ledger)

## Algorithm

The tool uses a four-phase matching process:

1. **P&L closing rules** — special handling for profit/loss closing entries
2. **Standard template matching** — 200+ built-in accounting entry rules
3. **Amount-based algorithmic matching** — subset sum with MITM optimization
4. **Fallback splitting** — sequential pairing for remaining entries

The MITM (Meet-in-the-Middle) algorithm splits the candidate array in half, enumerates all combinations for each half, then uses binary search to find matches — reducing complexity from O(2^N) to O(2^(N/2)).

## License

This project is licensed under the [MIT License](LICENSE).

"""核对摘要明确引用的旧凭证，隔开冲销分录与新业务。"""

from collections import Counter, defaultdict
from datetime import date, datetime
import re
import unicodedata

import pandas as pd

from ..core.precision import PrecisionEngine
from ..utils.logger import logger
from .group_processor import GroupProcessor, process_group


引用格式 = re.compile(
    r"^[\[【](?:冲销|冲回|红冲)\s*(\d{4})[./-](\d{1,2})[./-](\d{1,2})\s*"
    r"([^\s\-\]】]+)\s*[-－]\s*(\d+)号凭证[\]】](.*)$"
)
冲销提示 = re.compile(r"^[\[【]\s*(?:冲销|冲回|红冲)")
日期格式 = re.compile(r"^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$")
凭证号格式 = re.compile(r"^(?:([^\s\-]+)-)?(\d+)(?:\.0+)?$")
摘要列 = ("摘要", "业务说明")
日期列 = ("会计月", "凭证日期", "记账时间", "日期")


def _文字(value):
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _日期(value):
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    found = 日期格式.fullmatch(_文字(value))
    if not found:
        return ""
    try:
        return date(*(int(part) for part in found.groups())).isoformat()
    except ValueError:
        return ""


def _凭证号(row):
    found = 凭证号格式.fullmatch(_文字(row.get("凭证编号")))
    if not found:
        return None
    word = _文字(row.get("凭证种类")) or (found.group(1) or "")
    if found.group(1) and found.group(1) != word:
        return None
    return (word, str(int(found.group(2)))) if word else None


def _明细科目(row):
    for column in ("科目编号", "科目名称"):
        value = row.get(column)
        if value is None or pd.isna(value):
            continue
        text = _文字(value)
        if text:
            if column == "科目编号" and re.fullmatch(r"\d+\.0+", text):
                text = text.split(".")[0]
            return _文字(row.get("一级科目")), column, text
    return None


def _净额(row):
    debit, credit = row["借方发生额"], row["贷方发生额"]
    if (debit != 0) == (credit != 0):
        return 0
    return PrecisionEngine.to_integer_li(debit) - PrecisionEngine.to_integer_li(credit)


def _引用(row):
    matches = []
    for column in 摘要列:
        if column not in row:
            continue
        found = 引用格式.fullmatch(_文字(row[column]))
        if found:
            try:
                day = date(*(int(found.group(i)) for i in (1, 2, 3))).isoformat()
            except ValueError:
                return None
            matches.append((column, day, found.group(4), str(int(found.group(5))),
                            found.group(6).strip()))
    return matches[0] if matches and matches[0][-1] and all(
        match[1:] == matches[0][1:] for match in matches) else None


def _凭证日期(group):
    days = set()
    for _, row in group.iterrows():
        row_days = {_日期(row[column]) for column in 日期列 if column in row}
        row_days.discard("")
        if not row_days:
            return ""
        days.update(row_days)
    return next(iter(days)) if len(days) == 1 else ""


def _原行输出(original, rows_by_index):
    """原行每一份金额都能追溯，才复制它的对方科目。"""
    pieces = rows_by_index.get(original.name, ())
    if not pieces or any(
        not row.get("对方科目") or row["对方科目"] == "未找到匹配"
        or row.get("匹配类型") not in {"标准模板", "算法生成"}
        for row in pieces
    ):
        return None
    debit = sum(PrecisionEngine.to_integer_li(row["借方发生额"]) for row in pieces)
    credit = sum(PrecisionEngine.to_integer_li(row["贷方发生额"]) for row in pieces)
    if debit != PrecisionEngine.to_integer_li(original["借方发生额"]) or credit != PrecisionEngine.to_integer_li(original["贷方发生额"]):
        return None
    original_net = _净额(original)
    if any(not _净额(row) or _净额(row) * original_net <= 0 for row in pieces):
        return None
    return [(row["对方科目"], abs(_净额(row))) for row in pieces]


def _反向输出(row, pieces, index):
    column = "借方发生额" if row["借方发生额"] else "贷方发生额"
    sign = 1 if row[column] > 0 else -1
    result = []
    for counterpart, amount_li in pieces:
        output = row.to_dict()
        output[column] = sign * amount_li / PrecisionEngine.SCALE
        output["对方科目"] = counterpart
        output["匹配类型"] = "原凭证冲销"
        output["_orig_idx"] = index
        result.append(output)
    return result


def apply_documented_reversals(tasks, output_rows, ledger_col=None):
    """整表匹配唯一后，只替换已查实冲销凭证的处理结果。"""
    if not tasks or not any(any(column in group for column in 摘要列) for _, group in tasks):
        return output_rows
    if not any(group[column].astype(str).str.strip().str.match(引用格式).any()
               for _, group in tasks for column in 摘要列 if column in group):
        return output_rows
    if sum(len(group) for _, group in tasks) != len({index for _, group in tasks for index in group.index}):
        return output_rows
    originals = defaultdict(list)
    referenced = []
    hinted = Counter()
    task_by_name = dict(tasks)
    for name, group in tasks:
        if not group.index.is_unique or sum(_净额(row) for _, row in group.iterrows()):
            continue
        number = _凭证号(group.iloc[0])
        day = _凭证日期(group)
        ledger = _文字(group.iloc[0].get(ledger_col)) if ledger_col else ""
        if number and day and (not ledger_col or ledger):
            for index, row in group.iterrows():
                if _引用(row) is None and _明细科目(row) and _净额(row):
                    for column in 摘要列:
                        summary = _文字(row.get(column))
                        if summary:
                            originals[(ledger, day, *number, column, _明细科目(row), summary,
                                       _净额(row))].append((name, index))
        for index, row in group.iterrows():
            if any(冲销提示.match(_文字(row.get(column))) for column in 摘要列):
                hinted[name] += 1
            ref = _引用(row)
            if ref:
                referenced.append((name, index, ledger, ref, row))

    candidates = defaultdict(list)
    for name, index, ledger, ref, row in referenced:
        column, day, word, number, summary = ref
        account, amount = _明细科目(row), _净额(row)
        if not account or not amount or (ledger_col and not ledger):
            candidates[(name, day, word, number)].append(None)
            continue
        matches = originals.get((ledger, day, word, number, column, account, summary, -amount), ())
        candidates[(name, day, word, number)].append((index, matches[0]) if len(matches) == 1 else None)

    valid = []
    for (name, _, _, _), links in candidates.items():
        if any(link is None for link in links):
            continue
        original_names = {origin_name for _, (origin_name, _) in links}
        target_indices = [index for index, _ in links]
        if (len(original_names) != 1 or len(target_indices) != len(set(target_indices))
                or len({origin_index for _, (_, origin_index) in links}) != len(links)
                or sum(_净额(task_by_name[name].loc[index]) for index in target_indices)):
            continue
        valid.append((name, links))

    claims = Counter(origin_index for _, links in valid for _, (_, origin_index) in links)
    accepted = defaultdict(list)
    for name, links in valid:
        if all(claims[origin_index] == 1 for _, (_, origin_index) in links):
            accepted[name].append(links)
    accepted = {name: plans for name, plans in accepted.items()
                if sum(len(links) for links in plans) == hinted[name]}
    if not accepted:
        return output_rows

    rows_by_index = defaultdict(list)
    for row in output_rows:
        if "_orig_idx" in row:
            rows_by_index[row["_orig_idx"]].append(row)
    replaced = set()
    additions = []
    for name, plans in accepted.items():
        group = task_by_name[name]
        profit_check = GroupProcessor((name, group))._is_profit_subject
        if any(profit_check(str(subject)) for subject in group["一级科目"].dropna()):
            continue
        if any(index not in rows_by_index for index in group.index):
            continue
        used = set()
        new_rows = []
        try:
            for links in plans:
                indices = [index for index, _ in links]
                used.update(indices)
                templates = {}
                for index, (original_name, original_index) in links:
                    original = task_by_name[original_name].loc[original_index]
                    templates[index] = _原行输出(original, rows_by_index)
                if all(templates.values()):
                    for index in indices:
                        new_rows.extend(_反向输出(group.loc[index], templates[index], index))
                else:
                    part, warnings = process_group((name, group.loc[indices]))
                    new_rows.extend(part)
                    for warning in warnings:
                        logger.warning(warning)
            remaining = group.drop(index=list(used))
            if not remaining.empty:
                part, warnings = process_group((name, remaining))
                new_rows.extend(part)
                for warning in warnings:
                    logger.warning(warning)
        except Exception as exc:
            logger.warning("凭证%s冲销复核未完成，保留原处理结果：%s", name, exc)
            continue
        replaced.update(group.index)
        additions.extend(new_rows)
    return [row for row in output_rows if row.get("_orig_idx") not in replaced] + additions

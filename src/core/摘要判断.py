"""本地摘要双轨判断；保留业务身份，文字相似不能抵消明确矛盾。"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import re
import unicodedata


RELATION_THRESHOLD = 0.72
MAX_SUMMARY_LENGTH = 2000

# 逐条登记业务表达，不把公共动作词当作业务事项。
BUSINESS_PATTERNS = (
    ("设备", r"设备|机器|机床"),
    ("工资", r"工资|薪酬|薪资"),
    ("货款", r"货款|材料款|商品采购"),
    ("办公费", r"办公费|办公用品"),
    ("成本结转", r"结转.{0,6}成本|成本结转"),
    ("折旧", r"折旧"), ("摊销", r"摊销"),
    ("所得税", r"所得税"), ("增值税", r"增值税"),
    ("利息", r"利息"), ("租赁", r"租金|租赁"),
    ("进项税", r"进项税"),
)
ACTION_PATTERNS = (
    ("冲销", r"冲销|冲回|红冲"),
    ("计提", r"计提|预提"),
    ("收款", r"收到|收取|收回"),
    ("付款", r"支付|付款|缴纳|代付|^付"),
    ("维修", r"维修|修理|保养"),
    ("购置", r"采购|购置|购买"),
)
IDENTIFIER_RE = re.compile(
    r"(合同|发票|订单)(?:编号|号码|号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_./-]*)",
    re.I,
)
OBJECT_RE = re.compile(
    r"(?:支付|代付|付款给|收到|收取|向|付|[，,;； ]|^)"
    r"([\u4e00-\u9fffA-Za-z0-9]{1,40}?(?:公司|工厂|中心|事务所))"
)
PERIOD_RE = re.compile(
    r"(?:(20\d{2})年)?(1[0-2]|0?[1-9])月(?!\d{1,2}日)"
    r"|(20\d{2})[-/](1[0-2]|0?[1-9])(?![-/\d])"
)
DATE_RE = re.compile(r"20\d{2}年\d{1,2}月\d{1,2}日|20\d{2}[-/]\d{1,2}[-/]\d{1,2}")


@dataclass(frozen=True)
class SummaryInfo:
    raw: str
    text: str
    business: frozenset
    actions: frozenset
    objects: tuple
    periods: tuple
    identifiers: tuple
    special: bool


@dataclass(frozen=True)
class SummaryRelation:
    score: float = 0
    known: bool = False
    conflict: bool = False
    reason: str = "缺少可区分依据"


def _text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return unicodedata.normalize("NFKC", text)


@lru_cache(maxsize=8192)
def _extract(raw):
    business = frozenset(name for name, pattern in BUSINESS_PATTERNS if re.search(pattern, raw))
    actions = frozenset(name for name, pattern in ACTION_PATTERNS if re.search(pattern, raw))
    identifiers = tuple(sorted(set((m[0], m[1].upper()) for m in IDENTIFIER_RE.findall(raw))))
    objects = tuple(sorted(set(OBJECT_RE.findall(raw))))
    without_dates = DATE_RE.sub("", raw)
    periods = tuple(sorted(set(
        (int(m[0] or m[2]) if m[0] or m[2] else None, int(m[1] or m[3]))
        for m in PERIOD_RE.findall(without_dates)
    ), key=str))
    text = IDENTIFIER_RE.sub("", without_dates)
    text = PERIOD_RE.sub("", text)
    for obj in objects:
        text = text.replace(obj, "")
    for pattern, replacement in (
        (r"设备采购|购置设备|购买设备", "设备"),
        (r"职工工资|员工薪酬|薪酬|薪资", "工资"),
        (r"支付|付款|收到|收取|计提|预提|办理|所属期|本月|本期|业务|处理", ""),
        (r"^付", ""),
    ):
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[\W_]+", "", text).strip("款")
    return SummaryInfo(raw, text, business, actions, objects, periods, identifiers,
                       bool(re.search(r"代付|汇总|合并|批量", raw)))


def extract_summary(value):
    """摘要判断的证据入口，不截断长摘要后假装识别完整。"""
    raw = _text(value)
    if len(raw) > MAX_SUMMARY_LENGTH:
        return SummaryInfo(raw, "", frozenset(), frozenset(), (), (), (), False)
    return _extract(raw)


def compare_summaries(left, right):
    """可替换的摘要判断入口；以后辅助模型仍须遵守金额及来源约束。"""
    a, b = extract_summary(left), extract_summary(right)
    for field in ("identifiers", "periods"):
        av, bv = getattr(a, field), getattr(b, field)
        if field == "identifiers":
            kinds = {kind for kind, _ in av} & {kind for kind, _ in bv}
            conflict = any({v for k, v in av if k == kind} !=
                           {v for k, v in bv if k == kind} for kind in kinds)
        else:
            conflict = bool(av and bv and not any(
                x[1] == y[1] and (x[0] is None or y[0] is None or x[0] == y[0])
                for x in av for y in bv
            ))
        if conflict:
            return SummaryRelation(-1, True, True, "明确编号或所属期间不同")
    if a.objects and b.objects and a.objects != b.objects and not (a.special or b.special):
        return SummaryRelation(-1, True, True, "明确交易对象不同")
    if not a.text or not b.text:
        return SummaryRelation()
    # 设备税额只有明确设备语境，才作为设备业务的伴随事项。
    ab = a.business - {"进项税"} if "设备" in a.business else a.business
    bb = b.business - {"进项税"} if "设备" in b.business else b.business
    if ab and bb and ab.isdisjoint(bb):
        return SummaryRelation(-1, True, True, "明确业务事项不同")
    if a.actions and b.actions and (
            a.actions.isdisjoint(b.actions) or
            "维修" in a.actions and "购置" in b.actions or
            "购置" in a.actions and "维修" in b.actions):
        return SummaryRelation(-1, True, True, "业务动作不同")
    def grams(text):
        return {text[i:i + 2] for i in range(len(text) - 1)} or {text}
    ga, gb = grams(a.text), grams(b.text)
    overlap = 2 * len(ga & gb) / (len(ga) + len(gb))
    order = SequenceMatcher(None, a.text, b.text, autojunk=False).ratio()
    score = (overlap + order) / 2
    shared_identity = bool(set(a.identifiers) & set(b.identifiers) or
                           set(a.objects) & set(b.objects) or set(a.periods) & set(b.periods))
    if ab and bb and ab == bb and overlap >= 0.5:
        score = max(score, 0.8 if shared_identity else 0.74)
    if shared_identity and (ab & bb) and (
            overlap >= 0.5 or "设备" in ab & bb and "进项税" in a.business | b.business):
        score = max(score, 0.9)
    if not shared_identity and not (ab & bb) and ga != gb:
        score = min(score, 0.65)
    if bool(a.objects) != bool(b.objects):
        score = min(score, 0.76)
    if a.objects and b.objects and a.objects != b.objects:
        score = min(score, 0.55)
    return SummaryRelation(score, True, False, "正则业务线索与文字相似度")

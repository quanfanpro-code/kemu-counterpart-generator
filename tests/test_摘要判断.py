"""摘要双轨判断的人工正反例，防止套话及身份信息造成误合并。"""
import pytest


def compare(left, right):
    from src.core.摘要判断 import compare_summaries
    return compare_summaries(left, right)


@pytest.mark.parametrize("left,right", [
    ("付甲公司设备采购款", "支付甲公司购置设备款"),
    ("支付甲公司合同号HT-001设备采购款", "付甲公司购置设备款 合同编号HT-001"),
    ("计提2026年9月职工工资", "预提2026-09所属期员工薪酬"),
])
def test_同业务改写有较强关联(left, right):
    result = compare(left, right)
    assert result.known and not result.conflict
    assert result.score >= 0.72


@pytest.mark.parametrize("left,right", [
    ("支付工资", "支付货款"),
    ("支付甲公司设备款合同号HT-001", "支付甲公司设备款合同号HT-002"),
    ("计提2025年9月工资", "计提2026年9月工资"),
    ("支付甲公司设备款", "支付乙公司设备款"),
    ("计提工资", "支付工资"),
])
def test_明确身份或业务矛盾不能由相似文字掩盖(left, right):
    result = compare(left, right)
    assert result.known and result.conflict
    assert result.score < 0


@pytest.mark.parametrize("left,right", [
    ("", "支付货款"), (None, "支付工资"),
    ("本月业务", "本月业务"), ("支付", "收到"),
])
def test_空摘要和公共套话不贡献依据(left, right):
    assert not compare(left, right).known


def test_编号中的连接符不得被清洗丢失():
    from src.core.摘要判断 import extract_summary
    info = extract_summary("支付甲公司合同号HT-001设备采购款")
    assert info.identifiers == (("合同", "HT-001"),)
    assert info.objects == ("甲公司",)


def test_付款日期不同不等于所属期间冲突():
    result = compare("2026年10月1日支付9月工资", "2026年10月2日支付9月工资")
    assert not result.conflict
    assert result.score >= 0.72


def test_设备和进项税有共同单据时可关联():
    result = compare("购置设备合同号HT-001", "设备进项税合同号HT-001")
    assert not result.conflict
    assert result.score >= 0.72


def test_普通税款不能无依据并到设备采购():
    assert compare("购买设备", "缴纳所得税").conflict


def test_多单位代付不因不同对象直接否定():
    result = compare("代付甲公司设备款", "代付乙公司设备款")
    assert not result.conflict
    assert result.score < 0.72


def test_未登记的具体业务仍可用文字轨关联():
    result = compare("办理园区蓝色标识牌制作", "园区蓝色标识牌制作办理")
    assert result.known and result.score >= 0.72


def test_缺少一个身份字段不假装身份相同():
    result = compare("甲公司设备采购款", "设备采购款")
    assert not result.conflict
    assert result.score < compare("甲公司设备采购款", "甲公司购置设备款").score


def test_同类业务不能掩盖不同具体事项():
    assert compare("支付甲公司设备维修款", "支付甲公司设备采购款").score < 0.72


def test_同类多个编号不得只保留最后一个():
    result = compare("设备合同号HT-001 合同号HT-002", "设备合同号HT-002")
    assert result.conflict


def test_泛化摘要改写也没有区分依据():
    assert not compare("本期业务处理", "本月业务处理").known


def test_只有单据编号时仍能检查明确冲突():
    assert compare("合同号HT-001", "合同号HT-002").conflict


def test_未知摘要文字相似但缺少身份不等于同一业务():
    result = compare("办理蓝色标牌更换", "办理绿色标牌更换")
    assert result.score < 0.72

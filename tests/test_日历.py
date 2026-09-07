import json
from datetime import date
from copy import deepcopy
import pytest
from src import 日历 as calendar


def test_年度日历日期分类和未知年():
    data=json.loads(calendar.BUNDLED.read_text(encoding="utf-8-sig"))
    calendar.validate_calendar(data)
    assert calendar.day_type(date(2026,1,1),data)[0]=="法定节假日"
    assert calendar.day_type(date(2026,1,2),data)[0]=="假期连休或调休"
    assert calendar.day_type(date(2026,1,4),data)[0]=="调休补班"
    assert calendar.day_type(date(2024,2,9),data)[0]=="工作日"
    assert calendar.day_type(date(2025,1,26),data)[0]=="调休补班"
    assert calendar.day_type(date(2030,1,1),data)[0]=="日历缺失"


def test_拒绝同一天既放假又补班():
    data=json.loads(calendar.BUNDLED.read_text(encoding="utf-8-sig"))
    data["2026"]["workdays"].append("01-01")
    with pytest.raises(ValueError):
        calendar.validate_calendar(data)


def test_日历更新先验证再保存_坏更新保留现有文件(tmp_path,monkeypatch):
    path=tmp_path/"日历.json"
    monkeypatch.setattr(calendar,"cache_path",lambda:path)
    class Response:
        def __init__(self,content):self.content=content
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):return self.content
    payload=calendar.BUNDLED.read_bytes()
    def download(url, **kwargs):
        # HTTP请求路径需要编码为ASCII，真实下载不能直接携带中文。
        url.encode("ascii")
        return Response(payload)
    monkeypatch.setattr(calendar,"urlopen",download)
    assert calendar.update_calendar()==["2024","2025","2026"]
    assert path.read_bytes()==payload
    monkeypatch.setattr(calendar,"urlopen",lambda *a,**kw:Response(b"{}"))
    with pytest.raises(ValueError):
        calendar.update_calendar()
    assert path.read_bytes()==payload

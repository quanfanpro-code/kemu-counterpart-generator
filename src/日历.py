"""中国大陆放假调休日历。已核验的数据随程序提供，筛选过程不联网。"""
import json
import os
import shutil
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

BUNDLED = Path(__file__).with_name("中国节假日.json")
UPDATE_URL = "https://raw.githubusercontent.com/quanfanpro-code/kemu-counterpart-generator/main/src/中国节假日.json"


def validate_calendar(data):
    if not isinstance(data, dict) or not data:
        raise ValueError("日历数据为空或格式错误")
    for year, info in data.items():
        if not str(year).isdigit() or not str(info["source"]).startswith("https://"):
            raise ValueError("年份或官方来源缺失")
        seen = set()
        for start, end, name, statutory in info["holidays"]:
            a,b = date.fromisoformat(f"{year}-{start}"),date.fromisoformat(f"{year}-{end}")
            if a>b or not name:
                raise ValueError("假期范围错误")
            days = {a+timedelta(days=i) for i in range((b-a).days+1)}
            if seen & days or not {date.fromisoformat(f"{year}-{d}") for d in statutory} <= days:
                raise ValueError("假期重叠或法定日期不在范围内")
            seen |= days
        workdays={date.fromisoformat(f"{year}-{d}") for d in info["workdays"]}
        if seen & workdays:
            raise ValueError("同日不能同时放假和补班")
    return data


def cache_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "序时账分析器" / "中国节假日.json"


def load_calendar():
    data=validate_calendar(json.loads(BUNDLED.read_text(encoding="utf-8-sig")))
    path=cache_path()
    if path.exists():
        # 损坏缓存必须报出，不能静默把该年当普通周末判断。
        data.update(validate_calendar(json.loads(path.read_text(encoding="utf-8-sig"))))
    return data


def update_calendar():
    """仅下载本项目维护的公开日历，不发送序时账和用户资料。"""
    with urlopen(UPDATE_URL, timeout=20) as response:
        payload=response.read(1024*1024+1)
    if len(payload)>1024*1024:
        raise ValueError("日历文件大小异常")
    data=validate_calendar(json.loads(payload.decode("utf-8-sig")))
    path=cache_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        backup=(Path.home() / "BackUp")/("序时账日历_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        backup.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,backup/path.name)
        if hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256((backup/path.name).read_bytes()).digest():
            raise OSError("日历备份校验失败")
    temp=path.with_suffix(".tmp")
    temp.write_bytes(payload)
    temp.replace(path)
    return sorted(data)


def day_type(day, data):
    info=data.get(str(day.year))
    if info is None:
        return "日历缺失", "", ""
    md=day.strftime("%m-%d")
    if md in info["workdays"]:
        return "调休补班", "", info["source"]
    for start,end,name,statutory in info["holidays"]:
        if start<=md<=end:
            return ("法定节假日" if md in statutory else "假期连休或调休"),name,info["source"]
    return ("普通周末" if day.weekday()>=5 else "工作日"),"",info["source"]

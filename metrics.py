"""衍生指标计算 —— 增粉 / 环比上周 / 上周增粉

口径(与腾讯文档表头对应):
  增粉        = 今日累计粉丝 - 上一次记录的累计粉丝(严格在今天之前)
  上周增粉数据 = 7天前最近值 - 14天前最近值     (上一完整周期的净增)
  环比上周    = 本周增粉 vs 上周增粉 的百分比(上周为 0 显示"新增")
历史不足时填 "-"。
"""

from datetime import datetime, timedelta

from history import prev_value, series, value_at_or_before  # noqa: F401

NA = "-"


def _d(date: str, days: int) -> str:
    return (datetime.strptime(date, "%Y-%m-%d")
            + timedelta(days=days)).strftime("%Y-%m-%d")


def _fmt_delta(v):
    if v is None:
        return NA
    return v if v >= 0 else v    # 负数原样(如 -3), 正数裸数字(表格好看)


def growth_row(hist_data: dict, key: str, date: str, followers) -> dict:
    """返回 {daily, last_week, wow} 三列的值。"""
    if not isinstance(followers, int):
        return {"daily": NA, "last_week": NA, "wow": NA}
    prev = prev_value(hist_data, key, "followers", date)
    daily = followers - prev if isinstance(prev, int) else None

    v7 = value_at_or_before(hist_data, key, "followers", _d(date, -7))
    v14 = value_at_or_before(hist_data, key, "followers", _d(date, -14))
    last_week = (v7 - v14) if isinstance(v7, int) and isinstance(v14, int) \
        else None

    this_week = followers - v7 if isinstance(v7, int) else None
    if isinstance(this_week, int) and isinstance(last_week, int):
        if last_week > 0:
            wow = f"{(this_week - last_week) / last_week * 100:+.0f}%"
        elif this_week > 0:
            wow = "新增"
        else:
            wow = "0%"
    else:
        wow = NA
    return {"daily": _fmt_delta(daily), "last_week": _fmt_delta(last_week),
            "wow": wow}

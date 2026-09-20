"""本地历史快照 —— data/history.json (原子写, 参考 auto-publisher state 套路)

结构:
{
  "days": [
    {"date": "2026-09-18",
     "accounts": {"futu:26436016": {"owner","name","url","followers","content","views","errors"}},
     "crawled_at": ["09:00"]}
  ],
  "synced": {"2026-09-18": "2026-09-18 09:05:03"}   # 腾讯文档同步记录(幂等用)
}
"""

import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "history.json"


def account_key(acct: dict) -> str:
    """平台:标识。标识优先 handle(x/youtube), 否则 url 去协议头;
    两者皆无(手动填写型如公众号)用账号名, 避免同平台多账号互相覆盖。"""
    pid = (acct.get("handle") or "").strip().lstrip("@")
    if not pid:
        url = (acct.get("url") or "").strip()
        pid = url.replace("https://", "").replace("http://", "").rstrip("/")
    if not pid:
        pid = (acct.get("name") or "").strip()
    return f"{acct.get('platform')}:{pid}"


def load() -> dict:
    if DATA.exists():
        try:
            return json.loads(DATA.read_text(encoding="utf-8"))
        except Exception:
            bak = DATA.with_suffix(
                DATA.suffix + f".corrupt-{datetime.now():%Y%m%d%H%M%S}")
            os.replace(DATA, bak)
    return {"days": [], "synced": {}}


def save(data: dict) -> None:
    data["days"].sort(key=lambda d: d["date"])
    DATA.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, DATA)


def day(data: dict, date: str) -> dict:
    """取/建某天的记录。"""
    d = next((x for x in data["days"] if x["date"] == date), None)
    if d is None:
        d = {"date": date, "accounts": {}, "crawled_at": []}
        data["days"].append(d)
    d.setdefault("accounts", {})
    d.setdefault("crawled_at", [])
    return d


def record(data: dict, date: str, key: str, result: dict, acct: dict) -> None:
    """写入一个账号的当日抓取结果(整条覆盖, 含错误便于排查)。"""
    d = day(data, date)
    rec = {
        "platform": acct["platform"],
        "platform_label": acct.get("platform_label", ""),
        "owner": acct.get("owner", ""),
        "name": acct.get("name") or result.get("name") or "",
        "url": acct.get("url", ""),
        "handle": acct.get("handle", ""),
        "followers": result.get("followers"),
        "content": result.get("content"),
        "views": result.get("views"),
        "errors": result.get("errors") or {},
        "manual": result.get("manual", False),
    }
    # 平台累计计数快照(x发帖数): 供次日算24h增量, 无则不存
    if result.get("content_total") is not None:
        rec["content_total"] = result["content_total"]
    # 24h内原创帖明细(x): 仅供本地查看/排查, 不进表格
    if result.get("content_detail"):
        rec["content_detail"] = result["content_detail"]
    d["accounts"][key] = rec


def mark_synced(data: dict, date: str) -> None:
    data.setdefault("synced", {})[date] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S")


def is_synced(data: dict, date: str) -> bool:
    return date in (data.get("synced") or {})


def series(data: dict, key: str, metric: str, before: str = "") -> list:
    """某账号某指标的时间序列 [(date, value)](升序, 只含有值的)。

    before 传日期时只取严格早于该日期的记录。
    """
    out = []
    for d in sorted(data.get("days", []), key=lambda x: x["date"]):
        if before and not d["date"] < before:
            continue
        rec = (d.get("accounts") or {}).get(key) or {}
        v = rec.get(metric)
        if isinstance(v, int):
            out.append((d["date"], v))
    return out


def value_at_or_before(data: dict, key: str, metric: str, date: str):
    """≤date 的最近一次有值记录(不含 date 当天更早也行, 增粉口径取严格
    '之前'由调用方传 date+1 天实现; 这里取 ≤date 最后值)。"""
    s = series(data, key, metric, before=_next_day(date))
    return s[-1][1] if s else None


def _next_day(date: str) -> str:
    from datetime import datetime, timedelta
    return (datetime.strptime(date, "%Y-%m-%d")
            + timedelta(days=1)).strftime("%Y-%m-%d")


def prev_value(data: dict, key: str, metric: str, date: str):
    """严格早于 date 的最近一次有值记录 → 增粉的对比基准。"""
    s = series(data, key, metric, before=date)
    return s[-1][1] if s else None

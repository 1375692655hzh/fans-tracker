#!/usr/bin/env python3
"""一次性历史播种 —— 把 auto-publisher 的 followers_history.json 历史导入本项目

auto-publisher 已有 futu/xueqiu/changqiao/eastmoney/weibo/zhihu 每天粉丝数
(2026-09-04 起)。按平台+主页URL 对上 accounts.yaml 里的账号后写入本项目
data/history.json, 让 增粉/环比上周/上周增粉 从第一天起就有数值。

重复执行安全: 已存在的 (日期, 账号) 记录不会被覆盖。
"""

import json
import logging
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed")

ROOT = Path(__file__).resolve().parent
SRC = Path(r"D:\AI\auto-publisher\autopub\followers_history.json")

# auto-publisher 平台名 → 本项目平台名
PLATFORM_MAP = {"futu": "futu", "xueqiu": "xueqiu", "changqiao": "changqiao",
                "eastmoney": "eastmoney", "weibo": "sina"}


def main():
    import history as hist

    if not SRC.exists():
        log.warning(f"没找到 {SRC} (本机没有 auto-publisher 历史), 跳过。"
                    "不影响正常使用, 增粉列会从第二天开始有值。")
        return
    src = json.loads(SRC.read_text(encoding="utf-8"))
    profiles = src.get("profiles") or {}
    accounts = (yaml.safe_load(
        (ROOT / "config" / "accounts.yaml").read_text(encoding="utf-8"))
        or {}).get("accounts") or []

    # 本项目账号 key → (platform, url 归一化, owner)
    by_url = {}
    for a in accounts:
        url = (a.get("url") or "").replace("https://", "").replace(
            "http://", "").rstrip("/")
        by_url[url] = a

    data = hist.load()
    n = 0
    for d in src.get("days") or []:
        date = d["date"]
        day = hist.day(data, date)
        for plat, count in (d.get("counts") or {}).items():
            plat2 = PLATFORM_MAP.get(plat)
            if not plat2:
                continue
            url = (profiles.get(plat) or {}).get("url", "")
            url_norm = url.replace("https://", "").rstrip("/")
            acct = by_url.get(url_norm)
            if not acct:
                continue
            key = hist.account_key(acct)
            if key in day["accounts"]:        # 已有(本项目今天抓的)不覆盖
                continue
            day["accounts"][key] = {
                "platform": plat2,
                "platform_label": acct.get("platform_label", ""),
                "owner": acct.get("owner", ""),
                "name": acct.get("name") or "",
                "url": acct.get("url", ""),
                "handle": "",
                "followers": count,
                "content": None, "views": None,
                "errors": {},
                "seeded": True,
            }
            n += 1
    hist.save(data)
    log.info(f"播种完成: 导入 {n} 条 (auto-publisher → data/history.json)")


if __name__ == "__main__":
    main()

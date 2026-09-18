#!/usr/bin/env python3
"""fans-tracker —— 多平台社媒账号数据追踪 + 腾讯文档自动填报

用法:
    python main.py crawl                 # 抓取全部账号 → 写本地历史 → 写腾讯文档
    python main.py crawl --platforms futu,xueqiu --no-sync
    python main.py sync                  # 只把今天的历史写进腾讯文档(可重复执行, 覆盖)
    python main.py daily                 # 计划任务入口: 今天已同步过则跳过(幂等)
    python main.py login <platform>      # 需登录平台扫码一次(xueqiu/xhs/douyin/sina...)
    python main.py probe <url> [--spec futu]   # 调试: 打开页面看提取候选, 调选择器用
    python main.py status                # 配置/历史/登录态一览
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import history as hist  # noqa: E402
from browser import BrowserSession  # noqa: E402
from fetchers import (API_FETCHERS, BROWSER_PLATFORMS, PLATFORM_LABELS,  # noqa: E402
                      SPEC)
from fetchers import bilibili_api  # noqa: E402
from fetchers.browser_page import EXTRACT_JS, extract_account  # noqa: E402

log = logging.getLogger("fans")


# ---------- 配置 ----------

def load_settings() -> dict:
    try:
        return yaml.safe_load(
            (ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.warning("settings.yaml 读取失败(%s), 用默认值", e)
        return {}


def load_accounts() -> list:
    d = yaml.safe_load(
        (ROOT / "config" / "accounts.yaml").read_text(encoding="utf-8")) or {}
    out = []
    for a in (d.get("accounts") or []):
        p = (a.get("platform") or "").strip()
        if not p:
            continue
        a["platform"] = p
        a["platform_label"] = PLATFORM_LABELS.get(p, p)
        a["_key"] = hist.account_key(a)
        out.append(a)
    return out


# ---------- 抓取 ----------

def _retryable(result: dict) -> bool:
    """核心指标(粉丝)没拿到且有错误 → 值得重试。"""
    return result.get("followers") is None and bool(result.get("errors"))


async def _fetch_browser_accounts(accounts: list, settings: dict) -> dict:
    """浏览器平台逐账号抓。返回 {key: result}。bilibili 附带 API 粉丝兜底。"""
    results = {}
    retry = int((settings.get("crawl") or {}).get("retry", 1))
    async with BrowserSession(settings, log) as sess:
        for acct in accounts:
            p = acct["platform"]
            spec = SPEC[p]
            key = acct["_key"]
            log.info(f"[{key}] 打开 {acct.get('url')}")
            page, _ = await sess.acquire_page(p)
            result = await extract_account(page, acct, spec, settings, log)
            for _ in range(retry):        # 核心指标失败重试
                if not _retryable(result):
                    break
                log.info(f"[{key}] 重试一次…")
                result = await extract_account(page, acct, spec, settings, log)
            # bilibili: relation/stat 公开接口兜底粉丝(比页面稳)
            if spec.get("api_hook") == "bilibili":
                mid = bilibili_api.extract_mid(acct)
                v, err = bilibili_api.fetch_followers(mid)
                if isinstance(v, int):
                    if result.get("followers") != v:
                        log.info(f"[{key}] API 粉丝 {v} 覆盖页面值 "
                                  f"{result.get('followers')}")
                    result["followers"] = v
                    result.get("errors", {}).pop("followers", None)
                elif result.get("followers") is None:
                    result.setdefault("errors", {})["followers"] = \
                        f"API 也失败: {err}"
            results[key] = result
            _log_result(key, acct, result)
    return results


def _fetch_api_accounts(accounts: list) -> dict:
    results = {}
    for acct in accounts:
        key = acct["_key"]
        fetch = API_FETCHERS[acct["platform"]]
        result = fetch(acct)
        if _retryable(result):            # API 请求轻量, 固定重试一次
            result = fetch(acct)
        results[key] = result
        _log_result(key, acct, result)
    return results


def _log_result(key, acct, result):
    ok = {m: result.get(m) for m in ("followers", "content", "views")
          if result.get(m) is not None}
    errs = result.get("errors") or {}
    tag = PLATFORM_LABELS.get(acct["platform"], acct["platform"])
    if errs and not ok:
        log.warning(f"[{key}] ❌ {tag} 全失败: {errs}")
    elif errs:
        log.info(f"[{key}] ✓ {tag} {ok} (缺: {list(errs)})")
    else:
        log.info(f"[{key}] ✓ {tag} {ok}")


async def crawl(only=None, do_sync=True) -> int:
    settings = load_settings()
    accounts = load_accounts()
    if only:
        accounts = [a for a in accounts if a["platform"] in only]
    if not accounts:
        log.error("没有可抓的账号(检查 config/accounts.yaml)")
        return 1

    data = hist.load()
    today = datetime.now().strftime("%Y-%m-%d")
    day = hist.day(data, today)

    api_accts = [a for a in accounts if a["platform"] in API_FETCHERS]
    brw_accts = [a for a in accounts
                 if a["platform"] in BROWSER_PLATFORMS]
    skipped = [a for a in accounts
               if a["platform"] not in API_FETCHERS
               and a["platform"] not in BROWSER_PLATFORMS]
    for a in skipped:
        log.warning(f"[{a['_key']}] 平台未支持/预留: "
                    f"{SPEC.get(a['platform'], {}).get('disabled', '未知平台')}")

    if api_accts:
        log.info(f"— API 平台 {len(api_accts)} 个 —")
        for k, r in _fetch_api_accounts(api_accts).items():
            acct = next(a for a in api_accts if a["_key"] == k)
            hist.record(data, today, k, r, acct)
        hist.save(data)
    if brw_accts:
        log.info(f"— 浏览器平台 {len(brw_accts)} 个 —")
        for k, r in (await _fetch_browser_accounts(brw_accts, settings)).items():
            acct = next(a for a in brw_accts if a["_key"] == k)
            hist.record(data, today, k, r, acct)
        hist.save(data)

    day.setdefault("crawled_at", []).append(
        datetime.now().strftime("%H:%M"))
    day["crawled_at"] = day["crawled_at"][-5:]
    hist.save(data)

    if do_sync:
        return sync(today)
    return 0


def sync(date: str = "") -> int:
    """把某天(默认今天)的本地历史写进腾讯文档当天 sheet。"""
    import tdoc
    settings = load_settings()
    data = hist.load()
    date = date or datetime.now().strftime("%Y-%m-%d")
    day = next((d for d in data.get("days", []) if d["date"] == date), None)
    if not day or not day.get("accounts"):
        log.error(f"{date} 没有本地抓取数据, 先 python main.py crawl")
        return 1
    try:
        tdoc.sync_day(day, settings, log, date)
    except tdoc.TDocError as e:
        log.error(f"腾讯文档写入失败: {e}")
        return 2
    hist.mark_synced(data, date)
    hist.save(data)
    return 0


def daily(force=False) -> int:
    """计划任务入口: 幂等 —— 今天已抓且已同步则直接退出。"""
    data = hist.load()
    today = datetime.now().strftime("%Y-%m-%d")
    if not force and hist.is_synced(data, today):
        log.info(f"{today} 已完成并同步过, 跳过(重跑: python main.py daily --force)")
        return 0
    return crawl()


# ---------- 登录 / 探测 / 状态 ----------

async def probe(url: str, spec_key: str = "") -> None:
    """调试工具: 打开任意主页, 打印三个指标的提取候选原文。"""
    settings = load_settings()
    spec = SPEC.get(spec_key) or {}
    cfg = {
        "fLabels": spec.get("labels", ["粉丝"]),
        "fPrio": spec.get("prio_res", []),
        "cLabels": (spec.get("content") or {}).get("labels", ["作品", "帖子",
                                                              "笔记", "文章"]),
        "cPrio": (spec.get("content") or {}).get("prio_res", []),
        "vLabels": (spec.get("views") or {}).get("labels", ["阅读", "播放"]),
        "vPrio": (spec.get("views") or {}).get("prio_res", []),
    }
    async with BrowserSession(settings, log) as sess:
        page, _ = await sess.acquire_page("probe")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        for i in range(4):
            await page.wait_for_timeout(2500)
            out = await page.evaluate(EXTRACT_JS, cfg)
            if out.get("followers"):
                break
        print(f"title: {out.get('title')}")
        print(f"url  : {page.url}")
        for m in ("followers", "content", "views"):
            print(f"{m:>10}: {out.get(m)}")


def status() -> None:
    settings = load_settings()
    accounts = load_accounts()
    data = hist.load()
    print(f"账号 {len(accounts)} 个:")
    for a in accounts:
        need = SPEC.get(a["platform"], {}).get("needs_login")
        print(f"  - {a['_key']}  [{a['platform_label']}]"
              f"  {a.get('owner') or '-'}  {a.get('url') or '@' + a.get('handle', '')}"
              + ("  (需登录态)" if need else ""))
    days = data.get("days", [])
    if days:
        print(f"本地历史 {len(days)} 天: {days[0]['date']} ~ {days[-1]['date']}")
        last = days[-1]
        for k, rec in sorted(last.get("accounts", {}).items()):
            print(f"  {last['date']} {k}: 粉丝{rec.get('followers')} "
                  f"内容{rec.get('content')} 阅读{rec.get('views')}")
    print(f"腾讯文档: file_id={settings.get('tdoc', {}).get('file_id')}")
    import tdoc
    try:
        cli = tdoc.SheetClient()
        sheets = cli.get_sheets(settings["tdoc"]["file_id"])
        print(f"  Token ✓, 现有 sheet: "
              + ", ".join(s.get("sheet_name", "?") for s in sheets[:15]))
    except tdoc.TDocError as e:
        print(f"  Token/写入不可用: {e}")


def login(platform: str) -> int:
    """扫码登录: profiles/<platform> 持久化保存, 一次长期有效。"""
    if platform not in BROWSER_PLATFORMS:
        log.error(f"未知平台 {platform}, 可选: {', '.join(BROWSER_PLATFORMS)}")
        return 1
    import login as login_mod
    return login_mod.interactive_login(platform)


def main():
    parser = argparse.ArgumentParser(description="fans-tracker 多平台粉丝追踪")
    parser.add_argument("cmd", nargs="?", default="crawl",
                        choices=["crawl", "sync", "daily", "login",
                                 "probe", "status"])
    parser.add_argument("--platforms", help="逗号分隔平台过滤, 如 futu,xueqiu")
    parser.add_argument("--no-sync", action="store_true",
                        help="只抓取不写腾讯文档")
    parser.add_argument("--force", action="store_true", help="daily: 忽略幂等")
    parser.add_argument("extra", nargs="*", help="login 平台名 / probe URL")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    (ROOT / "logs").mkdir(exist_ok=True)

    only = ([s.strip() for s in args.platforms.split(",")]
            if args.platforms else None)
    if args.cmd == "crawl":
        sys.exit(asyncio.run(crawl(only=only, do_sync=not args.no_sync)))
    if args.cmd == "daily":
        sys.exit(daily(force=args.force))
    if args.cmd == "sync":
        sys.exit(sync())
    if args.cmd == "login":
        plat = args.extra[0] if args.extra else ""
        sys.exit(login(plat))
    if args.cmd == "probe":
        url = args.extra[0] if args.extra else ""
        if not url.startswith("http"):
            print("用法: python main.py probe <主页URL> [--spec futu](需 -- 前)")
            sys.exit(1)
        spec_key = ""
        if "--spec" in sys.argv:
            spec_key = sys.argv[sys.argv.index("--spec") + 1]
        sys.exit(asyncio.run(probe(url, spec_key)))
    if args.cmd == "status":
        status()
        sys.exit(0)


if __name__ == "__main__":
    main()

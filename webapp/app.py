"""fans-tracker Web 控制台 —— 可视化 / 账号管理 / 设置 / 手动抓取

启动: python main.py web   →  http://127.0.0.1:8787
"""

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import history as hist  # noqa: E402
import tasks  # noqa: E402
from main import load_accounts, load_settings  # noqa: E402
from fetchers import API_FETCHERS, PLATFORM_LABELS, SPEC  # noqa: E402
from fetchers.browser_page import BROWSER_PLATFORMS  # noqa: E402

app = Flask(__name__)

CRAWL_LOG = ROOT / "logs" / "web_crawl.log"
_state = {"running": False, "started": "", "proc": None, "tail": ""}
_lock = threading.Lock()


# ---------- 页面 ----------

@app.route("/")
def page_index():
    return render_template("index.html")


@app.route("/accounts")
def page_accounts():
    return render_template("accounts.html")


@app.route("/settings")
def page_settings():
    return render_template("settings.html")


# ---------- 数据 API ----------

@app.route("/api/data")
def api_data():
    """趋势序列 + 今日表格行(与腾讯文档同口径)。"""
    data = hist.load()
    dates = sorted({d["date"] for d in data.get("days", [])})
    by_date = {d["date"]: (d.get("accounts") or {})
               for d in data.get("days", [])}
    today = datetime.now().strftime("%Y-%m-%d")
    latest = next((d for d in reversed(data.get("days", []))
                   if d.get("accounts")), None)
    from metrics import growth_row
    rows, series = [], {}
    if latest:
        for key in sorted(latest["accounts"]):
            rec = latest["accounts"][key]
            g = growth_row(data, key, latest["date"], rec.get("followers"))
            rows.append({
                "key": key, "owner": rec.get("owner") or "-",
                "platform": rec.get("platform_label") or rec.get("platform"),
                "name": rec.get("name") or "-",
                "views": rec.get("views"), "content": rec.get("content"),
                "daily": g["daily"], "wow": g["wow"],
                "followers": rec.get("followers"),
                "last_week": g["last_week"],
                "errors": rec.get("errors") or {},
            })
            pts = [((by_date.get(dt) or {}).get(key) or {}).get("followers")
                   for dt in dates]
            series[key] = {
                "label": f"{rec.get('owner') or ''}·"
                         f"{rec.get('platform_label') or rec.get('platform')}",
                "points": pts}
    return jsonify({"dates": dates, "series": series, "rows": rows,
                    "latest_date": latest["date"] if latest else "",
                    "today": today, "synced": hist.is_synced(data, today)})


@app.route("/api/accounts", methods=["GET", "POST", "DELETE"])
def api_accounts():
    f = ROOT / "config" / "accounts.yaml"
    if request.method == "GET":
        return jsonify({"accounts": load_accounts()})
    if request.method == "POST":
        d = request.json or {}
        return jsonify(add_account(f, d))
    # DELETE
    d = request.json or {}
    return jsonify(delete_account(f, d.get("platform", ""),
                                  d.get("url", ""), d.get("handle", "")))


def add_account(f: Path, d: dict) -> dict:
    plat = (d.get("platform") or "").strip()
    if plat not in PLATFORM_LABELS:
        return {"ok": False, "msg": f"未知平台 {plat}"}
    if SPEC.get(plat, {}).get("disabled"):
        return {"ok": False, "msg": f"{plat} 本期未开通"}
    url = (d.get("url") or "").strip()
    handle = (d.get("handle") or "").strip().lstrip("@")
    if plat in API_FETCHERS and not handle:
        return {"ok": False, "msg": "X/YouTube 必须填 handle(@用户名)"}
    if plat not in API_FETCHERS and not url.startswith("http"):
        return {"ok": False, "msg": "必须填主页链接(http开头)"}
    acct = {"platform": plat, "owner": (d.get("owner") or "").strip() or "未填",
            "name": (d.get("name") or "").strip()}
    if handle:
        acct["handle"] = handle
    if url:
        acct["url"] = url
    lines = [f"  - platform: {plat}"]
    for k in ("owner", "name"):
        if acct.get(k):
            lines.append(f"    {k}: {acct[k]}")
        else:
            lines.append(f'    {k}: ""')
    if handle:
        lines.append(f"    handle: {handle}")
    if url:
        lines.append(f"    url: {url}")
    with open(f, "a", encoding="utf-8") as fh:   # 追加列表项, 不动已有注释
        fh.write("\n" + "\n".join(lines) + "\n")
    return {"ok": True, "msg": "已添加(立即生效)"}


def delete_account(f: Path, platform: str, url: str, handle: str) -> dict:
    lines = f.read_text(encoding="utf-8").splitlines()
    out, i, removed = [], 0, False
    ident = (url or handle or "").strip().lstrip("@")
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == f"- platform: {platform}" and not removed:
            block = [ln]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip().startswith("- platform:") or not nxt.startswith(
                        (" ", "\t")):
                    break
                block.append(nxt)
                j += 1
            blk = "\n".join(block)
            if ident and ident in blk:
                removed = True
                i = j
                continue
        out.append(ln)
        i += 1
    if not removed:
        return {"ok": False, "msg": "没找到该账号"}
    f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return {"ok": True, "msg": "已删除"}


# ---------- 设置 API ----------

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    import yaml
    f = ROOT / "config" / "settings.yaml"
    settings = load_settings()
    if request.method == "GET":
        env = ROOT / ".env"
        key = ""
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("YOUTUBE_API_KEY="):
                    key = line.split("=", 1)[1].strip()
        sched = settings.get("schedule") or {}
        import tdoc
        return jsonify({
            "youtube_key_set": bool(key), "youtube_key_tail": key[-6:],
            "tdoc_token_ok": bool(tdoc.load_token()),
            "tdoc_file_id": (settings.get("tdoc") or {}).get("file_id"),
            "headless": bool((settings.get("browser") or {})
                             .get("headless", False)),
            "schedule": {"enabled": sched.get("enabled", True),
                         "hour": sched.get("hour", 9),
                         "minute": sched.get("minute", 0)},
            "task": tasks.query_schedule(),
            "platforms": [{"id": k, "label": v["label"],
                           "needs_login": v.get("needs_login", False)}
                          for k, v in SPEC.items()]
                          + [{"id": "x", "label": "X", "needs_login": False},
                             {"id": "youtube", "label": "YouTube",
                              "needs_login": False}],
        })
    # POST: 三类可改项, 分别应用
    d = request.json or {}
    msgs = []
    if "youtube_key" in d:
        key = (d.get("youtube_key") or "").strip()
        (ROOT / ".env").write_text(f"YOUTUBE_API_KEY={key}\n", encoding="utf-8")
        msgs.append("YouTube API Key 已保存" + ("(已清除)" if not key else ""))
    if "headless" in d:
        settings.setdefault("browser", {})["headless"] = bool(d["headless"])
        _save_yaml(f, settings)
        msgs.append("静默(无头)浏览: " + ("开" if d["headless"] else "关"))
    if "schedule" in d:
        sc = d["schedule"]
        settings["schedule"] = {
            "enabled": bool(sc.get("enabled", True)),
            "hour": int(sc.get("hour", 9)), "minute": int(sc.get("minute", 0))}
        _save_yaml(f, settings)
        out = tasks.register_schedule(settings["schedule"]["hour"],
                                      settings["schedule"]["minute"],
                                      settings["schedule"]["enabled"])
        msgs.append(f"计划任务已更新: {out}")
    if not msgs:
        return jsonify({"ok": False, "msg": "没有可应用的更改"})
    return jsonify({"ok": True, "msg": "; ".join(msgs)})


def _save_yaml(f: Path, d: dict):
    import yaml
    text = yaml.safe_dump(d, allow_unicode=True, sort_keys=False)
    f.write_text("# 由控制台自动生成; 各项含义见 README.md\n" + text,
                 encoding="utf-8")


# ---------- 手动抓取 ----------

@app.route("/api/crawl", methods=["POST"])
def api_crawl_start():
    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "msg": "已有抓取在跑"})
        _state.update(running=True, started=datetime.now().strftime("%H:%M:%S"),
                      tail="")
    ROOT.joinpath("logs").mkdir(exist_ok=True)
    logf = open(CRAWL_LOG, "a", encoding="utf-8")
    logf.write(f"\n===== web 触发 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    logf.flush()
    proc = subprocess.Popen([sys.executable, "main.py", "crawl"],
                            cwd=str(ROOT), stdout=logf, stderr=logf)

    def _wait():
        proc.wait()
        logf.close()
        with _lock:
            _state["running"] = False

    threading.Thread(target=_wait, daemon=True).start()
    _state["proc"] = proc
    return jsonify({"ok": True, "msg": "已开始(浏览器平台约1-3分钟)"})


@app.route("/api/crawl/status")
def api_crawl_status():
    with _lock:
        running = _state["running"]
    tail = ""
    if CRAWL_LOG.exists():
        tail = CRAWL_LOG.read_text(encoding="utf-8", errors="replace")[-2500:]
    return jsonify({"running": running, "tail": tail})

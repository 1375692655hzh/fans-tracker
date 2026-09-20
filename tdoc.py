"""腾讯文档写入 —— 直连 sheet MCP 端点(MCP-over-HTTP, 无状态单次 tools/call)

鉴权 Token 按顺序找:
  1. 本项目 secret.local.json 的 tdoc_token
  2. auto-publisher 的 secret.local.json (autopub/tdoc_client.py 授权过)
  3. mcporter 配置 C:/Users/<user>/.mcporter/mcporter.json 里 sheet-mcp 的
     Authorization 头(tencent-docs skill 授权过)
Token 过期(400006)时提示重新授权。

每天写入流程:
  get_sheets → 当日 sheet 不存在则 add_sheet(name=YYYY-MM-DD)
  → set_range_value_by_csv 批量写 表头+数据行(整块覆盖, 可重复执行)
"""

import csv
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHEET_MCP = "https://docs.qq.com/api/v6/sheet/mcp"
MCPORTER_CONF = Path.home() / ".mcporter" / "mcporter.json"
AUTOPUB_SECRET = Path(r"D:\AI\auto-publisher\autopub\secret.local.json")


class TDocError(RuntimeError):
    pass


def load_token() -> str:
    for p in (ROOT / "secret.local.json", AUTOPUB_SECRET):
        try:
            tok = (json.loads(p.read_text(encoding="utf-8"))
                   .get("tdoc_token") or "")
            if tok:
                return tok
        except Exception:
            continue
    try:                             # mcporter: headers.Authorization 即 Token
        d = json.loads(MCPORTER_CONF.read_text(encoding="utf-8"))
        tok = (((d.get("mcpServers") or {}).get("sheet-mcp") or {})
               .get("headers") or {}).get("Authorization") or ""
        if tok:
            return tok
    except Exception:
        pass
    return ""


def save_token(token: str) -> None:
    (ROOT / "secret.local.json").write_text(
        json.dumps({"tdoc_token": token}, ensure_ascii=False, indent=2),
        encoding="utf-8")


# ---------- 用户自助授权(扫码一次, 长期有效) ----------

TOKEN_URL = "https://docs.qq.com/oauth/v2/mcp/token/get"
AUTH_PAGE = "https://docs.qq.com/scenario/open-claw.html"

# 网页端授权流程状态(webapp 控制台"扫码授权"按钮用)
_auth_state = {}


def start_auth_flow() -> str:
    """启动后台轮询线程, 返回授权页 URL(前端开新标签页展示给用户扫码)。

    用户在授权页确认后, 轮询线程拿到 Token 自动落盘; 之后
    load_token() 即有效。"""
    import secrets
    import threading
    import time
    code = secrets.token_hex(8)
    url = f"{AUTH_PAGE}?nlc=1&authType=1&code={code}&mcp_source=desktop"
    _auth_state["code"] = code

    def _poll():
        for _ in range(100):                   # 3s × 100 ≈ 5 分钟
            time.sleep(3)
            try:
                with urllib.request.urlopen(
                        f"{TOKEN_URL}?code={code}", timeout=15) as resp:
                    d = json.loads(resp.read().decode("utf-8"))
            except Exception:
                continue
            tok = ((d.get("data") or {}).get("token") or d.get("token") or "")
            if tok:
                save_token(tok)
                _auth_state["done"] = True
                return
            if d.get("error") or d.get("code") in (-1, 1):
                _auth_state["failed"] = str(d)[:150]
                return

    threading.Thread(target=_poll, daemon=True).start()
    return url


def auth_flow_status() -> dict:
    return {"authorized": bool(load_token()),
            "done": bool(_auth_state.get("done")),
            "failed": _auth_state.get("failed", "")}


def cli_auth() -> int:
    """授权向导: 本地随机 code → 浏览器扫码确认 → 轮询拿 Token 存盘。"""
    import secrets
    import time
    import webbrowser
    code = secrets.token_hex(8)
    url = f"{AUTH_PAGE}?nlc=1&authType=1&code={code}&mcp_source=desktop"
    print("🔑 腾讯文档授权(一次即可, 长期有效)")
    print("1) 即将打开浏览器, 请用 QQ/微信扫码并确认授权")
    print(f"   没弹就手动访问:\n   {url}")
    print("2) 链接 5 分钟内有效; 完成后本窗口自动继续")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    for i in range(100):                       # 3s × 100 ≈ 5 分钟
        time.sleep(3)
        try:
            with urllib.request.urlopen(
                    f"{TOKEN_URL}?code={code}", timeout=15) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"❌ 授权失败: token/get 请求失败: {e}")
            return 1
        tok = ((d.get("data") or {}).get("token") or d.get("token") or "")
        if tok:
            save_token(tok)
            print("✅ 授权成功, Token 已存 secret.local.json(已 gitignore)")
            return 0
        if d.get("error") or d.get("code") in (-1, 1):
            print("❌ 授权失败:", json.dumps(d, ensure_ascii=False)[:200])
            return 1
        print(f"  等待浏览器完成授权… ({(i + 1) * 3}s)")
    print("❌ 超时。重新运行: python main.py tdoc-auth")
    return 1


class SheetClient:
    def __init__(self, token: str = ""):
        self.token = token or load_token()
        if not self.token:
            raise TDocError("未找到腾讯文档 Token: 在本项目目录执行 "
                            "python main.py tdoc-auth 扫码授权一次即可")

    def call(self, tool: str, arguments: dict) -> dict:
        """sheet-mcp 工具名不带 sheet. 前缀; 个别环境带前缀, 自动回退。"""
        last_err = None
        for name in (tool, f"sheet.{tool}"):
            try:
                return self._post(name, arguments)
            except TDocError as e:
                if "tool not found" in str(e) and name != f"sheet.{tool}":
                    last_err = e
                    continue
                raise
        raise last_err or TDocError(f"{tool}: 调用失败")

    def _post(self, tool: str, arguments: dict) -> dict:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": tool, "arguments": arguments or {}}}
        req = urllib.request.Request(
            SHEET_MCP, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "Authorization": self.token})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise TDocError(
                f"HTTP {e.code}: Token 失效或无权限"
                "(400006=过期, 执行 python main.py tdoc-auth 重新授权)"
            ) from e
        except Exception as e:
            raise TDocError(f"网络请求失败: {e}") from e
        if d.get("error"):
            raise TDocError(f"{tool}: {d['error']}")
        try:
            inner = json.loads(d["result"]["content"][0]["text"])
        except Exception:
            raise TDocError(f"{tool}: 返回结构异常: {str(d)[:200]}")
        if inner.get("error"):
            raise TDocError(f"{tool}: {inner['error']}")
        return inner

    # ---- 常用操作 ----

    def get_sheets(self, file_id: str) -> list:
        """[{sheet_id, sheet_name, ...}]"""
        d = self.call("get_sheet_info", {"file_id": file_id})
        sheets = d.get("data", {}).get("sheets") or d.get("sheets") or []
        return sheets if isinstance(sheets, list) else []

    def add_sheet(self, file_id: str, name: str) -> str:
        d = self.call("add_sheet", {"file_id": file_id, "name": name,
                                    "append_index": True})
        sid = (d.get("data") or {}).get("sheet_id") or d.get("sheet_id") or ""
        if not sid:
            raise TDocError(f"add_sheet 未返回 sheet_id: {str(d)[:200]}")
        return sid

    def write_csv(self, file_id: str, sheet_id: str, rows: list) -> None:
        """rows: 二维数组, 从 A1 开始整块写入(自动数字/字符串类型)。"""
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(
            [[_csv_cell(c) for c in row] for row in rows])
        self.call("set_range_value_by_csv", {
            "file_id": file_id, "sheet_id": sheet_id,
            "start_row": 0, "start_col": 0, "csv_data": buf.getvalue()})

    def delete_sheet(self, file_id: str, sheet_id: str) -> None:
        self.call("delete_sheet", {"file_id": file_id, "sheet_id": sheet_id})

    def read_cells(self, file_id: str, sheet_id: str,
                   end_row=5, end_col=9) -> list:
        d = self.call("get_cell_data", {
            "file_id": file_id, "sheet_id": sheet_id,
            "start_row": 0, "start_col": 0,
            "end_row": end_row, "end_col": end_col})
        data = d.get("data") or d
        cells = data.get("cells") if isinstance(data, dict) else None
        if cells is not None:          # cells 数组结构 → 二维表
            grid = {}
            for c in cells:
                v = {"STRING": c.get("string_value"),
                     "NUMBER": c.get("number_value"),
                     "BOOL": c.get("bool_value")}.get(c.get("value_type"))
                if v in (None, "", 0) and c.get("string_value"):
                    v = c["string_value"]
                grid[(c["row"], c["col"])] = v
            if not grid:
                return []
            nrow = max(r for r, _ in grid) + 1
            ncol = max(cc for _, cc in grid) + 1
            return [[grid.get((r, c), "") for c in range(ncol)]
                    for r in range(nrow)]
        txt = (data.get("csv") if isinstance(data, dict) else "") or ""
        return [r for r in csv.reader(io.StringIO(txt)) if r]


def _csv_cell(v):
    if v is None:
        return "-"
    if isinstance(v, bool):
        return str(v)
    return v


def sync_day(hist_day: dict, settings: dict, logger, date: str = "") -> str:
    """把一天的账号数据写进当日 sheet(表头驱动, 列序随配置)。返回 sheet_id。

    hist_day: history.day() 的 {"date","accounts":{key:rec}}
    """
    from metrics import growth_row
    from history import load as load_hist
    hist_all = load_hist()

    tcfg = settings.get("tdoc") or {}
    file_id = tcfg.get("file_id") or "YOUR_SHEET_ID"
    header = tcfg.get("header") or ["账号所有人", "所属平台", "账号名称",
                                    "阅读/播放量", "内容数", "增粉", "累计粉丝"]
    date = date or hist_day.get("date") or datetime.now().strftime("%Y-%m-%d")

    cli = SheetClient()
    sheets = cli.get_sheets(file_id)
    logger.info(f"腾讯文档: 共 {len(sheets)} 个 sheet: "
                + ", ".join(s.get("sheet_name", "?") for s in sheets[:12]))
    target = next((s for s in sheets if s.get("sheet_name") == date), None)
    if target:
        sheet_id = target["sheet_id"]
        logger.info(f"腾讯文档: sheet「{date}」已存在({sheet_id}), 覆盖更新")
    else:
        sheet_id = cli.add_sheet(file_id, date)
        logger.info(f"腾讯文档: 新建 sheet「{date}」({sheet_id})")

    from metrics import growth_row
    from history import load as load_hist
    hist_all = load_hist()

    def _field(col, rec, key):
        """列名 → 单元格值; 不认识的列名填 "-", 未来调列自动适配。"""
        if col == "账号所有人":
            return rec.get("owner") or "-"
        if col == "所属平台":
            return rec.get("platform_label") or rec.get("platform") or "-"
        if col == "账号名称":
            return rec.get("name") or "-"
        if col == "阅读/播放量":
            return rec.get("views") if rec.get("views") is not None else "-"
        if col == "内容数":
            return rec.get("content") if rec.get("content") is not None                 else "-"
        if col == "增粉":
            return growth_row(hist_all, key, date,
                              rec.get("followers"))["daily"]
        if col == "累计粉丝":
            return rec.get("followers")                 if rec.get("followers") is not None else "-"
        return "-"

    rows = [list(header)]
    for key in sorted(hist_day.get("accounts", {})):
        rec = hist_day["accounts"][key]
        rows.append([_field(col, rec, key) for col in header])
    cli.write_csv(file_id, sheet_id, rows)
    logger.info(f"腾讯文档: 已写入 {len(rows) - 1} 个账号 → sheet「{date}」")
    return sheet_id

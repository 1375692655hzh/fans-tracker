"""Windows 计划任务与桌面快捷方式管理 —— 供 main.py setup 与网页设置页共用

计划任务(时间可由用户在设置页改, 保存即生效):
  fans-tracker-daily     每天 HH:MM 抓取+写表
  fans-tracker-catchup   每次登录补跑(幂等, 当天做过即跳过)
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BAT = ROOT / "run_daily.bat"
TASK_DAILY = "fans-tracker-daily"
TASK_CATCHUP = "fans-tracker-catchup"


def _schtasks(args: list) -> tuple:
    r = subprocess.run(["schtasks"] + args, capture_output=True)
    return r.returncode, (r.stdout or r.stderr).decode("gbk", "replace").strip()


def register_schedule(hour: int = 9, minute: int = 0, enabled: bool = True) -> str:
    """(重)注册每天 HH:MM 任务; enabled=False 时只删不建。返回执行结果文本。"""
    msgs = []
    if not enabled:
        for tn in (TASK_DAILY, TASK_CATCHUP):
            code, out = _schtasks(["/Delete", "/TN", tn, "/F"])
            msgs.append(f"删除 {tn}: {out}")
        return "; ".join(msgs)
    st = f"{max(0, min(23, int(hour))):02d}:{max(0, min(59, int(minute))):02d}"
    code, out = _schtasks(["/Create", "/TN", TASK_DAILY, "/TR", str(BAT),
                           "/SC", "DAILY", "/ST", st, "/F"])
    msgs.append(f"每天 {st}: {out or 'ok'}")
    code, out = _schtasks(["/Create", "/TN", TASK_CATCHUP, "/TR", str(BAT),
                           "/SC", "ONLOGON", "/F"])
    msgs.append(f"登录补跑: {out or 'ok'}")
    return "; ".join(msgs)


def query_schedule() -> dict:
    """当前任务状态(找不到返回 enabled=False)。"""
    code, out = _schtasks(["/Query", "/TN", TASK_DAILY])
    ok = code == 0
    return {"registered": ok,
            "task": TASK_DAILY,
            "raw": out.splitlines()[-1] if ok and out else ""}


def create_desktop_shortcut(name: str = "粉丝数据追踪控制台",
                            url: str = "http://127.0.0.1:8787") -> str:
    """桌面建 .url 快捷方式(纯文本 INI, 无需 PowerShell)。返回路径。"""
    desktop = Path(os_desktop())
    link = desktop / f"{name}.url"
    link.write_text("[InternetShortcut]\n"
                    f"URL={url}\n"
                    "IconIndex=0\n", encoding="utf-8")
    return str(link)


def os_desktop() -> str:
    import os
    for env in ("USERPROFILE", "HOME"):
        base = os.environ.get(env)
        if base:
            d = Path(base) / "Desktop"
            if d.exists():
                return str(d)
    return str(Path.home())

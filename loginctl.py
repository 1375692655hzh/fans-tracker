"""登录状态检测 —— 控制台"登录状态"面板用

对每个平台(或每账号)的持久 profile 做一次无头快速探测:
打开平台首页, 看 URL 是否被跳到登录页(login_marks), 从而判定登录态
是否有效。只读导航, 不触发风控写入。
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "profiles"

from login import LOGIN_URLS          # noqa: E402  平台 → (首页, 登录页URL特征)
from fetchers.browser_page import SPEC  # noqa: E402
from browser import profile_name      # noqa: E402

# 页面正文出现这些特征 ⇒ 判定为未登录(有些平台匿名不跳转登录页, URL判定会漏)
BODY_LOGGED_OUT = {
    # 匿名访问时顶部导航以 登录/注册 开头; 已登录则显示 "NEW"/个人主页入口
    "weibo": r"^\s*登录\s*\n\s*注册",
}

# 会话 cookie 判定(优先于页面探测): 这些平台首页对无头浏览器有风控
# (抖音被跳登录页/快手干脆不渲染), 页面探测不可靠 —— 直接读持久档案里的
# 会话 cookie: 有会话即已登录, 不访问任何页面, 不受风控影响。
COOKIE_MARKERS = {
    "douyin": ["sessionid", "sessionid_ss"],
    "kuaishou": ["passToken"],
    "weibo": ["SUB"],
    "xueqiu": ["xq_a_token"],
    "zhihu": ["z_c0"],
    "bilibili": ["SESSDATA", "DedeUserID"],
    "xhs": ["web_session"],
}


def probe_target(platform: str, ident: str = "") -> tuple:
    """返回 (探测用首页, 登录页URL特征列表)。"""
    spec = SPEC.get(platform) or {}
    home = spec.get("home_url") or LOGIN_URLS.get(platform, ("", []))[0]
    marks = spec.get("login_marks") or LOGIN_URLS.get(platform, ("", []))[1]
    return home, marks


async def _probe_body_len(page) -> str:
    try:
        return await page.evaluate(
            "() => (document.body&&document.body.innerText||'')")
    except Exception:
        return ""


async def _probe_async(platform: str, prof: str, home: str,
                       marks: list) -> dict:
    out = {"logged_in": None, "detail": ""}
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILES / prof), headless=True,
            viewport={"width": 1280, "height": 860}, locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"])
        markers = COOKIE_MARKERS.get(platform)
        if markers:                     # cookie 判定: 不访问任何页面
            cookies = await ctx.cookies()
            names = {c.get("name", "") for c in cookies}
            hit = [m for m in markers if m in names]
            if hit:
                out.update(logged_in=True, detail=f"会话cookie存在({','.join(hit)})")
            else:
                out.update(logged_in=False, detail="无会话cookie(未登录或已退出)")
            await ctx.close()
            return out
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await page.goto(home, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            out["detail"] = f"打开首页超时/失败: {str(e)[:80]}"
            await ctx.close()
            return out
        url, body = "", ""
        for _ in range(8):               # 8×2.5s = 20s, 等登录跳转落定
            await page.wait_for_timeout(2500)
            url = (page.url or "").lower()
            if any(m.lower() in url for m in marks):
                out.update(logged_in=False,
                           detail=f"被重定向到登录页 {url[:60]}")
                await ctx.close()
                return out
            body = await _probe_body_len(page)
            pat = BODY_LOGGED_OUT.get(platform)
            if pat and re.search(pat, body):
                out.update(logged_in=False, detail="页面呈现未登录特征")
                await ctx.close()
                return out
            s = body.strip()
            if s.startswith("{") and s.endswith("}"):
                break                          # 裸JSON, 再等也不会渲染
            if len(body) > 80:
                break
        if body.strip().startswith("{") and body.strip().endswith("}"):
            # 服务端只回了裸JSON(如快手 result:2) —— 无头受限渲染失败, 无法据此判登录
            out.update(logged_in=None, detail="页面未渲染(无头受限, 不代表未登录)")
        elif len(body) < 80:
            # 内容始终渲染不出: 未登录/被风控
            out.update(logged_in=False, detail="页面内容为空(未登录或被风控)")
        else:
            out.update(logged_in=True,
                       detail=f"首页正常打开 {url[:60] or home[:60]}")
        await ctx.close()
        return out


def probe(platform: str, ident: str = "", account_url: str = "") -> dict:
    """探测一次登录态。account_url 优先于平台首页(更能反映账号页登录墙)。
    返回 {platform, ident, profile, profile_exists, logged_in: True/False/None,
    detail, home, checked_at}。"""
    prof = profile_name(platform, ident)
    home, marks = probe_target(platform, ident)
    target = account_url or home
    r = {"platform": platform, "ident": ident, "profile": prof,
         "profile_exists": (PROFILES / prof).exists(),
         "logged_in": None, "detail": "", "home": target,
         "checked_at": datetime.now().strftime("%H:%M:%S")}
    if not target:
        r["detail"] = "该平台没有可探测的首页配置"
        return r
    try:
        res = asyncio.run(_probe_async(platform, prof, target, marks))
        r.update(res)
    except Exception as e:
        r["detail"] = f"检测失败: {str(e)[:100]}" \
                      "(可能是抓取正在占用该浏览器档案, 稍后再试)"
    return r

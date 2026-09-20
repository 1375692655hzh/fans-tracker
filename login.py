"""一次性扫码登录 —— profiles/<平台> 持久化保存登录态, 长期有效

用法: python main.py login xueqiu
打开该平台的独立浏览器窗口 → 手机扫码/账号登录 → 自动检测到已登录后
等 8 秒(让 cookie 落盘)自动关闭。之后 daily 抓取共用这份登录态。
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "profiles"

# 平台 → (首页, 登录页特征: URL 含任一即视为还在登录页)
LOGIN_URLS = {
    "futu": ("https://q.futunn.com/", ["passport", "login"]),
    "xueqiu": ("https://xueqiu.com/", ["login"]),
    "changqiao": ("https://longportapp.com/", ["signin", "login"]),
    "eastmoney": ("https://www.eastmoney.com/", ["passport", "/login"]),
    "laohu": ("https://www.laohu8.com/", ["login", "signin"]),
    "ths": ("https://t.10jqka.com.cn/", ["login"]),
    "sina": ("https://weibo.com/", ["newlogin", "login.sina", "/login"]),
    "weibo": ("https://weibo.com/", ["newlogin", "login.sina", "/login"]),
    "zhihu": ("https://www.zhihu.com/", ["signin", "/login", "unhuman"]),
    "bilibili": ("https://www.bilibili.com/", ["passport"]),
    "xhs": ("https://www.xiaohongshu.com/", ["login"]),
    "douyin": ("https://www.douyin.com/", ["login"]),
    "kuaishou": ("https://www.kuaishou.com/", ["login", "passport"]),
}


async def _login_flow(platform: str) -> bool:
    home, marks = LOGIN_URLS[platform]
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILES / platform),
            headless=False,
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        print(f"[{platform}] 打开 {home}, 请在弹出的窗口里登录(扫码/账密)…")
        await page.goto(home, wait_until="domcontentloaded", timeout=60000)
        ok = False
        for _ in range(200):              # 3s × 200 = 10 分钟
            await asyncio.sleep(3)
            url = page.url or ""
            if not any(m in url.lower() for m in marks):
                # URL 不在登录页了 → 多半已登录; 再看有没有头像/昵称类元素
                logged = await page.evaluate("""() => {
                    return !!document.querySelector(
                        '[class*="avatar"],[class*="Avatar"],[class*="user"],'
                        + '[class*="User"],img[alt]');
                }""")
                if logged:
                    ok = True
                    break
        if ok:
            print(f"[{platform}] 检测到已登录, 8 秒后保存并关闭…")
            await asyncio.sleep(8)
        else:
            print(f"[{platform}] 10 分钟未检测到登录, 直接关闭"
                  "(登录态若已产生同样会保留)")
        await ctx.close()
        return ok


def interactive_login(platform: str) -> int:
    if platform not in LOGIN_URLS:
        print(f"平台 {platform} 不在登录列表: {', '.join(LOGIN_URLS)}")
        return 1
    PROFILES.mkdir(exist_ok=True)
    ok = asyncio.run(_login_flow(platform))
    print(("✅ 登录态已保存到 profiles/" + platform) if ok
          else "⚠️ 未确认登录成功, 可重跑或直接手测: python main.py probe <主页URL>")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python login.py <platform>")
        sys.exit(1)
    sys.exit(interactive_login(sys.argv[1]))

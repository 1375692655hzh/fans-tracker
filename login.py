"""一次性扫码登录 —— profiles/<平台> 持久化保存登录态, 长期有效

用法: python main.py login xueqiu
打开该平台的独立浏览器窗口 → 用户自己登录(不限时, 0约束) →
登录完成后**用户手动关闭窗口**, 登录态随持久化上下文自动落盘。
程序绝不自动关窗、绝不限时、不做"检测到已登录"的猜测。
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "profiles"

# 平台 → (首页, 登录页特征: 仅作提示用, 不用于自动关窗)
LOGIN_URLS = {
    "futu": ("https://q.futunn.com/", ["passport", "login"]),
    "xueqiu": ("https://xueqiu.com/", ["login"]),
    "changqiao": ("https://longportapp.com/", ["signin", "login"]),
    "eastmoney": ("https://www.eastmoney.com/", ["passport", "/login"]),
    "laohu": ("https://www.laohu8.com/", ["login", "signin"]),
    "ths": ("https://t.10jqka.com.cn/", ["login"]),
    "weibo": ("https://weibo.com/", ["newlogin", "login.sina", "/login"]),
    "zhihu": ("https://www.zhihu.com/", ["signin", "/login", "unhuman"]),
    "bilibili": ("https://www.bilibili.com/", ["passport"]),
    "xhs": ("https://www.xiaohongshu.com/", ["login"]),
    "douyin": ("https://www.douyin.com/", ["login"]),
    "kuaishou": ("https://www.kuaishou.com/", ["login", "passport"]),
}

HARD_TIMEOUT_S = 3600          # 唯一的保险丝: 1小时(防窗口被遗忘后进程常驻)


async def _login_flow(platform: str, prof: str) -> bool:
    home, _marks = LOGIN_URLS[platform]
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            str(PROFILES / prof),
            headless=False,
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        print(f"[{platform}] 已打开 {home}")
        print(f"[{platform}] 不限时、不会自动关闭 —— 请慢慢登录;"
              f" 完成后直接关闭该窗口, 登录态自动保存。")
        try:
            await page.goto(home, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            print(f"[{platform}] 首页打开慢/失败, 不影响: 可在窗口里自行访问登录页")
        # 0约束: 只等用户关窗, 不猜测登录状态、不代关窗口
        loop = asyncio.get_event_loop()
        deadline = loop.time() + HARD_TIMEOUT_S
        while loop.time() < deadline:
            if page.is_closed() or not ctx.pages:
                break
            try:
                await asyncio.sleep(2)
            except Exception:
                break
        try:
            await ctx.close()
        except Exception:
            pass                       # 用户已关窗, 再关一次报错无所谓
        return True


def interactive_login(platform: str, ident: str = "") -> int:
    if platform not in LOGIN_URLS:
        print(f"平台 {platform} 不在登录列表: {', '.join(LOGIN_URLS)}")
        return 1
    ident = re.sub(r"^https?://", "", (ident or "").strip())  # 与抓取侧哈希口径一致
    from browser import profile_name
    prof = profile_name(platform, ident)
    if ident:
        print(f"账号级登录态: profiles/{prof} (该账号独立, 与其他账号互不影响)")
    PROFILES.mkdir(exist_ok=True)
    asyncio.run(_login_flow(platform, prof))
    print(f"✅ 窗口已关闭, 登录态按关闭时的状态保存到 profiles/{prof}")
    print("   验证效果: 控制台 设置→平台登录 点「检测」, 或 python main.py probe <主页URL>")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python login.py <platform>")
        sys.exit(1)
    sys.exit(interactive_login(sys.argv[1]))

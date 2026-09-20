"""浏览器会话管理 —— 移植 auto-publisher 双模式

CDP 优先: 本机 Chrome 开了调试口(9222)就接管, 复用日常登录态
         (chrome_debug.bat / chrome --remote-debugging-port=9222)。
回退: 逐平台 profiles/<平台> 独立登录态窗口(python main.py login <平台> 预先扫码)。
"""

import hashlib
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
PROFILES = ROOT / "profiles"

ANTI_DETECT_ARGS = ["--disable-blink-features=AutomationControlled"]
HIDE_WEBDRIVER = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"


def profile_name(platform: str, ident: str = "") -> str:
    """登录态目录名: 平台级共用 profiles/<平台>;
    多账号平台(xhs/douyin 创作者后台)每账号独立 profiles/<平台>_<hash8>。"""
    if not ident:
        return platform
    return f"{platform}_{hashlib.md5(ident.encode()).hexdigest()[:8]}"


def cdp_alive(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(cdp_url + "/json/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def resolve_mode(settings: dict) -> str:
    """settings.browser.mode: auto/cdp/own → 实际生效模式 cdp/own。"""
    b = settings.get("browser") or {}
    mode = (b.get("mode") or "auto").lower()
    if mode == "auto":
        return "cdp" if cdp_alive(b.get("cdp_url", "http://127.0.0.1:9222")) \
            else "own"
    if mode == "cdp":
        return "cdp" if cdp_alive(b.get("cdp_url", "http://127.0.0.1:9222")) \
            else "own"
    return "own"


MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.5 Mobile/15E148 Safari/604.1")


class BrowserSession:
    """统一入口: acquire_page(platform) 拿一个带登录态的 page, 用完 release。

    cdp 模式: 全程共用一个新开 tab(借用户 Chrome 的登录态)。
    own 模式: 同一平台共用一个持久化 context, 换平台才换 context。
    acquire_mobile_page(): 手机UA的无头独立页(小红书短链公开页兜底)。
    """

    def __init__(self, settings: dict, logger):
        self.settings = settings
        self.log = logger
        self.mode = resolve_mode(settings)
        self._pw = None
        self._browser = None          # cdp 模式的 browser
        self._page = None             # cdp 模式的共享 tab
        self._ctx = None              # own 模式当前 platform 的 context
        self._ctx_platform = ""
        self._mobile_browser = None   # 手机UA兜底浏览器(小红书公开页)
        self._mobile_ctx = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        if self.mode == "cdp":
            cdp_url = (self.settings.get("browser") or {}).get(
                "cdp_url", "http://127.0.0.1:9222")
            self._browser = await self._pw.chromium.connect_over_cdp(
                cdp_url, timeout=15000)
            ctx = (self._browser.contexts[0]
                   if self._browser.contexts
                   else await self._browser.new_context())
            await ctx.add_init_script(HIDE_WEBDRIVER)
            self._page = await ctx.new_page()
            self._page.set_default_timeout(45000)
            self.log.info(f"浏览器: 已接管本机 Chrome ({cdp_url}), 复用日常登录态")
        else:
            self.log.info("浏览器: 独立登录态窗口模式"
                          "(需登录的平台先 python main.py login <平台>)")
        return self

    async def acquire_page(self, platform: str, ident: str = ""):
        """返回 (page, ctx_owned_by_caller)。own 模式换 profile 时关旧开新。

        ident: 多账号平台(xhs/douyin)每账号独立登录态目录; 其余传空共用平台级。
        """
        prof = profile_name(platform, ident)
        if self.mode == "cdp":
            return self._page, False
        if self._ctx_platform != prof:
            await self._close_ctx()
            headless = bool((self.settings.get("browser") or {})
                            .get("headless", False))
            kwargs = dict(
                headless=headless,
                viewport={"width": 1280, "height": 860},
                locale="zh-CN",
                args=ANTI_DETECT_ARGS,
                ignore_default_args=["--enable-automation"],
            )
            ch = (self.settings.get("browser") or {}).get("channel", "chromium")
            if ch in ("chrome", "msedge"):
                kwargs["channel"] = ch
            PROFILES.mkdir(exist_ok=True)
            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(PROFILES / prof), **kwargs)
            await self._ctx.add_init_script(HIDE_WEBDRIVER)
            self._ctx_platform = prof
            page = (self._ctx.pages[0]
                    if self._ctx.pages
                    else await self._ctx.new_page())
            page.set_default_timeout(45000)
            return page, True
        page = (self._ctx.pages[-1]
                if self._ctx.pages
                else await self._ctx.new_page())
        page.set_default_timeout(45000)
        return page, True

    async def acquire_mobile_page(self):
        """手机UA的无头独立 page(匿名公开页兜底)。调用方用完 close(page)。"""
        if self._mobile_ctx is None:
            self._mobile_browser = await self._pw.chromium.launch(
                headless=True)
            self._mobile_ctx = await self._mobile_browser.new_context(
                user_agent=MOBILE_UA, viewport={"width": 390, "height": 844},
                locale="zh-CN",
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"})
        page = await self._mobile_ctx.new_page()
        page.set_default_timeout(45000)
        return page

    async def _close_ctx(self):
        if self._ctx is not None:
            try:
                await self._ctx.close()
            except Exception:
                pass
            self._ctx, self._ctx_platform = None, ""

    async def __aexit__(self, *exc):
        await self._close_ctx()
        for ctx in (self._mobile_ctx,):
            if ctx is not None:
                try:
                    await ctx.close()
                except Exception:
                    pass
        self._mobile_ctx = None
        if self._mobile_browser is not None:
            try:
                await self._mobile_browser.close()
            except Exception:
                pass
            self._mobile_browser = None
        if self._page is not None:
            try:                      # cdp: 只关自己开的 tab, 不动用户 Chrome
                await self._page.close()
            except Exception:
                pass
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass

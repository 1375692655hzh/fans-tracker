"""平台抓取器注册表

API 平台(x/youtube): 纯 HTTP, 无浏览器依赖。
浏览器平台: 见 browser_page.SPEC, 由 main.crawl 统一走 Playwright。
"""

from . import bilibili_api, x_fxtwitter, youtube_api

# 纯 API 平台: platform → fetch(account) -> result dict
API_FETCHERS = {
    "x": x_fxtwitter.fetch,
    "youtube": youtube_api.fetch,
}

from .browser_page import BROWSER_PLATFORMS, SPEC  # noqa: E402

PLATFORM_LABELS = {k: v["label"] for k, v in SPEC.items()}
PLATFORM_LABELS["x"] = "X"
PLATFORM_LABELS["youtube"] = "YouTube"

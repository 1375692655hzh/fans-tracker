"""B站 UP 主数据 —— 公开 HTTP API 优先, 空间页浏览器补充

- 粉丝: GET https://api.bilibili.com/x/relation/stat?vmid={mid}  (公开稳定)
- 投稿数/总播放: 公开接口已要求 Wbi 签名, 走 space.bilibili.com/{mid}
  页面提取(在 browser_page 的 bilibili SPEC 里配 api_hook 调本模块)
"""

import re

import requests


def extract_mid(account: dict) -> str:
    """从空间链接提取 mid: space.bilibili.com/{mid} 或纯数字。"""
    url = (account.get("url") or "").strip()
    m = re.search(r"space\.bilibili\.com/(\d+)", url)
    if m:
        return m.group(1)
    return url if url.isdigit() else (account.get("handle") or "").strip()


def fetch_followers(mid: str) -> tuple:
    """relation/stat → (followers:int|None, err:str)。公开接口无需登录。"""
    if not mid:
        return None, "无法从链接解析 mid"
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/relation/stat",
            params={"vmid": mid},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                     "Referer": "https://space.bilibili.com/"},
            timeout=20)
        resp.raise_for_status()
        d = resp.json()
        if d.get("code") != 0:
            return None, f"接口 code={d.get('code')} {d.get('message', '')[:60]}"
        return int((d.get("data") or {}).get("follower") or 0), ""
    except Exception as e:
        return None, f"relation/stat 请求失败: {str(e)[:100]}"

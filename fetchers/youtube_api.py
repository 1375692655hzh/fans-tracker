"""YouTube 频道数据 —— Google 官方 Data API v3(免费), 无需登录

GET https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&forHandle={handle}&key={KEY}
→ statistics: subscriberCount(订阅) / videoCount(视频数) / viewCount(累计播放)
订阅数被博主隐藏时 subscriberCount 缺失 → 记 None。
"""

import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://www.googleapis.com/youtube/v3/channels"


def _api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if key:
        return key.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("YOUTUBE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch(account: dict) -> dict:
    handle = (account.get("handle") or "").strip().lstrip("@")
    r = {"name": None, "followers": None, "content": None, "views": None,
         "errors": {}}
    if not handle:
        r["errors"] = {"followers": "缺少 handle(@频道名)"}
        return r
    key = _api_key()
    if not key:
        r["errors"] = {"followers": "未配置 YOUTUBE_API_KEY(见 .env / README)"}
        return r
    try:
        resp = requests.get(API, params={
            "part": "snippet,statistics",
            "forHandle": handle,
            "key": key,
        }, timeout=30)
        if resp.status_code == 403:
            r["errors"] = {"followers": "API Key 无效或未启用 YouTube Data API v3"}
            return r
        if resp.status_code == 404:
            r["errors"] = {"followers": f"@{handle} 频道不存在"}
            return r
        resp.raise_for_status()
        items = (resp.json() or {}).get("items") or []
        if not items:
            r["errors"] = {"followers": f"@{handle} 未匹配到频道"}
            return r
        ch = items[0]
        st = ch.get("statistics") or {}
        r["name"] = (ch.get("snippet") or {}).get("title") or f"@{handle}"
        if st.get("hiddenSubscriberCount"):
            r["errors"]["followers"] = "订阅数被博主隐藏"
        else:
            r["followers"] = int(st["subscriberCount"]) if st.get(
                "subscriberCount", "").isdigit() else None
        r["content"] = int(st["videoCount"]) if st.get(
            "videoCount", "").isdigit() else None
        r["views"] = int(st["viewCount"]) if st.get(
            "viewCount", "").isdigit() else None
    except Exception as e:
        r["errors"] = {"followers": f"YouTube API 请求失败: {str(e)[:120]}"}
    return r

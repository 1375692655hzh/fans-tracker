"""YouTube 频道数据 —— Google 官方 Data API v3(免费), 无需登录

口径(用户确认): 内容数=昨日发布视频数; 阅读/播放量=最新一条视频的播放量。
链路: channels(订阅) → search(order=date)取最新 → 本地按日期筛昨日
   → videos.list 拿最新视频播放量。
注意: search 的 publishedAfter 窗口参数对刚发布视频不可靠(实测漏数据),
   所以用"取最新列表+本地筛选"。
订阅数被博主隐藏时缺失 → 记 None。
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://www.googleapis.com/youtube/v3/channels"
SEARCH = "https://www.googleapis.com/youtube/v3/search"
VIDEOS = "https://www.googleapis.com/youtube/v3/videos"


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

        # 昨日发布数 + 最新视频播放量
        s = requests.get(SEARCH, params={
            "part": "snippet", "channelId": ch["id"], "order": "date",
            "type": "video", "maxResults": 15, "key": key}, timeout=30)
        s.raise_for_status()
        sitems = (s.json() or {}).get("items") or []
        r["content"] = 0
        if sitems:
            # 本地时区的"昨天"(发布时间是 UTC, 转本地再比日期)
            tz = datetime.now().astimezone().tzinfo
            yesterday = (datetime.now(tz) - timedelta(days=1)).date()
            for it in sitems:
                pub = datetime.fromisoformat(
                    it["snippet"]["publishedAt"].replace("Z", "+00:00")
                ).astimezone(tz).date()
                if pub == yesterday:
                    r["content"] += 1
            latest = sitems[0]["id"]["videoId"]
            v = requests.get(VIDEOS, params={
                "part": "statistics", "id": latest, "key": key}, timeout=30)
            v.raise_for_status()
            vitems = (v.json() or {}).get("items") or []
            if vitems:
                vc = (vitems[0].get("statistics") or {}).get("viewCount")
                r["views"] = int(vc) if str(vc or "").isdigit() else None
    except Exception as e:
        r["errors"] = {"followers": f"YouTube API 请求失败: {str(e)[:120]}"}
    return r

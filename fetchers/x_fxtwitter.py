"""X(Twitter) 账号数据 —— FxTwitter 公开 API v2, 无需登录

GET /2/profile/{handle}/statuses → 用户时间线(约20条/页, cursor翻页)
每条含 views(公开浏览量) / created_timestamp / replying_to(=null即原创非回复)。
口径: content = 24h内原创帖数(排除回复与纯转推), views = 这些帖浏览量合计;
content_total(累计发帖)照存, 时间线不可用时由 main.py 作差兜底。
"""

import time

import requests

API = "https://api.fxtwitter.com/2/profile/{handle}/statuses"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
           "Accept": "application/json"}
MAX_PAGES = 5                                  # 翻页安全上限(覆盖24h足够)


def _is_original(t: dict) -> bool:
    """原创帖 = 非回复 且 非纯转推(引用帖算原创)。"""
    if t.get("replying_to") is not None:
        return False
    if str(t.get("text") or "").startswith("RT @"):
        return False
    return not any(k in t for k in ("retweeted_status", "retweet"))


def _fetch_page(handle: str, cursor: str = "") -> dict:
    params = {"cursor": cursor} if cursor else {}
    resp = requests.get(API.format(handle=handle), headers=HEADERS,
                        params=params, timeout=30)
    if resp.status_code == 404:
        raise ValueError(f"@{handle} 不存在(404)")
    resp.raise_for_status()
    d = resp.json() or {}
    if d.get("code") != 200:
        raise ValueError(f"接口返回 code={d.get('code')}")
    return d


def fetch(account: dict) -> dict:
    handle = (account.get("handle") or "").strip().lstrip("@")
    if not handle:
        return {"name": None, "followers": None, "content": None, "views": None,
                "errors": {"followers": "缺少 handle(@用户名)"}}
    r = {"name": None, "followers": None, "content": None, "views": None,
         "content_total": None, "errors": {}}
    try:
        cutoff = time.time() - 86400
        page, cursor, tweets, guard = {}, "init", [], 0
        while cursor and guard < MAX_PAGES:    # 翻页直到覆盖满24h
            page = _fetch_page(handle, cursor if cursor != "init" else "")
            results = page.get("results") or []
            tweets.extend(t for t in results if t.get("id") not in
                          {x.get("id") for x in tweets})
            ts = [t.get("created_timestamp") for t in results
                  if t.get("created_timestamp")]
            if not ts or min(ts) < cutoff:     # 本页已老于24h, 不用再翻
                break
            cursor = page.get("cursor") or ""
            guard += 1

        author = next((t.get("author") for t in tweets if t.get("author")),
                      None)
        if author:
            r["name"] = author.get("name") or f"@{handle}"
            followers = author.get("followers")
            r["followers"] = followers if isinstance(followers, int) \
                and followers >= 0 else None
            if r["followers"] is None:
                r["errors"]["followers"] = "字段缺失或非法"
            total = author.get("statuses")
            if isinstance(total, int) and total >= 0:
                r["content_total"] = total
        elif not tweets:
            raise ValueError("时间线为空且无用户信息")

        origs = sorted(
            (t for t in tweets if _is_original(t)
             and (t.get("created_timestamp") or 0) >= cutoff),
            key=lambda t: -(t.get("created_timestamp") or 0))
        r["content"] = len(origs)
        r["views"] = sum(int(t.get("views") or 0) for t in origs)
        r["content_detail"] = [
            f"{time.strftime('%m-%d %H:%M', time.localtime(t['created_timestamp']))}"
            f" 浏览{t.get('views')} 赞{t.get('likes')} {str(t.get('text'))[:30]}"
            for t in origs[:20]]
    except Exception as e:
        r["errors"] = {"followers": f"FxTwitter 请求失败: {str(e)[:120]}"}
    return r

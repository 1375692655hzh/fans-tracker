"""X(Twitter) 账号数据 —— FxTwitter 公开 API, 无需登录

GET https://api.fxtwitter.com/{handle}
→ user: { name, followers, tweets, ... }   (阅读量/曝光不公开, 记 None)
"""

import requests

API_BASE = "https://api.fxtwitter.com/"


def fetch(account: dict) -> dict:
    handle = (account.get("handle") or "").strip().lstrip("@")
    if not handle:
        return {"name": None, "followers": None, "content": None, "views": None,
                "errors": {"followers": "缺少 handle(@用户名)"}}
    r = {"name": None, "followers": None, "content": None, "views": None,
         "errors": {}}
    try:
        resp = requests.get(
            API_BASE + handle,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                     "Accept": "application/json"},
            timeout=30)
        if resp.status_code == 404:
            r["errors"] = {"followers": f"@{handle} 不存在(404)"}
            return r
        resp.raise_for_status()
        data = resp.json()
        user = (data or {}).get("user") or {}
        if not user:
            r["errors"] = {"followers": f"返回无 user 字段: {str(data)[:120]}"}
            return r
        r["name"] = user.get("name") or f"@{user.get('screen_name', handle)}"
        r["followers"] = user.get("followers")
        # 口径=昨日发布数: FxTwitter 无公开时间线接口, 拿不到每日推文
        # (总推文数会误当"昨日数", 不填); 曝光量 X 本就不公开
        for k in ("followers",):
            if not isinstance(r[k], int) or r[k] < 0:
                r[k] = None
                r["errors"][k] = "字段缺失或非法"
    except Exception as e:
        r["errors"] = {"followers": f"FxTwitter 请求失败: {str(e)[:120]}"}
    return r

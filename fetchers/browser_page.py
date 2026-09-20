"""通用平台主页抓取器 —— Playwright 打开账号主页, 提取 粉丝/内容数/阅读播放量

移植 auto-publisher followers.py 的成熟机制:
  4 层提取(平台专属正则 > 链接文本 > 标签旁兄弟数字 > 全文正则) + parse_count。
每平台一段 SPEC(labels/正则/是否需登录), 拿不到的指标记 None → 表格填 "-"。
选择器不准的平台用 `python main.py probe <url>` 现场看候选文本再调 SPEC。
"""

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = ROOT / "logs" / "screenshots"

# 数字统一形态: 12345 / 12,345 / 1.2万 / 3.4w / 980+
NUM = r"(\d[\d,.]*\s*[万亿wWkK]?)"

# ---------- 平台规格 ----------
# followers/content/views 各支持: prio 平台专属权威正则 / labels 页面文案
# needs_login: True 表示建议带登录态(未登录多半被墙或看不到)
SPEC = {
    "futu": {
        "label": "富途",
        # 主页强制登录(未登录重定向 passport), 复用 auto-publisher 登录态
        # 统计板 "128 关注 | 5187 粉丝 | 2.1万 +7999 来访"(来访两段需求和)
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},   # 页面无总内容数(文章标题含日期易误配)
        "views": {"labels": [], "prio_res": [
            r"((?:\d[\d,.]*\s*[万亿wWkK]?\s*\+\s*)*\d[\d,.]*\s*[万亿wWkK]?)\s*来访"]},
        "login_marks": ["passport", "login"], "needs_login": True,
    },
    "xueqiu": {
        "label": "雪球",
        # 页面头部 "47 关注 | 624 粉丝"(数字在前); 帖子 "帖子 563"
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["帖子"], "prio_res": [r"帖子\s*[：:(（]?\s*" + NUM]},
        "views": {"labels": []},
        "login_marks": ["login"], "needs_login": False,
    },
    "changqiao": {
        "label": "长桥",
        # 页面 "7关注 | 2596关注者"
        "labels": ["粉丝", "关注者", "Followers"],
        "prio_res": [NUM + r"\s*关注者", NUM + r"\s*粉丝"],
        "content": {"labels": ["帖子", "主题", "动态"]},
        "views": {"labels": []},
        "login_marks": ["signin", "login"], "needs_login": False,
    },
    "eastmoney": {
        "label": "东方财富",
        # i 页头部 "160粉丝0关注 179获赞"; 页面无总阅读量(日期会误配, 不抓)
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["文章", "帖子", "微博"]},
        "views": {"labels": []},
        "login_marks": ["passport", "/login"], "needs_login": False,
    },
    "laohu": {
        "label": "老虎",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["帖子", "文章"]},
        "views": {"labels": ["阅读"]},
        "login_marks": ["login", "signin"], "needs_login": False,
    },
    "ths": {
        "label": "同花顺",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["帖子", "文章", "微博"]},
        "views": {"labels": ["阅读"]},
        "login_marks": ["login"], "needs_login": False,
    },
    "weibo": {
        "label": "微博",
        # 主页 "9粉丝 | 10关注 | 24转评赞"; 内容数仅登录后"全部微博(N)"
        "labels": ["粉丝"], "prio_res": [
            r"全部粉丝\s*[（(]\s*" + NUM + r"\s*[）)]", NUM + r"\s*粉丝"],
        "content": {"labels": [], "prio_res": [
            r"全部微博\s*[（(]\s*" + NUM + r"\s*[）)]"]},
        "views": {"labels": []},
        "login_marks": ["newlogin", "login.sina", "/login"], "needs_login": False,
    },
    "zhihu": {
        "label": "知乎",
        # 主页 "关注了 1 | 关注者 58"; 内容栏 "回答3 | 文章169 | 专栏1"
        # 匿名访问会被风控(unhuman), 必须登录态(已复用 auto-publisher)
        "labels": ["关注者"], "prio_res": [
            r"关注者\s*[：:]?\s*" + NUM, NUM + r"\s*关注者"],
        "content": {"labels": ["文章"], "prio_res": [r"文章\s*(\d+)"]},
        "views": {"labels": []},   # 总阅读量仅创作中心有, 公开页无
        "login_marks": ["signin", "/login", "unhuman"], "needs_login": True,
    },
    "bilibili": {
        "label": "B站",
        # 空间页 "关注数 686 | 粉丝数 1798.9万", 投稿 "999+"(平台封顶)
        "labels": ["粉丝"], "prio_res": [r"粉丝数?\s*[量：:]*\s*" + NUM],
        "content": {"labels": ["投稿"], "prio_res": [r"投稿\s*[（(:：]?\s*" + NUM]},
        "views": {"labels": []},   # 总播放匿名不可见(需登录 upstat)
        "login_marks": ["passport"], "needs_login": False,
        "api_hook": "bilibili",   # 粉丝走 relation/stat 公开接口(见 bilibili_api)
    },
    "xhs": {
        "label": "小红书",
        "labels": ["粉丝"], "prio_res": [r"粉丝\s*[（(:：]?\s*" + NUM],
        "content": {"labels": ["笔记"], "prio_res": [r"笔记\s*[（(:：]?\s*" + NUM]},
        "views": {"labels": []},   # 小红书无公开总阅读, 获赞不等于阅读
        "login_marks": ["login"], "needs_login": True,
    },
    "douyin": {
        "label": "抖音",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["作品"], "prio_res": [r"作品\s*[（(:：]?\s*" + NUM]},
        "views": {"labels": []},
        "login_marks": ["login"], "needs_login": True,
    },
    "kuaishou": {
        "label": "快手",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": ["作品", "视频"]},
        "views": {"labels": ["播放"]},
        "login_marks": ["login"], "needs_login": False,
    },
    # 微信封闭生态, 需后台登录, 本期跳过(接口预留)
    "weixin_gzh": {"label": "公众号", "disabled": "需公众号后台权限, 未开通"},
    "weixin_sph": {"label": "视频号", "disabled": "需视频号助手后台权限, 未开通"},
}

BROWSER_PLATFORMS = [k for k, v in SPEC.items() if not v.get("disabled")]


# ---------- 数字解析(移植 followers.py) ----------

def parse_count(raw):
    """'1.2万'/'12,345'/'980+'/'3.4w' → int; 解析不了返回 None"""
    if raw is None:
        return None
    s = re.sub(r"[\s,，+]", "", str(raw).strip())
    m = re.match(r"^(\d+(?:\.\d+)?)([万亿wWkK]?)$", s)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2)
    if unit in ("万", "w", "W"):
        v *= 10000
    elif unit == "亿":
        v *= 100000000
    elif unit in ("k", "K"):
        v *= 1000
    return int(round(v))


# ---------- 页面提取(三级策略, prio 正则由 Python 传入避免转义问题) ----------

EXTRACT_JS = """(cfg) => {
    const numRe = /(\\d[\\d,.]*\\s*[万亿wWkK]?)/;
    const body = (document.body && document.body.innerText || '')
        .replace(/\\u00a0/g, ' ');
    const pick = (labels, prio) => {
        const out = [];
        const push = s => { const t = String(s||'').trim();
            if (t && !out.includes(t)) out.push(t); };
        // 1) 平台专属权威正则(命中即收, 避免误抓列表里别人的数字)
        for (const src of (prio || [])) {
            const m = new RegExp(src).exec(body);
            if (m) { push(m[1]); }
        }
        // 2) 标签元素旁的兄弟数字(元素文本就是"粉丝/作品"这类短标签)
        for (const el of document.querySelectorAll(
                'span,div,li,dt,dd,p,em,i,b,strong,a,button')) {
            if (el.children.length > 1) continue;
            const t = (el.innerText || '').replace(/\\s+/g, '').trim();
            if (!t || t.length > 8) continue;
            if (!labels.some(l => t === l || t.startsWith(l) || t.endsWith(l)))
                continue;
            for (const scope of [el.previousElementSibling,
                                 el.nextElementSibling, el.parentElement]) {
                if (!scope) continue;
                const m = numRe.exec(
                    (scope.innerText || '').replace(/\\u00a0/g, ' '));
                if (m) { push(m[1]); break; }
            }
        }
        // 3) 全文 "数字+标签" / "标签+数字"
        for (const l of labels) {
            let m = new RegExp('(\\\\d[\\\\d,.]*\\\\s*[万亿wWkK]?)\\\\s*' + l).exec(body)
                 || new RegExp(l + '\\\\s*[:：(（]?\\\\s*(\\\\d[\\\\d,.]*\\\\s*[万亿wWkK]?)')
                       .exec(body);
            if (m) push(m[1]);
        }
        // 粉丝类: 再看 粉丝/关注 链接文本(followers 链接里的数字最可靠)
        if (out.length === 0 && labels.some(l => l.indexOf('粉丝') >= 0)) {
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (!/fans|followers?|relate=fans/i.test(h)) continue;
                const m = numRe.exec(
                    (a.innerText || '').replace(/\\u00a0/g, ' '));
                if (m) push(m[1]);
            }
        }
        return out.slice(0, 5);
    };
    return {
        followers: pick(cfg.fLabels, cfg.fPrio),
        content: pick(cfg.cLabels, cfg.cPrio),
        views: pick(cfg.vLabels, cfg.vPrio),
        title: (document.title || '').slice(0, 80),
        h1: ((document.querySelector('h1') || {}).innerText || '')
            .replace(/\\s+/g, ' ').slice(0, 40),
    };
}"""


async def _shot(page, tag):
    try:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(
            path=str(SHOT_DIR / f"{tag}_{datetime.now():%H%M%S}.png"))
    except Exception:
        pass


def _is_login_page(url: str, marks) -> bool:
    u = (url or "").lower()
    return any(m.lower() in u for m in marks)


def _first_int(cands):
    for c in (cands or []):
        if "+" in c:                 # "2.1万 +7999" 这类两段累计 → 求和
            parts = [parse_count(p) for p in c.split("+")]
            if all(isinstance(p, int) for p in parts) and parts:
                return sum(parts), c
            continue
        v = parse_count(c)
        if v is not None:
            return v, c
    return None, ""


async def extract_account(page, account, spec, settings, logger):
    """打开单个账号主页轮询提取 → fetch result dict。

    page: 已带登录态的页面(调用方保证); settings 供等待参数。
    """
    url = (account.get("url") or "").strip()
    key = account["_key"]
    r = {"name": None, "followers": None, "content": None, "views": None,
         "errors": {}}
    wait = int((settings.get("crawl") or {}).get("page_wait_ms", 2500))
    rounds = int((settings.get("crawl") or {}).get("page_rounds", 8))
    cfg = {
        "fLabels": spec.get("labels", []),
        "fPrio": spec.get("prio_res", []),
        "cLabels": (spec.get("content") or {}).get("labels", []),
        "cPrio": (spec.get("content") or {}).get("prio_res", []),
        "vLabels": (spec.get("views") or {}).get("labels", []),
        "vPrio": (spec.get("views") or {}).get("prio_res", []),
    }
    try:
        await page.goto(url, wait_until="domcontentloaded",
                        timeout=int((settings.get("crawl") or {})
                                    .get("nav_timeout_ms", 45000)))
    except Exception as e:
        await _shot(page, f"{key}_goto_fail")
        r["errors"] = {"followers": f"打开主页失败: {str(e)[:100]}"}
        return r
    found_title = ""
    for _ in range(rounds):
        await page.wait_for_timeout(wait)
        if _is_login_page(page.url, spec.get("login_marks", [])):
            r["errors"] = {"followers": "未登录/登录态失效(先 python main.py login)"}
            await _shot(page, f"{key}_loginwall")
            return r
        try:
            out = await page.evaluate(EXTRACT_JS, cfg)
        except Exception:
            out = {}
        found_title = (out or {}).get("title") or found_title
        if r["followers"] is None:
            r["followers"], raw = _first_int(out.get("followers"))
            if r["followers"] is not None:
                logger.info(f"[{key}] 粉丝 {r['followers']} (原文 {raw!r})")
        if r["content"] is None:
            r["content"], raw = _first_int(out.get("content"))
            if r["content"] is not None:
                logger.info(f"[{key}] 内容数 {r['content']} (原文 {raw!r})")
        if r["views"] is None:
            r["views"], raw = _first_int(out.get("views"))
            if r["views"] is not None:
                logger.info(f"[{key}] 阅读播放 {r['views']} (原文 {raw!r})")
        # 粉丝是核心指标: 拿到粉丝且(内容或阅读拿不到但已轮询过半)就提前收
        if r["followers"] is not None and _ > rounds // 2:
            break
        if None not in (r["followers"], r["content"], r["views"]):
            break
    # 昵称: <title> 前段 / 页面 h1, 谁可用用谁
    r["name"] = (_clean_title_name(found_title)
                 or _clean_title_name(out.get("h1") or "")) or r["name"]
    for m in ("followers", "content", "views"):
        if r[m] is None and m not in r["errors"]:
            r["errors"][m] = "页面未出现该指标(公开页无此数据)"
    if r["followers"] is None:
        await _shot(page, f"{key}_extract_fail")
    return r


def _clean_title_name(title: str) -> str:
    """从页面标题猜昵称: 'XXX的个人主页-富途牛牛' → 'XXX'; 保守截断。"""
    if not title:
        return ""
    t = title.split("-")[0].split("_")[0].split("｜")[0].strip()
    for suf in ("的个人主页", "的个人中心", "的个人空间", "的主页", "的主页",
                "个人主页", "的微博", "的直播间"):
        if t.endswith(suf):
            t = t[:-len(suf)]
    t = t.lstrip("@").strip()
    return t[:24] if 0 < len(t) <= 24 else ""

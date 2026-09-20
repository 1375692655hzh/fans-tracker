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
# followers: prio 平台专属权威正则 / labels 页面文案
# items(可选): 「昨日内容」口径 —— 内容列表的 日期/浏览 正则。
#   date_res 捕获日期 token(须带 HH:MM 或发布动词锚定, 防止标题里的数字误配);
#   views_res 可选, 每条内容的浏览数; window=日期与浏览视为同条目的最大字符距。
# 配了 items 的平台: 内容数=昨日发布数, 阅读播放量=昨日条目浏览合计。
SPEC = {
    "futu": {
        "label": "富途",
        # 主页强制登录(未登录重定向 passport), 复用 auto-publisher 登录态
        # 统计板 "128 关注 | 5187 粉丝 | 2.1万 +7999 来访"(来访两段需求和)
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},   # 页面无总内容数(文章标题含日期易误配)
        "views": {"labels": [], "prio_res": [
            r"((?:\d[\d,.]*\s*[万亿wWkK]?\s*\+\s*)*\d[\d,.]*\s*[万亿wWkK]?)\s*来访"]},
        # feed: "…浏览 9.5万|作者|参与了话题|·|09/18 19:11|专栏 标题…"
        # (只认发布/参与类动作, "赞了"不算; | 分隔符要放行)
        "items": {
            "date_res": r"(?:发表了文章|发布了|原创了|参与了话题|留下了心情)"
                       r"[\s\S]{0,30}?"
                       r"(\d+小时前|\d+分钟前|昨天|前天|今天|"
                       r"\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2})",
            "views_res": r"浏览\s*[：:]?\s*" + NUM, "window": 160,
        },
        "login_marks": ["passport", "login"], "needs_login": True,
    },
    "xueqiu": {
        "label": "雪球",
        # 页面头部 "47 关注 | 624 粉丝"
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
        # feed: "昨天 20:05 · 来自雪球" / "09-16 20:31 ·" (标题里的日期无时间后缀)
        "items": {
            "date_res": r"(昨天|前天|今天|\d{1,2}-\d{1,2})\s*\d{1,2}:\d{2}",
        },
        "login_marks": ["login"], "needs_login": False,
    },
    "changqiao": {
        "label": "长桥",
        # 页面 "7关注 | 2596关注者"
        "labels": ["粉丝", "关注者", "Followers"],
        "prio_res": [NUM + r"\s*关注者", NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
        # feed: "发布了长文 | 昨日 19:59"
        "items": {
            "date_res": r"(昨日|昨天|前天|今天|\d{1,2}-\d{1,2})\s*\d{1,2}:\d{2}",
        },
        "login_marks": ["signin", "login"], "needs_login": False,
    },
    "eastmoney": {
        "label": "东方财富",
        # i 页头部 "160粉丝0关注 179获赞"; 帖子列表 "发布于 09-18 19:03 | 189 阅读"
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
        "items": {
            "date_res": r"发布于\s*(昨天|前天|今天|\d+小时前|\d{2}-\d{2})",
            "views_res": NUM + r"\s*阅读", "window": 60, "pair": "after",
        },
        "login_marks": ["passport", "/login"], "needs_login": False,
    },
    "laohu": {
        "label": "老虎",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
        "login_marks": ["login", "signin"], "needs_login": False,
    },
    "ths": {
        "label": "同花顺",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
        "login_marks": ["login"], "needs_login": False,
    },
    "weibo": {
        "label": "微博",
        # 主页 "9粉丝 | 10关注 | 24转评赞"; feed 匿名截断, 登录后完整
        "labels": ["粉丝"], "prio_res": [
            r"全部粉丝\s*[（(]\s*" + NUM + r"\s*[）)]", NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},   # 微博不公开阅读量
        "items": {
            "date_res": r"(今天|昨天|前天|\d{1,2}月\d{1,2}日)\s*\d{1,2}:\d{2}",
        },
        "login_marks": ["newlogin", "login.sina", "/login"], "needs_login": False,
    },
    "zhihu": {
        "label": "知乎",
        # 主页 "关注了 1 | 关注者 58"; 动态 "2026-09-18 19:00 | 发表了文章"
        "labels": ["关注者"], "prio_res": [
            r"关注者\s*[：:]?\s*" + NUM, NUM + r"\s*关注者"],
        "content": {"labels": []},
        "views": {"labels": []},   # 总阅读量仅创作中心有, 公开页无
        "items": {
            "date_res": r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}",
        },
        "login_marks": ["signin", "/login", "unhuman"], "needs_login": True,
    },
    "bilibili": {
        "label": "B站",
        # 空间页 "关注数 686 | 粉丝数 1798.9万"; 投稿列表卡不带日期→昨日口径暂缺
        "labels": ["粉丝"], "prio_res": [r"粉丝数?\s*[量：:]*\s*" + NUM],
        "content": {"labels": []},
        "views": {"labels": []},
        "login_marks": ["passport"], "needs_login": False,
        "api_hook": "bilibili",   # 粉丝走 relation/stat 公开接口(见 bilibili_api)
    },
    "xhs": {
        "label": "小红书",
        "labels": ["粉丝"], "prio_res": [r"粉丝\s*[（(:：]?\s*" + NUM],
        "content": {"labels": []},   # 主页卡片无日期无阅读
        "views": {"labels": []},
        "login_marks": ["login"], "needs_login": True,
    },
    "douyin": {
        "label": "抖音",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},   # 作品网格不带日期(需进详情)
        "views": {"labels": []},
        "login_marks": ["login"], "needs_login": True,
    },
    "kuaishou": {
        "label": "快手",
        "labels": ["粉丝"], "prio_res": [NUM + r"\s*粉丝"],
        "content": {"labels": []},
        "views": {"labels": []},
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
        body: body.slice(0, 30000),
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
    found_body = ""
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
        out = out or {}
        found_title = out.get("title") or found_title
        found_body = out.get("body") or found_body
        if spec.get("items") and _ == 1:   # 滚动触发 feed 懒加载
            try:
                await page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight * .6)")
                await page.wait_for_timeout(1200)
                await page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass
        if r["followers"] is None:
            r["followers"], raw = _first_int(out.get("followers"))
            if r["followers"] is not None:
                logger.info(f"[{key}] 粉丝 {r['followers']} (原文 {raw!r})")
        # 「昨日内容」口径: 拿到正文且有 items 配置即解析一次
        if spec.get("items") and r["content"] is None and found_body:
            from datetime import datetime as _dt
            yi = parse_yesterday_items(found_body, spec["items"],
                                       _dt.now(), logger)
            if yi["dated"] == 0:      # 没解析到任何日期 ≠ 昨日没发
                r.setdefault("errors", {})["content"] = \
                    "页面未解析到内容日期(可能未登录/懒加载)"
            else:
                r["content"] = yi["count"]
                if yi["views"] is not None:
                    r["views"] = yi["views"]
                    logger.info(f"[{key}] 昨日内容 {yi['count']} 条, "
                                f"浏览合计 {yi['views']}")
                elif yi["count"]:
                    logger.info(f"[{key}] 昨日内容 {yi['count']} 条"
                                "(平台不公开浏览)")
        if r["views"] is None and not spec.get("items"):
            r["views"], raw = _first_int(out.get("views"))
            if r["views"] is not None:
                logger.info(f"[{key}] 阅读播放 {r['views']} (原文 {raw!r})")
        # 粉丝是核心指标: 拿到粉丝且其余指标已尽力就提前收
        done_enough = (r["followers"] is not None
                       and (spec.get("items") or r["content"] is not None)
                       and (r["views"] is not None or spec.get("items")
                            or not (spec.get("views") or {}).get("prio_res")))
        if done_enough and _ > rounds // 2:
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


# ---------- 「昨日内容」解析 ----------

def _classify_item_date(token: str, now):
    """日期 token → datetime.date; 认不出返回 None。"""
    from datetime import date, timedelta
    t = token.strip()
    if "昨天" in t or "昨日" in t:
        return (now - timedelta(days=1)).date()
    if "前天" in t:
        return (now - timedelta(days=2)).date()
    if "今天" in t:
        return now.date()
    m = re.search(r"(\d+)小时前", t)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).date()
    if re.search(r"\d+分钟前", t):
        return now.date()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
        return date(y, mo, d) if 1 <= mo <= 12 and 1 <= d <= 31 else None
    m = re.search(r"(\d{1,2})[/月-](\d{1,2})", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return date(now.year, mo, d)
    return None


def parse_yesterday_items(body: str, cfg: dict, now, logger=None) -> dict:
    """从内容列表文本解析昨日发布的内容数与浏览量合计。

    cfg = SPEC["items"]: date_res 必填, views_res/window 可选。
    返回 {"count": int, "views": int|None, "dated": 解析出日期的条目数}。
    """
    from datetime import timedelta
    yesterday = (now - timedelta(days=1)).date()
    dates = [(m.start(), m.group(0))
             for m in re.finditer(cfg["date_res"], body)]
    if not dates:
        return {"count": 0, "views": None, "dated": 0}
    ycnt = sum(1 for _, tok in dates
               if _classify_item_date(tok, now) == yesterday)
    if not cfg.get("views_res"):
        return {"count": ycnt, "views": None, "dated": len(dates)}
    window = int(cfg.get("window", 100))
    pair = cfg.get("pair", "nearest")
    views = []
    for m in re.finditer(cfg["views_res"], body):
        v = parse_count(m.group(1))
        if v is not None:
            views.append((m.start(), v))

    def _nearest(vpos):
        best, bi = None, -1
        for i, (dpos, _) in enumerate(dates):
            if i in used or abs(dpos - vpos) > window:
                continue
            if best is None or abs(dpos - vpos) < best:
                best, bi = abs(dpos - vpos), i
        return bi

    def _directional(vpos, after=True):
        # after: 日期之后到下一日期之前的段内; before: 上一日期之后到本日期段内
        for i, (dpos, _) in enumerate(dates):
            if i in used:
                continue
            nxt = dates[i + 1][0] if i + 1 < len(dates) else len(body)
            if after and dpos < vpos < nxt:
                return i
            if not after and dpos <= vpos < nxt and vpos < nxt:
                return i if vpos >= dpos else None
        return -1

    used, yviews = set(), []
    for pos, v in views:
        i = (_nearest(pos) if pair == "nearest"
             else _directional(pos, after=(pair == "after")))
        if i < 0:
            continue
        used.add(i)
        if _classify_item_date(dates[i][1], now) == yesterday:
            yviews.append(v)
    if logger:
        logger.info(f"    内容条目: 日期{len(dates)}个(昨日{ycnt})/"
                    f"浏览{len(views)}个, 昨日浏览明细{yviews[:5]}")
    return {"count": ycnt,
            "views": sum(yviews) if yviews else None,
            "dated": len(dates)}

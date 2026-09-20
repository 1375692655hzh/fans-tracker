# fans-tracker —— 多平台社媒账号数据追踪 + 腾讯文档自动填报

每天早上 9:00 自动抓取各平台账号的 **累计粉丝 / 内容数 / 阅读·播放量**，
自动计算 **增粉**，写入腾讯文档【每日社媒数据表】中以当日日期命名的
sheet，7 列表头：`账号所有人 | 所属平台 | 账号名称 | 阅读/播放量 | 内容数 | 增粉 | 累计粉丝`
（**写入按表头自动适配**——你在表里增删列/调列序，第二天起跟着走，识别不了的列填 `-`）。

## 多账号登录（小红书 / 抖音）

小红书分**两级方案**，按各账号的登录情况自动选择：

- **已扫码账号（全量）**：创作者平台首页拿粉丝，note-manager
  拿昨日笔记数+每条阅读量。扫码（每号独立登录态目录，互不挤掉）：
  `python main.py login xhs <该号公开主页链接>`
- **未扫码账号（兜底，免登录）**：配 `share_url`（手机 App 分享出来的
  短链 xhslink.cn/…）后，用手机 UA 匿名打开短链抓
  **粉丝数 + 获赞与收藏**（该口径填入表格"阅读/播放量"列）。
  注意：公开页只展示最新 1 条笔记，无日期/阅读，昨日数不可得（如实填 `-`）
- www 公开主页匿名/跨域登录态都会被"安全限制"硬拦（已实测），
  兜底必须走短链+手机UA，这就是为什么账号里要配 share_url

抖音同理（`login_per_account` 已预留）；快手需任一账号登录。

## 各平台补充说明

- **同花顺**: 填手机 App 分享出来的个人主页链接即可(自动识别跳转);
  该平台无公开浏览量, 只有日期与粉丝
- **B站**: 匿名可抓粉丝(API 精确); 昨日投稿数+每条播放需
  `python main.py login bilibili` 扫码一次后自动生效(投稿列表页)
- **快手**: 匿名访问是空壳, `python main.py login kuaishou` 任一账号
  登录后即可看任意公开主页
- **长桥**: 外部页(longportapp.com / longbridge.com)动态列表不稳定,
  内容数抓不到时如实填 `-`; 浏览量平台本就不提供
- **老虎**: 匿名全可见(粉丝/帖子数/每日日期); 列表无阅读量

## 环境要求

- Windows 10/11（计划任务/桌面快捷方式为 Windows 专用）
- Python 3.10+：[python.org/downloads](https://www.python.org/downloads/)
  下载，**安装时勾选 "Add Python to PATH"**
- 其余全部由 `setup.bat` 自动装（默认源失败自动换清华/npmmirror 镜像）

## 常见问题

| 症状 | 处理 |
|---|---|
| 双击 setup.bat 提示没有 Python | 按上面装好 Python（勾 PATH）再双击一次 |
| 某平台抓取全失败 | 控制台「设置」页「平台登录」：点「去登录」用任意手机号(如闲置号)登录一次 —— 该登录态是浏览凭据, 与账号管理无关; 失败截图在 `logs/screenshots/` |
| 不知道某平台登录态还有效吗 | 「平台登录」面板点「检测」，绿=已登录 / 红=已失效 / 黄=无法判断 |
| 腾讯文档报 Token 失效/未授权 | `python main.py tdoc-auth` 扫码一次 |
| 想改每天的抓取时间 | 控制台「设置」页改，保存立即生效 |
| 想加账号 | 控制台「账号管理」页表单添加，立即生效 |
| 抓取弹了浏览器窗口 | 设置页开「静默(无头)」；个别平台反爬严需关静默手动登录一次 |

### 腾讯文档授权说明（每台新机器都需要，一次即可）

- **谁需要授权**：每台运行本工具的机器都要用自己的 QQ/微信扫一次
  （setup.bat 第 4 步会引导，或手动 `python main.py tdoc-auth`）。
- **权限要求**：扫码的那个账号必须对目标表格有**编辑权限**——
  团队共用同一张表时，先把表格分享给该账号（可编辑）。
- **有效期**：Token 长期有效；若写入报 400006 过期，重新扫一次即可。
- **写自己的表**：控制台「设置」页改 file_id（自己建表后复制
  链接里 `/sheet/` 后面那段），表头复制上面 7 列即可（列名对上就自动适配）。

## 支持平台与路线

| 平台 | 标识 | 路线 | 粉丝 | 内容数 | 阅读/播放 | 登录态 |
|---|---|---|---|---|---|---|
| 富途 | `futu` | Playwright 主页(统计板) | ✓ | - | ✓来访 | **需登录**(已复用 auto-publisher 登录态) |
| 雪球 | `xueqiu` | Playwright 主页 | ✓ | ✓帖子 | - | 匿名可抓 |
| 长桥 | `changqiao` | Playwright 主页 | ✓ | - | - | 匿名可抓 |
| 东方财富 | `eastmoney` | Playwright i 主页 | ✓ | - | - | 匿名可抓 |
| 老虎 | `laohu` | Playwright 主页 | ✓ | - | - | 匿名可抓 |
| 同花顺 | `ths` | Playwright 主页 | ✓ | - | - | 匿名可抓 |
| 微博 | `weibo` | Playwright 主页 | ✓ | - | - | 匿名可抓(登录更全) |
| 微博 | `weibo` | Playwright 主页 | ✓ | - | - | 匿名可抓 |
| 知乎 | `zhihu` | Playwright 主页 | ✓ | ✓文章 | - | **需登录**(风控严) |
| B站 | `bilibili` | relation/stat API + 空间页 | ✓(API精确) | ✓投稿(999+封顶) | - | 匿名可抓 |
| 小红书 | `xhs` | Playwright 主页 | ✓ | ✓笔记 | - | 建议登录 |
| 抖音 | `douyin` | Playwright 主页 | ✓ | ✓作品 | - | 建议登录 |
| 快手 | `kuaishou` | Playwright 主页 | ✓ | - | - | 匿名可抓 |
| X | `x` | FxTwitter 公开 API | ✓ | ✓推文数 | - | 无需 |
| YouTube | `youtube` | Google Data API v3 | ✓订阅 | ✓视频数 | ✓累计播放 | API Key |
| 公众号 | `weixin_gzh` | 预留(需公众号后台) | - | - | - | 未开通 |
| 视频号 | `weixin_sph` | 预留(需视频号助手后台) | - | - | - | 未开通 |

说明：某平台公开页没有的指标在表格里填 `-`，不会编数。
抖音/快手/老虎/同花顺/小红书 的选择器基于通用规则预置，**拿到同事的真实
主页链接后**先跑一次 `python main.py probe <链接> --spec <平台>` 确认提取
候选，不对就调 `fetchers/browser_page.py` 里对应平台的 SPEC 正则（每平台
一段注释好的配置）。

## 使用

```bash
pip install -r requirements.txt
python main.py setup        # 一键初始化: 依赖→浏览器内核→计划任务→桌面快捷方式
python main.py web          # 打开控制台(图表/账号管理/设置/手动抓取)
python main.py status       # 配置/账号/历史/腾讯文档连通性一览
python main.py crawl        # 抓全部账号 → 本地历史 → 写腾讯文档
python main.py sync         # 只重写今天的腾讯文档 sheet(可反复执行)
python main.py daily        # 计划任务入口(幂等: 今天做过就跳过)
python main.py login xueqiu    # 需登录平台扫码一次(profiles/ 持久化)
python main.py probe <URL> --spec futu   # 调试: 看页面提取候选
python seed_history.py      # 一次性导入 auto-publisher 历史(可选)
```

## 新用户下载上手(3 步)

1. **下载解压 → 双击 `setup.bat`**（自动装依赖、浏览器内核、注册
   每天 9:00 计划任务、引导腾讯文档扫码授权、创建桌面快捷方式）
2. 双击桌面快捷方式打开**控制台网页**：
   - 「账号管理」页添加账号（账号所有人-所属平台-账号名称-主页链接，
     或 X/YouTube 的 @handle）——立即生效，无需改代码
     （首次会自动从 `accounts.example.yaml` 生成清单文件）
   - 「设置」页粘贴 YouTube API Key、改定时时间（保存即重注册计划任务）、
     开关静默(无头)浏览、改要写入的腾讯文档 file_id
3. 需登录的平台（富途必须，小红书/抖音建议）在命令行执行
   `python main.py login futu` 扫码一次，长期有效
   （账号管理页会按你已配的账号提示要执行哪些命令）

腾讯文档写入用的是纯 HTTP 接口（无浏览器、无界面、静默）；
每日抓取默认无头后台运行，**不弹任何窗口**。
新用户第一次用控制台「设置」页会提示未授权，
执行 `python main.py tdoc-auth` 扫码一次即可（Token 存本地，不进仓库）。

## 自动化

- 计划任务 `fans-tracker-daily`（默认每天 09:00，**时间在控制台
  「设置」页改，保存立即生效**）+ `fans-tracker-catchup`（每次登录补跑，
  电脑 9 点关机也不漏；幂等，当天做过即跳过）
- 也可以让 Agent/脚本直接调 `python main.py daily --force` 触发
- 也可在控制台仪表盘点「立即抓取」手动跑一次

## 添加账号（同事发来主页链接后）

控制台「账号管理」页表单操作即可（推荐）：**添加 / 编辑 / 删除**，
点某账号的「编辑」会把它的值回填到顶部表单，改完「保存修改」立即生效
（可以改所有人、名称、链接，甚至换平台）。也可以编辑
`config/accounts.yaml`（首次从 `accounts.example.yaml` 复制），照注释加一段：

```yaml
  - platform: douyin          # 平台标识(见上表)
    owner: 张三               # 账号所有人(表格第一列)
    name: ""                  # 账号名称(留空自动抓昵称)
    url: https://www.douyin.com/user/xxx   # 主页链接
  - platform: x
    owner: 李四
    handle: elonmusk          # X/YouTube 填 @后面的字符串, 不用 url
```

## YouTube API Key

1. 打开 https://console.cloud.google.com/ → 新建项目(任意名)
2. 「API 和服务」→「启用 API」→ 搜 **YouTube Data API v3** → 启用
3. 「凭据」→「创建凭据」→「API 密钥」→ 复制
4. 填入本项目 `.env` 文件: `YOUTUBE_API_KEY=xxxx`
   (免费额度每日 1 万次, 每天几十个频道绰绰有余)

未配置 key 时 YouTube 账号自动跳过并在表格标错，不影响其他平台。

## 登录态

- **CDP 接管**：若本机 Chrome 开着调试口 9222（auto-publisher 的
  `chrome_debug.bat`），自动接管复用其全部登录态。
- **独立 profile**：否则逐平台用 `profiles/<平台>/` 登录态窗口。
  futu 已从 auto-publisher 复制；其他平台需要时：
  `python main.py login <平台>` 扫码一次，长期有效。
- 腾讯文档 Token 自动读取（mcporter 配置 / secret.local.json），
  过期(400006)时用 tencent-docs skill 重新授权一次即可。

## 自动化（已注册）

| 计划任务 | 触发 | 作用 |
|---|---|---|
| `fans-tracker-daily` | 每天 09:00 | 抓取+写表 |
| `fans-tracker-catchup` | 每次登录 | 9 点没开机时补跑(幂等, 做过即跳过) |

日志: `logs/daily.log`；失败截图: `logs/screenshots/`。

## 目录结构

```
main.py            CLI 入口
config/accounts.yaml  账号清单(随时加)
config/settings.yaml  浏览器/文档/抓取参数
fetchers/          x_fxtwitter / youtube_api / bilibili_api / browser_page(通用SPEC)
browser.py         CDP优先 + 独立profile 双模式
history.py         data/history.json 逐日快照(原子写)
metrics.py         增粉计算(环比/上周口径保留为内部工具)
tdoc.py            腾讯文档 sheet-mcp 直连写入
login.py           扫码登录
seed_history.py    历史播种(auto-publisher → 本项目)
run_daily.bat      计划任务入口
```

## 指标口径

- **累计粉丝**：当日抓取时的粉丝总量
- **内容数**：**前一天发布的内容条数**（feed 按日期筛选）
- **阅读/播放量**：**前一天发布内容的浏览量合计**（富途/东方财富）；
  **YouTube 特例 = 最新一条视频的播放量**（用户确认的口径）
- 雪球/长桥/知乎/微博：平台不公开内容浏览量 → 内容数照抓、浏览填 `-`
- X：无公开时间线接口 → 内容数/浏览均 `-`（FxTwitter 只能解析单条）
- B站：作品卡不带发布日期 → 暂 `-`（需登录态+API 再开）
- 解析不到内容日期（未登录/页面没渲染）时填 `-`，不会把"没抓到"伪装成 0
- 增粉 = 今日累计粉丝 − 上一条历史记录（新账号当天建基线, 次日起有值）
- 上周增粉/环比上周：现版表格已删这两列, metrics.py 保留计算能力备用
- 历史不足（新账号前两周）相应列填 `-`

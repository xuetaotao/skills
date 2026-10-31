# 网页图片下载

把一个网页（图集、文章、帖子）里的**正文图片**批量下载到本地，可选**自动翻页**。自动识别懒加载和原图链接，跳过图标、头像、推荐区和广告，内容相同的图片只存一份，文件按页面顺序编号 `001.jpg、002.png…`。

PyQt5 桌面小程序，也可以走命令行。

## 快速开始

```bat
scripts\start_gui.bat
```

启动脚本使用项目下的 `.venv`。还没有这个目录时，用 PATH 上的 `python` 创建它并安装 `requirements.txt`，之后一直用这个环境。已有 `.venv` 但缺少依赖时，脚本会提示安装命令：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS / Linux 用 `scripts/start_gui.sh`。图形界面会记住上次的输出目录和各项选项，下载完成后点「打开保存位置」直接打开文件夹。

## 功能

| 环节 | 做法 |
|------|------|
| 找图 | `<img>` 的懒加载属性（`data-src`、`data-original` 等）优先于 `src`；有 `srcset` 时取最大的一张；缩略图外面包着指向图片文件的链接（`<a href="xxx.jpg"><img></a>`）时下载原图 |
| 过滤 | 图片自身 class/id 像图标（icon、logo、avatar、emoji 等）的跳过；位于侧边栏、推荐、评论、页眉页脚、广告区域里的跳过，但正文容器（article-content、post-body 等）里的不受影响；可按大小跳过小图 |
| 翻页 | 识别「下一页」、页码链接、`?page=N` 和 `/N` 路径分页；某一页没有新图片、或翻页跳回已下载过的页面时停止；可限制最多页数 |
| 下载 | 连接复用、失败自动重试（不理会 Cloudflare 要求的 60 秒等待）；带来源页作为 Referer；按文件头判断真实格式，伪装成 `.jpg` 的 webp 存成 `.webp`，防盗链返回的网页不会被存成图片 |
| 命名 | 下载时先用临时名，全部结束后按页面顺序重新编号，失败、过小、重复的图片不占号 |
| 取消 | 图形界面点「取消」或命令行按 Ctrl+C，已下载的图片保留并照常编号 |

保存位置形如 `outputs/example.com-网页标题-20261025_153000/001.jpg`，同一秒内重复下载会自动加 `_2` 后缀。

## 命令行

```bash
python -m backend "https://example.com/post/123"                                      # 单页
python -m backend "https://example.com/gallery/1" --auto-pagination -m 20 --min-size 30  # 翻页，最多 20 页，跳过 30KB 以下
python -m frontend                                                                     # 图形界面（同 start_gui.bat）
python scripts/probes/probe_pages.py [网址 ...]                                         # 只解析第一页，不下载
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o/--output` | 输出根目录，每次下载在里面新建一个子目录 | 项目下的 `outputs/` |
| `-j/--num-threads` | 并发下载数 | 8 |
| `-t/--timeout` | 单个请求超时（秒） | 15 |
| `--auto-pagination` | 自动翻页（图形界面默认开启） | 关 |
| `-m/--max-pages` | 最多下载多少页 | 不限 |
| `--min-size` | 跳过小于该大小（KB）的图片 | 0（不过滤） |
| `--keep-duplicates` | 保留内容重复的图片 | 关（去重） |
| `--keep-names` | 文件名带上原文件名，如 `001_photo.jpg` | 关 |

默认并发数、超时、重试次数和图标 / 排除区域 / 正文容器关键词都在 `backend/config.py`。

## 站点验证记录

测试站点清单放在项目根目录的 `test_sites.md`（已 gitignore，只保存在本地），`probe_pages.py` 不带参数时逐个探测里面的网址。

2026-10-25：分页图集站 4 页 40 张全部下载成功，图片地址是 `.jpg`、实际内容是 webp，按真实格式保存；另一个路径分页的图集站访问返回 Cloudflare 502，未能验证。本地测试页覆盖了 GBK 编码、懒加载、srcset、原图链接、防盗链、重复图片、翻页越界重定向和取消。

## 踩过的坑

1. **扩展名不可信**：不少图床把 webp 放在 `.jpg` 地址下，按地址后缀命名会得到打不开的文件，所以按文件头判断。
2. **翻页越界会跳回第一页**：路径分页（`/N`）的站点请求不存在的页码时重定向回第 1 页，不检测就会无限循环，所以记录访问过的最终地址。
3. **Retry-After 太长**：Cloudflare 502 会要求等 60 秒，按标准重试 3 次就是 3 分钟，所以忽略这个头，按指数退避重试。
4. **关键词误判**：直接用子串匹配时 `ad` 会命中 `thread`、`header` 会命中 `subheader-title`，所以关键词只在 class/id 的词首或 `-`、`_` 之后匹配。
5. **网页编码**：不声明 charset 的 GBK 网页按 UTF-8 解析会乱码，标题和目录名都会受影响，所以把原始字节交给 BeautifulSoup 自己识别。

## 项目结构

```
downloader/image/
├── backend/
│   ├── config.py      # 默认参数、User-Agent、懒加载属性、图标 / 排除区域 / 正文容器关键词
│   ├── core.py        # 取网页、提取图片、翻页、并发下载、去重、按页面顺序编号
│   └── cli.py         # 命令行（python -m backend）
├── frontend/
│   └── gui.py         # PyQt5 图形界面（python -m frontend），后台线程复用 core
├── scripts/
│   ├── start_gui.bat / start_gui.sh
│   └── probes/        # 网页探测（只解析不下载）
├── outputs/           # 下载的图片（已 gitignore）
└── requirements.txt
```

## 局限

- 只看网页源码：完全靠接口异步加载、或要点击 / 滚动后由脚本插入的图片拿不到。
- 原图只认 `<a>` 直接指向图片文件的情况；点击后弹出大图查看器、地址藏在脚本里的网站只能拿到缩略图。
- 需要登录才能看的页面暂不支持传 Cookie。
- 过滤靠 class/id 关键词，个别网站的正文图片可能被误判跳过，或推荐区图片混进来；可以用 `--min-size` 辅助。

## 免责声明

本工具仅供学习研究使用，请遵守相关法律法规和网站的使用条款。

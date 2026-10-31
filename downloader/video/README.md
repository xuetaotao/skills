# 音视频下载

从视频网站下载**视频或音频**。通用站点（YouTube、Bilibili、X 等上千个网站）交给 [yt-dlp](https://github.com/yt-dlp/yt-dlp)；**抖音**（无水印）、**MacCMS 影视站**、**RouVideo** 用内置的专用解析器；m3u8 由自己的下载器处理，支持 AES-128 加密和断点续传。

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

macOS / Linux 用 `scripts/start_gui.sh`。建议另外安装：

- **[ffmpeg](https://ffmpeg.org/download.html)**（放进 PATH）：合并分开的视频流和音频流、转 mp3 等格式、嵌入封面、字幕转 srt、m3u8 转 mp4 都要用到。没有 ffmpeg 时自动改下「最佳单文件」，m3u8 保存为 `.ts`。
- **JavaScript 运行时**：Deno、Node.js、Bun 任选一个，YouTube 解算播放地址要用，没有的话部分画质会缺失。本机装了 Node.js 就够了。

图形界面会记住上次的选项；「查看信息」只解析不下载；下载完成后点「打开保存位置」直接打开文件夹。

## 功能

| 来源 | 做法 |
|------|------|
| 通用站点 | yt-dlp 一次解析并下载；画质可选最高 / 4K / 1080p / 720p / 480p / 360p / 最佳单文件，合并为 mp4、mkv 或 webm；默认下载中英文字幕（含自动字幕），可保存封面；默认只下播放列表的第一个 |
| 仅音频 | 保留原始格式，或转成 mp3、m4a、flac、wav、aac、opus，可嵌入封面 |
| 抖音 | 分享短链逐跳解析；视频无水印；图集逐张下载；「仅音频」在作品没有原声音乐地址时用 ffmpeg 从视频里提取音轨；作品被删除时显示抖音给出的提示 |
| MacCMS 影视站 | 识别播放页和详情页（详情页跳到第一集），解析 `player_aaaa` 并解密 encrypt 0/1/2；yt-dlp 不认识的网址也会检查页面内容是不是 MacCMS |
| RouVideo | 从页面数据里解密播放地址，剥掉 CDN 给 m3u8 和分片套的 PNG 外壳 |
| m3u8 | 主播放列表选最高码率；AES-128（IV 来自属性或分片序号）、fMP4 初始化分片；多线程下载、失败重试，任一分片缺失就报错而不是拼出残缺视频；分片缓存在输出目录的 `.hls_cache`，中途失败或取消后重新下载会接着下；专用解析器在自有下载器失败时依次退回 yt-dlp、ffmpeg |

文件名保留标题里的中文，只替换 Windows 不允许的字符。图形界面点「取消」或命令行按 Ctrl+C 会立刻停止。代理支持 HTTP / SOCKS5；Cookie 文件可以是浏览器导出的 `cookies.txt`，也可以是内容为 `a=1; b=2` 的文本文件。

保存位置形如 `outputs/bilibili.com-标题前20字-20261025_153000/标题.mp4`，抖音、MacCMS、RouVideo 的目录分别以 `douyin-`、`maccms-`、`rouvideo-` 开头。

## 命令行

```bash
python -m backend video "https://www.bilibili.com/video/BVxxx"                    # 最高画质
python -m backend video "https://www.youtube.com/watch?v=xxx" -q 720 --subtitle   # 不超过 720p，带字幕
python -m backend audio "https://www.youtube.com/watch?v=xxx" --audio-format mp3  # 转成 mp3
python -m backend info  "https://x.com/i/status/xxx"                              # 只看信息和可用格式
python -m backend douyin "https://v.douyin.com/xxx/" --mode audio                 # 抖音仅音频（video 子命令也会自动识别抖音）
python -m frontend                                                                # 图形界面（同 start_gui.bat）
python scripts/probes/probe_sites.py [网址 ...]                                    # 逐个站点只解析不下载
```

下载类子命令（video / audio / douyin）共用：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o/--output` | 输出根目录，每次下载在里面新建一个子目录 | 项目下的 `outputs/` |
| `-t/--timeout` | 网络超时（秒） | 30 |
| `--threads` | m3u8 分片并发数 | 8 |
| `--proxy` | 代理，如 `socks5://127.0.0.1:1080` | 无 |
| `--cookie-file` | Cookie 文件（`cookies.txt` 或 `a=1; b=2` 文本） | 无 |

| 子命令 | 参数 |
|------|------|
| `video` | `-q/--quality` best / 2160 / 1080 / 720 / 480 / 360 / single（默认 best）；`-f/--format` 自定义 yt-dlp 格式，优先于 `-q`；`--merge-output-format` mp4 / mkv / webm；`--subtitle`；`--sub-langs`（默认 `zh.*,en.*`，`all` 为全部）；`--thumbnail`；`--playlist` |
| `audio` | `--audio-format` best / mp3 / m4a / flac / wav / aac / opus（默认 best）；`--audio-quality` 0（最好）到 9；`--embed-thumbnail`；`--playlist` |
| `info` | 只有 `--proxy`、`--cookie-file` |
| `douyin` | `--mode` video / audio / info |

画质映射、音频格式、字幕语言、超时、并发数、分片重试次数和 JavaScript 运行时都在 `backend/config.py`。

## 站点验证记录

完整的测试网址和每个站点的细节见 [test_sites.md](test_sites.md)，`probe_sites.py` 不带参数时逐个探测里面的网址。

2026-10-25（yt-dlp 2026.10.21）：Bilibili、YouTube 实际下载成功（YouTube 360p 视频 + 音频合并为 8.7 MB 的 mp4）；X 解析出 8 种格式；抖音无水印视频 78.5 MB，作品没有原声音乐地址时从视频提取出 313 秒 aac 音轨；两个 MacCMS 站（encrypt 0 和 2）解析成功，抽查分片都是合法 TS；RouVideo 改版后重新适配，181 个分片约 9 MB/s，取消后可续传。本地测试覆盖了明文 / AES（两种 IV）/ fMP4 / 主播放列表、缺分片报错与续传、取消、MacCMS 三种入口、PNG 外壳和中文文件名。

## 踩过的坑

1. **yt-dlp 要跟着升级**：Bilibili 旧版本会报 HTTP 412，YouTube 新版本需要 JavaScript 运行时加 `yt-dlp-ejs` 组件（`requirements.txt` 用 `yt-dlp[default]` 带上），遇到某个站突然不行先执行 `.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"`。
2. **抖音要先“暖场”**：直接请求分享页拿不到 `videoInfoRes`，要先访问一次 `https://www.iesdouyin.com/` 拿到 `__ac_nonce`、`ttwid` Cookie。2026 年起不少作品不再返回原声音乐地址，「仅音频」只能从视频里提取。
3. **MacCMS 的 Referer 必须带末尾斜杠**：`https://kanav.ad/` 可以，`https://kanav.ad` 会被 CDN 拒绝。
4. **RouVideo 2026-10 改版**：页面从 Next.js 换成 TanStack Start，数据不在 `__NEXT_DATA__` 里了，而是 seroval 序列化的 `$R[n]={video:{...},ev:{d,k}}`；`ev` 解密不变（base64 解码 → 每字节减 k → JSON），得到相对地址 `/api/hls/{id}`，跳到 CDN 的 `index.png`，m3u8 和每个分片都藏在 PNG 的自定义块 `roUd` 里（首字节 bit0=1 表示其余内容经 zlib 压缩）。yt-dlp 和 ffmpeg 都处理不了这种外壳。
5. **重定向后的相对地址**：m3u8 里的分片地址要相对于重定向后的最终地址拼接，否则会拼到原站域名上。
6. **yt-dlp 的输出模板**：中文标题要开 `windowsfilenames` 而不是 `restrictfilenames`，否则全部变成下划线；`%(title).80s` 截断长标题，避免 Windows 路径超长。

## 项目结构

```
downloader/video/
├── backend/
│   ├── config.py      # 默认参数、User-Agent、画质与音频格式映射、字幕语言、JavaScript 运行时
│   ├── core.py        # 总调度：按网址选解析器，通用站点调用 yt-dlp（选项、进度、取消、错误提示）
│   ├── common.py      # 网络会话、Cookie、文件名、进度节流、取消、直链断点续传、站点下载器基类
│   ├── hls.py         # m3u8 下载器（主列表、AES-128、并发重试、续传、转封装）及 yt-dlp / ffmpeg 兜底
│   ├── douyin.py      # 抖音
│   ├── maccms.py      # MacCMS 影视站
│   ├── rouvideo.py    # RouVideo
│   └── cli.py         # 命令行（python -m backend）
├── frontend/
│   └── gui.py         # PyQt5 图形界面（python -m frontend），后台线程复用 core
├── scripts/
│   ├── start_gui.bat / start_gui.sh
│   └── probes/        # 站点探测（只解析不下载）
├── outputs/           # 下载的文件和 m3u8 分片缓存（已 gitignore）
├── test_sites.md      # 测试网址与各站点细节
└── requirements.txt
```

## 局限

- 专用解析器依赖网站页面结构，网站改版就会失效（RouVideo 2026-10 就改过一次），需要跟着修；通用站点则取决于 yt-dlp 的更新。
- 抖音只支持单个作品，用户主页无法批量下载；部分短剧等受限作品外部访问会 404。
- m3u8 不支持 SAMPLE-AES、DRM 和 BYTERANGE 分片。
- MacCMS 只取第一个播放源的指定一集，不会整部剧批量下载。
- 需要登录的内容只能靠手动导出的 Cookie 文件，Cookie 过期要重新导出。

## 免责声明

本工具仅供学习研究使用，请遵守相关法律法规和网站的使用条款。

# 音视频下载工具

从视频网站下载视频或音频的工具，基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，支持 GUI 和 CLI 两种使用方式。

## 功能特性

- **视频下载**：支持 YouTube、Bilibili 等上千个视频网站
- **音频提取**：从视频中提取音频，支持 mp3/flac/wav/m4a/aac/opus 等格式
- **画质选择**：支持最高画质/1080p/720p/480p/360p 等
- **字幕下载**：支持自动字幕和手动字幕下载
- **缩略图下载**：下载视频缩略图
- **播放列表**：支持整个播放列表下载
- **GUI 界面**：基于 PyQt5 的图形界面
- **CLI 命令行**：支持命令行直接运行，方便脚本化调用
- **代理支持**：支持 HTTP/SOCKS5 代理
- **Cookie 支持**：支持 Cookie 文件，用于需要登录的网站

## 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

> **注意**：如需下载最高画质视频（bestvideo+bestaudio）或转换音频格式，还需要安装 [ffmpeg](https://ffmpeg.org/download.html) 并确保其在系统 PATH 中。

## 使用方法

### 一键运行（GUI）

```bash
# macOS/Linux
./run.sh

# Windows
.\run_windows.ps1
```

### 命令行使用

```bash
# 下载视频（最高画质）
python -m src video "https://www.youtube.com/watch?v=xxx" -o ./output

# 下载视频（指定画质）
python -m src video "https://www.bilibili.com/video/BVxxx" -o ./output -f "bestvideo[height<=720]+bestaudio"

# 下载视频并带字幕和缩略图
python -m src video "https://www.youtube.com/watch?v=xxx" -o ./output --subtitle --thumbnail

# 下载音频（mp3 格式）
python -m src audio "https://www.youtube.com/watch?v=xxx" -o ./output --audio-format mp3

# 下载音频（最佳质量 flac）
python -m src audio "https://www.youtube.com/watch?v=xxx" -o ./output --audio-format flac --audio-quality 0

# 查看视频信息（不下载）
python -m src info "https://www.youtube.com/watch?v=xxx"

# 启动 GUI
python -m src gui

# 查看帮助
python -m src --help
python -m src video --help
python -m src audio --help
```

### 参数说明

#### 视频下载 (video)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 视频地址 | (必填) |
| `-o/--output` | 输出目录 | ./output |
| `-f/--format` | 视频格式 (yt-dlp 格式字符串) | bestvideo+bestaudio/best |
| `--merge-output-format` | 合并输出格式 | mp4 |
| `--subtitle` | 下载字幕 | False |
| `--thumbnail` | 下载缩略图 | False |
| `--playlist` | 下载整个播放列表 | False |
| `--proxy` | 代理地址 | None |
| `--cookie-file` | Cookie 文件路径 | None |
| `-t/--timeout` | 超时时间(秒) | 30 |

#### 音频下载 (audio)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 音视频地址 | (必填) |
| `-o/--output` | 输出目录 | ./output |
| `--audio-format` | 音频格式: best/mp3/wav/flac/aac/m4a/opus | best |
| `--audio-quality` | 音频质量 0(最好)-9(最差) | 0 |
| `--embed-thumbnail` | 嵌入缩略图到音频文件 | False |
| `--playlist` | 下载整个播放列表 | False |
| `--proxy` | 代理地址 | None |
| `--cookie-file` | Cookie 文件路径 | None |
| `-t/--timeout` | 超时时间(秒) | 30 |

#### 信息查看 (info)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 视频/音频地址 | (必填) |
| `--proxy` | 代理地址 | None |
| `--cookie-file` | Cookie 文件路径 | None |

## 支持的网站

yt-dlp 支持上千个视频网站，包括但不限于：

- YouTube
- Bilibili
- Twitter/X
- Reddit
- Vimeo
- Dailymotion
- Niconico
- Facebook
- Instagram
- TikTok
- 以及更多...

完整列表请参考 [yt-dlp 支持网站](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 项目结构

```
videodownloader/
├── src/
│   ├── __init__.py              # 包初始化
│   ├── __main__.py              # python -m src 入口
│   ├── main.py                  # CLI 主入口
│   ├── launcher.py              # GUI 启动入口
│   └── media_downloader/        # 音视频下载器
│       ├── __init__.py
│       ├── core.py              # 核心下载逻辑 (基于 yt-dlp)
│       ├── gui.py               # GUI 对话框
│       └── gui_main.py          # GUI 入口
├── output/                      # 默认输出目录
├── requirements.txt
├── run.sh
├── run_windows.ps1
└── README.md
```

## 常见问题

### 下载最高画质失败？

下载最高画质（bestvideo+bestaudio）需要 ffmpeg 来合并音视频流。请安装 ffmpeg 并确保其在系统 PATH 中。

### 如何下载需要登录的视频？

使用 `--cookie-file` 参数指定浏览器的 Cookie 文件。可以使用浏览器扩展（如 Get cookies.txt LOCALLY）导出 Cookie。

### 如何使用代理？

使用 `--proxy` 参数，例如：
```bash
python -m src video "https://www.youtube.com/watch?v=xxx" --proxy "socks5://127.0.0.1:1080"
```

## 免责声明

本工具仅供学习研究使用，请遵守相关法律法规和网站的使用条款。

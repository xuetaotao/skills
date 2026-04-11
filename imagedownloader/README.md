# 图片下载工具集

基于搜索引擎和网页抓取的图片批量下载工具，支持 GUI 和 CLI 两种使用方式。

## 功能特性

- **搜索引擎图片下载**：支持 Google、Bing、百度，支持 Selenium 和 API 两种爬取模式
- **网页图片批量下载**：从任意网页批量下载图片，支持懒加载图片、自动翻页
- **GUI 界面**：基于 PyQt5 的图形界面，通过统一启动器选择工具
- **CLI 命令行**：支持命令行直接运行，方便脚本化调用
- **多线程下载**：支持自定义并发线程数，高效下载
- **代理支持**：支持 HTTP 和 Socks5 代理

## 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

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
# 搜索引擎下载图片
python -m src search "关键词" -e Bing -d api -n 100 -o ./output

# 网页批量下载图片
python -m src webpage "https://example.com" -o ./output -j 4

# 启动统一启动器 GUI
python -m src gui

# 启动指定工具 GUI
python -m src gui --tool search    # 搜索引擎下载器
python -m src gui --tool webpage   # 网页下载器

# 查看帮助
python -m src --help
python -m src search --help
python -m src webpage --help
```

### 搜索引擎参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-e/--engine` | 搜索引擎 (Google/Bing/Baidu) | Google |
| `-d/--driver` | 驱动模式 (chrome_headless/chrome/api) | chrome_headless |
| `-n/--max-number` | 最大下载数量 | 100 |
| `-j/--num-threads` | 并发线程数 | 50 |
| `-t/--timeout` | 超时时间(秒) | 10 |
| `-o/--output` | 输出目录 | ./download_images |
| `-S/--safe-mode` | 安全模式(仅Google) | False |
| `-F/--face-only` | 仅人脸图片 | False |
| `-ph/--proxy_http` | HTTP代理 | None |
| `-ps/--proxy_socks5` | Socks5代理 | None |

### 网页下载参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o/--output` | 输出目录 | ./webpage_images |
| `-j/--num-threads` | 并发线程数 | 4 |
| `-t/--timeout` | 超时时间(秒) | 10 |
| `--keep-names` | 保留原文件名 | False(递增编号) |
| `--auto-pagination` | 自动翻页 | False |
| `-m/--max-pages` | 最大页数 | None(无限制) |

## 项目结构

```
imagedownloader/
├── src/
│   ├── __init__.py              # 包初始化
│   ├── __main__.py              # python -m src 入口
│   ├── main.py                  # CLI 统一主入口
│   ├── launcher.py              # GUI 统一启动器
│   ├── search_downloader/       # 搜索引擎图片下载器
│   │   ├── __init__.py
│   │   ├── crawler.py           # 搜索引擎爬虫
│   │   ├── downloader.py        # 多线程下载
│   │   ├── utils.py             # 配置和工具函数
│   │   ├── logger.py            # 日志系统
│   │   ├── image_downloader_cli.py  # CLI 入口
│   │   ├── gui.py               # GUI 入口
│   │   ├── mainwindow.py        # 主窗口逻辑
│   │   ├── mainwindow.ui        # Qt Designer 文件
│   │   ├── about.ui             # 关于对话框 UI
│   │   ├── ui_mainwindow.py     # 自动生成的 UI 代码
│   │   └── ui_about.py          # 自动生成的 UI 代码
│   └── webpage_downloader/      # 网页图片下载器
│       ├── __init__.py
│       ├── core.py              # 核心下载逻辑
│       ├── gui.py               # GUI 对话框
│       └── gui_main.py          # GUI 入口
├── output/                      # 默认输出目录
│   ├── search/                  # 搜索引擎下载输出
│   └── webpage/                 # 网页下载输出
├── requirements.txt
├── run.sh
├── run_windows.ps1
└── README.md
```

## 致谢

本项目基于 [Image-Downloader](https://github.com/sczhengyabin/Google-Image-Downloader) 开发。

## 免责声明

本工具仅供学习研究使用，请遵守相关法律法规和网站的使用条款。

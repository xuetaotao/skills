# 网页图片下载工具

从指定网页批量下载所有图片的工具，支持 GUI 和 CLI 两种使用方式。

## 功能特性

- **网页图片批量下载**：从任意网页批量下载图片，支持懒加载图片、自动翻页
- **GUI 界面**：基于 PyQt5 的图形界面
- **CLI 命令行**：支持命令行直接运行，方便脚本化调用
- **多线程下载**：支持自定义并发线程数，高效下载

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
# 网页批量下载图片
python -m src webpage "https://example.com" -o ./output/webpage -j 4

# 启动 GUI
python -m src gui

# 查看帮助
python -m src --help
python -m src webpage --help
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 网页地址 | (必填) |
| `-o/--output` | 输出根目录（自动创建子目录） | ./output |
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
│   ├── main.py                  # CLI 主入口
│   ├── launcher.py              # GUI 启动入口
│   └── webpage_downloader/      # 网页图片下载器
│       ├── __init__.py
│       ├── core.py              # 核心下载逻辑
│       ├── gui.py               # GUI 对话框
│       └── gui_main.py          # GUI 入口
├── output/                      # 默认输出目录
├── requirements.txt
├── run.sh
├── run_windows.ps1
└── README.md
```

## 免责声明

本工具仅供学习研究使用，请遵守相关法律法规和网站的使用条款。

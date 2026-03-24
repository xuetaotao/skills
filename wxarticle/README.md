# 微信公众号文章下载器

将微信公众号文章保存为 PDF 和截图的命令行工具。

## 功能特性

- 给定微信公众号文章链接，生成 PDF 和截图
- 自动处理页面滚动，加载懒加载图片
- 支持自定义输出目录

## 安装

```bash
cd wxarticle

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

## 使用方法

### 一键运行（推荐）

```bash
./run.sh "https://mp.weixin.qq.com/s/xxxxx"
```

首次运行会自动创建虚拟环境并安装依赖。

### 手动运行

```bash
cd wxarticle

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 运行
python -m src "https://mp.weixin.qq.com/s/xxxxx"

# 其他选项
python -m src "https://mp.weixin.qq.com/s/xxxxx" -o ./my_output  # 指定输出目录
python -m src "https://mp.weixin.qq.com/s/xxxxx" --pdf-only      # 只生成 PDF
python -m src "https://mp.weixin.qq.com/s/xxxxx" --screenshot-only  # 只生成截图
```

## 目录结构

```
wxarticle/
├── README.md           # 说明文档
├── requirements.txt    # 依赖
├── run.sh              # 一键运行脚本
├── output/             # 输出目录
└── src/
    ├── __init__.py
    ├── __main__.py     # 模块入口
    ├── main.py         # 命令行入口
    ├── fetcher.py      # 文章抓取
    └── generator.py    # PDF/截图生成
```

## 待实现功能

- [ ] 通过公众号名称自动获取最新文章并下载
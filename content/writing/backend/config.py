"""路径、写作阶段、文章状态。"""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_DIR / "prompts"
ARTICLES_DIR = Path(os.environ.get("WRITING_ARTICLES_DIR") or PROJECT_DIR / "articles")  # 草稿和定稿，不进 Git
TRASH_DIR = ARTICLES_DIR / "_trash"
FRONTEND_DIR = PROJECT_DIR / "frontend"
WORKFLOW_MD = PROJECT_DIR / "WorkFlow.md"
# 标题评分借用公众号工作空间的爆款预测器和基准数据；不存在时这个功能自动隐藏
WXPUB_DIR = Path(os.environ.get("WXPUB_DIR") or PROJECT_DIR.parent / "wxpubaccount").resolve()

PORT = 8331

# 写作阶段 → Prompt 文件。needs 决定网页上要填哪些输入
STAGES = [
    {"key": "expand", "file": "观点拓展Prompt.md", "name": "观点拓展", "step": "第一轮",
     "when": "想法还松散、不确定主线时：先不写正文，拓展观点、提炼概念、建议主线", "needs": ["topic", "ideas"]},
    {"key": "draft", "file": "网页端轻量初稿Prompt.md", "name": "轻量初稿", "step": "第二轮",
     "when": "想法比较清楚：直接写一版初稿，自然吸收必要拓展（最常用）", "needs": ["topic", "ideas"]},
    {"key": "quick", "file": "极简初稿Prompt.md", "name": "极简初稿", "step": "第二轮",
     "when": "想快速看到一版稿子，不想输入太多规则", "needs": ["topic", "ideas"]},
    {"key": "revise", "file": "修改反馈Prompt.md", "name": "修改反馈", "step": "第二轮",
     "when": "初稿出来后提修改意见：保留 / 删除 / 加强 / 弱化", "needs": ["feedback", "article"]},
    {"key": "check", "file": "质量检查Prompt.md", "name": "质量检查", "step": "第三轮",
     "when": "基本满意后：反方审稿、事实风险扫描、去 AI 腔", "needs": ["article"]},
]
STAGE = {s["key"]: s for s in STAGES}

STATUSES = ["构思", "初稿", "修改中", "定稿", "已发表"]
FINAL_STATUSES = {"定稿", "已发表"}  # 进入这两个状态时把当前版本另存为 final.md
SOURCES = ["我写的", "AI 初稿", "AI 修改", "质量检查后"]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

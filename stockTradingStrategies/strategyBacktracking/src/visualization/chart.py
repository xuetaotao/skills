"""
可视化模块
生成收益曲线、回撤图、月度收益热力图
"""
import os
import logging
from typing import Optional

import matplotlib
matplotlib.use('Agg')  # 非交互模式
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

# 中文字体设置
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


def plot_all(nav_history: list, benchmark_nav: dict, metrics: dict,
             output_dir: str, strategy_name: str = "") -> list:
    """
    生成所有图表
    返回: 生成的图片路径列表
    """
    from src.analytics.report import get_file_prefix
    file_prefix = get_file_prefix(output_dir)

    images = []

    try:
        # 1. 收益曲线 + 回撤图（上下组合）
        img1 = plot_equity_with_drawdown(
            nav_history, benchmark_nav, output_dir, strategy_name, file_prefix)
        images.append(img1)
    except Exception as e:
        logger.warning(f"生成收益曲线图失败: {e}")

    try:
        # 2. 月度收益热力图
        img2 = plot_monthly_heatmap(nav_history, output_dir, strategy_name, file_prefix)
        images.append(img2)
    except Exception as e:
        logger.warning(f"生成月度热力图失败: {e}")

    return images


def plot_equity_with_drawdown(nav_history: list, benchmark_nav: dict,
                               output_dir: str, strategy_name: str = "",
                               file_prefix: str = "") -> str:
    """收益曲线 + 回撤图"""
    if not nav_history:
        return ""

    dates = [pd.Timestamp(h["date"]) for h in nav_history]
    navs = [h["nav"] for h in nav_history]

    fig = plt.figure(figsize=(14, 10))
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 0.3], hspace=0.1)

    # ── 收益曲线 ──
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(dates, navs, linewidth=1.8, label=strategy_name or "策略", color='#2196F3')

    # 基准曲线
    colors = ['#FF9800', '#4CAF50', '#9C27B0', '#F44336', '#00BCD4']
    for i, (bm_name, bm_data) in enumerate(benchmark_nav.items()):
        bm_dates = [pd.Timestamp(d["date"]) for d in bm_data]
        bm_navs = [d["nav"] for d in bm_data]
        ax1.plot(bm_dates, bm_navs, linewidth=1.2, alpha=0.8,
                 label=bm_name, color=colors[i % len(colors)], linestyle='--')

    ax1.set_ylabel("净值", fontsize=12)
    ax1.set_title(f"策略回测: {strategy_name}", fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax1.tick_params(labelbottom=False)

    # 填充策略净值区域
    ax1.fill_between(dates, 1.0, navs, alpha=0.1, color='#2196F3')

    # ── 回撤图 ──
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    # 计算回撤序列
    nav_arr = np.array(navs)
    peak = np.maximum.accumulate(nav_arr)
    drawdown = (nav_arr - peak) / peak

    ax2.fill_between(dates, drawdown, 0, alpha=0.4, color='#F44336')
    ax2.plot(dates, drawdown, linewidth=0.8, color='#F44336')
    ax2.set_ylabel("回撤", fontsize=12)
    ax2.set_xlabel("日期", fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    # ── 指标摘要 ──
    ax3 = fig.add_subplot(gs[2])
    ax3.axis('off')
    summary_text = (
        f"年化收益: {metrics.get('annual_return_pct', 'N/A')}  |  "
        f"最大回撤: {metrics.get('max_drawdown_pct', 'N/A')}  |  "
        f"夏普比率: {metrics.get('sharpe_ratio', 'N/A')}  |  "
        f"胜率: {metrics.get('win_rate_pct', 'N/A')}  |  "
        f"盈亏比: {metrics.get('profit_loss_ratio', 'N/A')}"
    )
    ax3.text(0.5, 0.5, summary_text, ha='center', va='center', fontsize=11,
             transform=ax3.transAxes,
             bbox=dict(boxstyle='round,pad=0.5', facecolor='#F5F5F5', alpha=0.8))

    plt.tight_layout()

    filepath = os.path.join(output_dir, f"{file_prefix}_equity_curve.png" if file_prefix else "equity_curve.png")
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)

    logger.info(f"收益曲线图已保存: {filepath}")
    return filepath


def plot_monthly_heatmap(nav_history: list, output_dir: str,
                         strategy_name: str = "",
                         file_prefix: str = "") -> str:
    """月度收益热力图"""
    if not nav_history:
        return ""

    # 构建月度收益率
    df = pd.DataFrame(nav_history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')

    # 计算月度收益率
    monthly = df['nav'].resample('M').last()
    monthly_return = monthly.pct_change().dropna()

    if len(monthly_return) == 0:
        return ""

    # 构建年月矩阵
    data = {}
    for date, ret in monthly_return.items():
        year = date.year
        month = date.month
        if year not in data:
            data[year] = {}
        data[year][month] = ret

    years = sorted(data.keys())
    months = range(1, 13)

    # 构建矩阵
    matrix = np.full((len(years), 12), np.nan)
    for i, year in enumerate(years):
        for j, month in enumerate(months):
            if month in data.get(year, {}):
                matrix[i][j] = data[year][month]

    fig, ax = plt.subplots(figsize=(12, max(3, len(years) * 0.8 + 1.5)))

    # 绘制热力图
    masked = np.ma.masked_invalid(matrix)
    cmap = plt.cm.RdYlGn
    cmap.set_bad(color='white')

    vmax = max(abs(np.nanmin(matrix)), abs(np.nanmax(matrix)), 0.05)
    im = ax.imshow(masked, cmap=cmap, aspect='auto', vmin=-vmax, vmax=vmax)

    # 标注数值
    for i in range(len(years)):
        for j in range(12):
            val = matrix[i][j]
            if not np.isnan(val):
                color = 'white' if abs(val) > vmax * 0.5 else 'black'
                ax.text(j, i, f"{val:.1%}", ha='center', va='center',
                        fontsize=8, color=color)

    ax.set_xticks(range(12))
    ax.set_xticklabels([f"{m}月" for m in range(1, 13)])
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years)
    ax.set_title(f"月度收益热力图: {strategy_name}", fontsize=14, fontweight='bold')

    plt.colorbar(im, ax=ax, label='月度收益率', shrink=0.8)

    plt.tight_layout()
    filepath = os.path.join(output_dir, f"{file_prefix}_monthly_heatmap.png" if file_prefix else "monthly_heatmap.png")
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)

    logger.info(f"月度收益热力图已保存: {filepath}")
    return filepath

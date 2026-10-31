"""解析后台页面的无障碍树快照（data/raw/*.txt）。

快照是一行一个节点的缩进文本，例如：
    - StaticText "阅读"
    - generic
      - StaticText "289 人"
    - image "推荐, 96.53."
旧数据由 agent-browser 生成，新数据由 scraper.py 按同样格式生成。这里不依赖缩进和中间夹的
generic 节点，只把它拍平成 (角色, 文字) 序列再按「标签 → 后面第一个符合格式的值」取数，
这样页面多包一层 div 或快照工具换了也不影响解析。也兼容 Playwright aria_snapshot 的
`- text: 阅读` 写法。
"""

import re
from typing import List, Optional, Tuple

_LINE = re.compile(r'^\s*-\s+([A-Za-z]+)(?:\s+"((?:[^"\\]|\\.)*)")?(?::\s*(.*))?')
_ROLE_ALIAS = {"text": "StaticText", "img": "image"}

Token = Tuple[str, str]


def tokens(text: str) -> List[Token]:
    out = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        role = _ROLE_ALIAS.get(m.group(1), m.group(1))
        name = m.group(2)
        if name is None:
            name = (m.group(3) or "").strip().strip('"')
        else:
            name = name.replace('\\"', '"')
        out.append((role, name))
    return out


def _named(toks: List[Token]) -> List[Token]:
    """去掉没有文字的结构节点（generic、list、空格等），以及只是重复父节点名字的 StaticText
    （CDP 会在 cell / heading 下再挂一个同名文字节点，agent-browser 的快照里没有）。"""
    out = []
    for r, n in toks:
        if not n.strip():
            continue
        if r == "StaticText" and out and out[-1][0] != "StaticText" and out[-1][1].strip() == n.strip():
            continue
        out.append((r, n))
    return out


def _is_label(name: str, label: str, exact: bool) -> bool:
    name = name.strip()
    return name == label if exact else name.endswith(label)


def value_after(named: List[Token], label: str, pattern: str, exact: bool = False, role: str = None) -> Optional[str]:
    """第一个「标签后紧跟的值符合 pattern」的位置，返回 pattern 的第 1 组。"""
    rx = re.compile(pattern)
    for i, (r, n) in enumerate(named[:-1]):
        if (role is None or r == role) and _is_label(n, label, exact):
            m = rx.match(named[i + 1][1].strip())
            if m:
                return m.group(1)
    return None


def _int(s):
    return int(s.replace(",", "")) if s is not None else None


def chart_points(named: List[Token]) -> List[Tuple[str, str, str]]:
    """Highcharts 数据点：image "推荐, 96.53." / image "送达人数, 30. 首次传播." -> (名称, 数值, 系列)"""
    out = []
    for r, n in named:
        if r != "image":
            continue
        m = re.match(r'^([^,]+?),\s*([\d.]+)\.\s*(.*)$', n)
        if m:
            out.append((m.group(1).strip(), m.group(2), m.group(3).strip().rstrip(".")))
    return out


# ---------------- 单篇详情页 d2_<appmsg_id>.txt ----------------

def parse_detail(text: str) -> dict:
    named = _named(tokens(text))
    names = [n for _, n in named]
    out = {}

    v = value_after(named, "阅读", r"^([\d,]+) 人$", exact=True)
    if v:
        out["reads_d2"] = _int(v)
    v = value_after(named, "完读率", r"^(\d+(?:\.\d+)?)%$")
    if v:
        out["completion"] = float(v)
    v = value_after(named, "新增关注", r"^([\d,]+) 人$")
    if v:
        out["new_follows"] = _int(v)

    # 互动区块：「分享」到「赞赏」之间的三个数字依次是 分享总数 / 朋友圈分享 / 转发（好友、群）
    start = next((i for i, n in enumerate(names) if n.strip().endswith("分享")), None)
    if start is not None:
        end = next((j for j in range(start + 1, len(names)) if names[j].strip() == "赞赏"), None)
        if end is not None:
            nums = [_int(n.strip()) for n in names[start + 1:end] if re.match(r"^[\d,]+$", n.strip())]
            for key, val in zip(("shares", "moments", "forwards"), nums):
                out[key] = val

    for label, key in (("留言", "comments"), ("收藏", "collections"), ("赞赏", "appreciation")):
        v = value_after(named, label, r"^([\d,]+)$")
        if v:
            out[key] = _int(v)
    v = value_after(named, "听全文", r"^(\d+) 人$")
    if v:
        out["listen_full"] = int(v)

    points = chart_points(named)
    # 订阅漏斗 / 分享扩散只取「首次传播」系列
    for name, key in (("送达人数", "reach"), ("消息阅读人数", "msg_reads"), ("首次分享人数", "first_share_n"),
                      ("总分享人数", "total_share_n"), ("分享产生的阅读人数", "share_induced_reads")):
        hit = next((val for nm, val, series in points if nm == name and series.startswith("首次传播")), None)
        if hit is not None and re.match(r"^\d+$", hit):
            out[key] = int(hit)

    # 流量来源图里混着「送达人数」等其它指标，只留真正的渠道
    from .config import AGE_ORDER, TRAFFIC_SOURCES
    channels = {nm: float(val) for nm, val, _ in points if nm in TRAFFIC_SOURCES}
    if channels:
        out["channels"] = channels

    gender = {}
    for n in names:
        for k, val in re.findall(r'(男|女|未知)\s+(\d+(?:\.\d+)?)%', n):
            gender[k] = float(val)
    if gender:
        out["gender"] = gender

    age = {}
    for label in AGE_ORDER:
        hit = next((val for nm, val, _ in points if nm == label), None)
        if hit is not None:
            age[label] = float(hit)
    if age:
        out["age"] = age

    region = []
    cells = [n.strip() for r, n in named if r in ("cell", "gridcell")]
    for name, val in zip(cells, cells[1:]):
        m = re.match(r"^([\d.]+)%$", val)
        if m and not name.endswith("%"):
            region.append([name, m.group(1) + "%"])
    if region:
        out["region"] = region
    return out


# ---------------- 用户分析页 user_analysis.txt ----------------

def parse_user_analysis(text: str) -> dict:
    """累计关注、月增长率、新增关注渠道饼图。"""
    named = _named(tokens(text))
    names = [n for _, n in named]
    out = {"fans": None, "growth_month_pct": None, "channels": {}, "channels_total": None, "is_single_slice": False}

    v = value_after(named, "累计关注人数", r"^([\d,]+)$")
    if v:
        out["fans"] = _int(v)
    start = next((i for i, n in enumerate(names) if n.endswith("累计关注人数")), None)
    if start is not None:
        for j in range(start + 1, len(names) - 1):
            if names[j] == "月":
                m = re.match(r"^([\d.]+)%$", names[j + 1])
                if m:
                    out["growth_month_pct"] = float(m.group(1))
                break

    seg_start = next((i for i, n in enumerate(names) if "渠道构成" in n), 0)
    seg = named[seg_start:]
    for i, (_, n) in enumerate(seg):
        m = re.search(r"Pie chart with (\d+) slice", n)
        if m:
            out["is_single_slice"] = int(m.group(1)) == 1
            if i + 1 < len(seg):
                t = re.match(r"^(\d+)人$", seg[i + 1][1].strip())
                if t:
                    out["channels_total"] = int(t.group(1))
            break
    # 单片饼图时数值是人数，多片时是百分比，由使用方区分
    for nm, val, _ in chart_points(seg):
        if "关注" in nm:
            out["channels"][nm] = float(val)
    return out


# ---------------- 内容分析页 content_analysis.txt ----------------

def parse_content_analysis(text: str) -> dict:
    """账号级流量来源占比 + 阅读总人数。"""
    named = _named(tokens(text))
    traffic = {nm: float(val) for nm, val, _ in chart_points(named)}
    total = None
    for _, n in named:
        m = re.search(r"阅读总人数：([\d,]+)人", n)
        if m:
            total = _int(m.group(1))
            break
    return {"traffic": traffic, "total_readers": total}

# -*- coding: utf-8 -*-
"""同行业分组：按申万行业确定一只股票和谁比。

申万一级不超过 PEER_MAX_L1 家时整个一级行业一起比（如银行 42 家，再按二级分成国有大行、股份行、城商行、农商行）；
否则用二级（如白酒），二级仍太大时用三级。最终最多保留市值前 PEER_MAX 家，自选股本身一定保留。
"""
from .config import PEER_MAX, PEER_MAX_L1


def _members(cls, prefix):
    return [c for c, s in cls.items() if s.startswith(prefix)]


def peer_group(code, cls, names):
    """返回 dict(key, level, name, path, members, sub)；不在申万分类里的股票返回 None。

    sub: {成员代码: 下一级行业名}，用于在组内再分组；三级行业没有下一级时为 {}。
    """
    sw3 = cls.get(code)
    if not sw3 or len(sw3) != 6:
        return None
    l1, l2 = sw3[:2], sw3[:4]
    m = _members(cls, l1)
    if len(m) <= PEER_MAX_L1:
        level, key, sub_len = 1, l1, 4
    else:
        m = _members(cls, l2)
        if len(m) <= PEER_MAX:
            level, key, sub_len = 2, l2, 6
        else:
            m, level, key, sub_len = _members(cls, sw3), 3, sw3, None
    return dict(key=key, level=level, name=names.get(key, key),
                path=[names.get(k, k) for k in (l1, l2, sw3)[:level]], members=m,
                sub={c: names.get(cls[c][:sub_len], cls[c][:sub_len]) for c in m} if sub_len else {})


def cap_members(group, mcap, keep):
    """剔除没有当日估值的成员（退市、长期停牌），按市值保留前 PEER_MAX 家，keep 中的代码一定保留。"""
    alive = [c for c in group["members"] if c in mcap or c in keep]
    alive.sort(key=lambda c: -(mcap.get(c) or 0))
    top = alive[:PEER_MAX]
    top += [c for c in keep if c in group["members"] and c not in top]
    group = dict(group, members=top, total=len(alive))
    group["sub"] = {c: group["sub"][c] for c in top if c in group["sub"]}
    return group

"""解析 data/raw 下现有快照并打印结果（不联网、不写文件），用来核对解析规则。

    python scripts/probes/probe_snapshots.py             # 全部
    python scripts/probes/probe_snapshots.py 2247484125  # 只看某篇详情
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend import dataset, snapshot  # noqa: E402
from backend.config import RAW_DIR  # noqa: E402

only = set(sys.argv[1:])
cards = dataset.all_articles()
print(f"发表记录：{len(dataset.publish_pages())} 页，{len(cards)} 篇有发文时间"
      + (f"（{cards[0]['publish']} ~ {cards[-1]['publish']}）" if cards else ""))
print("用户分析：", json.dumps(dataset.load_user_analysis(), ensure_ascii=False))
ca = dataset.load_content_analysis()
print("内容分析：阅读总人数", ca["total_readers"], "流量来源", json.dumps(ca["traffic"], ensure_ascii=False))
for aid, path in sorted(dataset.detail_files().items()):
    if only and aid not in only:
        continue
    d = snapshot.parse_detail(path.read_text(encoding="utf-8"))
    keys = ("reads_d2", "completion", "new_follows", "shares", "comments", "collections")
    print(f"d2_{aid}: " + " ".join(f"{k}={d.get(k)}" for k in keys)
          + f" 渠道{len(d.get('channels', {}))} 年龄{len(d.get('age', {}))} 地域{len(d.get('region', []))}")
if not RAW_DIR.exists():
    print("data/raw 不存在：先运行 python -m backend scrape")

#!/usr/bin/env bash
# 翻页抓取微信公众平台「发表记录」，直到某页返回空数组为止。
# 产出 data/raw/publish_pN.txt（N 从 1 递增），build_articles.py 会合并全部页面。
# 用法： bash scripts/scrape_publish.sh <TOKEN> [WORKSPACE_DIR]
#   TOKEN 来自登录后 URL 里的 token= 参数。
# 注意：本机若设了 HTTP(S)_PROXY 会导致 Chromium ERR_NO_SUPPORTED_PROXIES，故先 unset。
unset HTTP_PROXY HTTPS_PROXY

TOKEN="${1:?用法: bash scripts/scrape_publish.sh <TOKEN> [WORKSPACE_DIR]}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# scripts -> wxpub-analysis -> skills -> .workbuddy -> wxpubaccount
WS="${2:-$(cd "$SCRIPT_DIR/../../../.." && pwd -W)}"
RAW="$WS/data/raw"
mkdir -p "$RAW"
# Python 解释器：优先系统 python3/python（可移植），回退到本机托管路径
PY="$(command -v python3 || command -v python || echo "C:/Users/xuetaotao/.workbuddy/binaries/python/versions/3.13.12/python.exe")"

URL="https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=%d&count=20&token=$TOKEN&lang=zh_CN"
EXTRACT="$SCRIPT_DIR/extract_pub.js"

count_cards () {
  # $1 = file ; 输出卡片数 (失败/空 = 0)
  "$PY" - "$1" <<'PY' 2> /dev/null
import json, sys, traceback
try:
    r = open(sys.argv[1], encoding="utf-8").read().strip()
    sys.stderr.write("DBG first20=%r len=%d\n" % (r[:20], len(r)))
    if not r:
        print(0); sys.exit(0)
    d = json.loads(r)
    if isinstance(d, list):
        if d and isinstance(d[0], str):
            d = json.loads(d[0])   # 双编码：外层数组包裹一个 JSON 字符串
    elif isinstance(d, str):
        d = json.loads(d)
    print(len(d) if isinstance(d, list) else 0)
except Exception:
    sys.stderr.write("DBG ERR: " + traceback.format_exc() + "\n")
    print(0)
PY
}

P=0
i=1
MAX_PAGES=200   # 安全上限（=4000 篇）；正常靠"空页即停"，命中上限说明可能漏抓，会显式告警
while [ "$i" -le "$MAX_PAGES" ]; do
  agent-browser open "$(printf "$URL" "$P")" >/dev/null 2>&1
  agent-browser wait 5000 >/dev/null 2>&1
  # 抓两次：首次若空（SPA 未渲染）再等 3s 重试一次
  agent-browser eval "$(cat "$EXTRACT")" > "$RAW/publish_p$i.txt" 2>&1
  n=$(count_cards "$RAW/publish_p$i.txt")
  if [ "$n" -eq 0 ]; then
    agent-browser wait 3000 >/dev/null 2>&1
    agent-browser eval "$(cat "$EXTRACT")" > "$RAW/publish_p$i.txt" 2>&1
    n=$(count_cards "$RAW/publish_p$i.txt")
  fi
  echo "page $i (begin=$P): $n cards  [$(head -c 80 "$RAW/publish_p$i.txt" | tr -d '\n')...]"
  if [ "$n" -eq 0 ]; then
    echo "空页 -> 停止翻页（已抓全量）"
    rm -f "$RAW/publish_p$i.txt"
    break
  fi
  P=$((P + 20))
  i=$((i + 1))
done
if [ "$i" -gt "$MAX_PAGES" ]; then
  echo "⚠️ 警告：已达到 MAX_PAGES=$MAX_PAGES 上限仍未遇到空页，数据可能不完整！请检查分页逻辑。"
fi
echo "完成：共抓到 $((i - 1)) 页发表记录 -> $RAW/publish_p*.txt"
rm -f "$RAW/_dbg_count.txt" 2>/dev/null   # 清理可能的调试残留

#!/bin/bash
# 923 batch: warm douyin login from cookie export, then run 8 themes sequentially.
export PATH="/usr/bin:/bin:$PATH"
export CODEBUDDY_SAFE_DELETE_ENABLED=0
ROOT="/d/刘宇钊/codex_work/haike-workflow/copy_skill/copy_skill-main"
cd "$ROOT" || exit 1
MC_PY="$ROOT/third_party/MediaCrawler/.venv/Scripts/python.exe"

echo "=== [1/2] warm login from cookie export ==="
"$MC_PY" scripts/warm_login_from_cookies.py "../../www.douyin.com_cookies.txt"
WARM_RC=$?
echo "=== warm exit code: $WARM_RC ==="
if [ $WARM_RC -ne 0 ]; then
  echo "WARMUP_FAILED - aborting batch"
  exit 1
fi

echo "=== [2/2] run 8 themes ==="
THEMES=("阿里真武V900" "高通2nm" "内存涨价" "Mac发售" "Grok4.7" "小米开源登顶" "机器人进乐园" "启元机器人")
i=0
for t in "${THEMES[@]}"; do
  i=$((i+1))
  echo "=== THEME $i/8: $t ==="
  uv run douyin-intelligence material-replication run --theme "$t" --pool-size 80 --business-date "2026-09-23"
  rc=$?
  echo "=== THEME $i ($t) exit code: $rc ==="
done
echo "=== ALL THEMES DONE ==="

#!/bin/bash
set -euo pipefail
HAIKE_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HAIKE_ROOT/deployment-cache/OFFLINE.json" ]; then
  bash "$HAIKE_ROOT/scripts/setup-mac.sh" --offline
else
  bash "$HAIKE_ROOT/scripts/setup-mac.sh"
fi
echo "安装完成。请运行 02-启动Mac.command。"

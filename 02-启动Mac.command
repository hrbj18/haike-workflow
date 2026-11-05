#!/bin/bash
set -euo pipefail
HAIKE_ROOT="$(cd "$(dirname "$0")" && pwd)"
HAIKE_ARCH="$(uname -m)"
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then HAIKE_ARCH=arm64; fi
HAIKE_PY="$HAIKE_ROOT/runtime/macos/$HAIKE_ARCH/python/bin/python3.12"
if [ ! -x "$HAIKE_PY" ]; then echo "请先运行 01-安装Mac.command。" >&2; exit 1; fi
exec "$HAIKE_PY" -s "$HAIKE_ROOT/scripts/mac-deploy.py" start

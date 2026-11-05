#!/bin/bash
set -euo pipefail
HAIKE_ROOT="$(cd "$(dirname "$0")" && pwd)"
HAIKE_ARCH="$(uname -m)"
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then HAIKE_ARCH=arm64; fi
exec "$HAIKE_ROOT/runtime/macos/$HAIKE_ARCH/python/bin/python3.12" -s "$HAIKE_ROOT/scripts/mac-deploy.py" check

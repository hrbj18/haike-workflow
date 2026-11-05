#!/bin/bash
# Native, user-local bootstrap. No Homebrew, sudo, Xcode or system Python needed.
set -euo pipefail
HAIKE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(uname -s)" != Darwin ]; then
  echo "此入口仅用于 macOS；Windows 请运行 01-setup.cmd。" >&2
  exit 1
fi
HAIKE_ARCH="$(uname -m)"
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then HAIKE_ARCH=arm64; fi
case "$HAIKE_ARCH" in
  arm64) HAIKE_PY_ARCH=aarch64; HAIKE_PY_SHA=d6e607f109db29f2e4a00137fde91f29f359709e1815887334305e4f560b19ac ;;
  x86_64) HAIKE_PY_ARCH=x86_64; HAIKE_PY_SHA=2dbebc822dea55d60db64f93f532aa72aea4b5ccb400a1cee4f8b4a489a10ce5 ;;
  *) echo "不支持的 Mac 架构：$HAIKE_ARCH" >&2; exit 1 ;;
esac
HAIKE_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
if [ "$HAIKE_MAJOR" -lt 14 ]; then echo "本部署方案需要 macOS 14 或更新版本。" >&2; exit 1; fi
HAIKE_PY_NAME="cpython-3.12.8+20241206-${HAIKE_PY_ARCH}-apple-darwin-install_only_stripped.tar.gz"
HAIKE_PY_DIR="$HAIKE_ROOT/runtime/macos/$HAIKE_ARCH"
HAIKE_PY="$HAIKE_PY_DIR/python/bin/python3.12"
HAIKE_ARCHIVE="$HAIKE_ROOT/deployment-cache/runtime/$HAIKE_PY_NAME"
HAIKE_OFFLINE=0
for HAIKE_ARG in "$@"; do if [ "$HAIKE_ARG" = --offline ]; then HAIKE_OFFLINE=1; fi; done
if [ ! -x "$HAIKE_PY" ]; then
  mkdir -p "$HAIKE_ROOT/deployment-cache/runtime" "$HAIKE_PY_DIR"
  if [ ! -f "$HAIKE_ARCHIVE" ]; then
    if [ "$HAIKE_OFFLINE" = 1 ]; then echo "离线 Python 缺失，请完整解压部署包。" >&2; exit 1; fi
    HAIKE_PY_URL="https://registry.npmmirror.com/-/binary/python-build-standalone/20241206/$HAIKE_PY_NAME"
    if [ "${HAIKE_RUNTIME_DOWNLOAD_ORIGIN:-0}" = 1 ]; then
      HAIKE_PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241206/$HAIKE_PY_NAME"
    fi
    curl --fail --location --retry 3 --connect-timeout 20 --proto '=https' --tlsv1.2 \
      "$HAIKE_PY_URL" \
      -o "$HAIKE_ARCHIVE.part"
    mv "$HAIKE_ARCHIVE.part" "$HAIKE_ARCHIVE"
  fi
  HAIKE_ACTUAL="$(shasum -a 256 "$HAIKE_ARCHIVE" | cut -d' ' -f1)"
  if [ "$HAIKE_ACTUAL" != "$HAIKE_PY_SHA" ]; then echo "Python 归档校验失败，已保留文件。" >&2; exit 1; fi
  tar -xzf "$HAIKE_ARCHIVE" -C "$HAIKE_PY_DIR"
fi
exec "$HAIKE_PY" -s "$HAIKE_ROOT/scripts/mac-deploy.py" install "$@"

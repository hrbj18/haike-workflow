#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
for tool in python3 node npm ffmpeg ffprobe; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "缺少 $tool。请安装 Python 3.12、Node.js 22 和 FFmpeg 后重试。"
    echo "已安装 Homebrew 时可执行：brew install python@3.12 node@22 ffmpeg"
    exit 1
  fi
done
python3 tools/kit.py verify
npm ci --no-audit --no-fund
npx remotion browser ensure
python3 tools/kit.py doctor
echo "安装完成。运行 python3 tools/kit.py list 查看可复刻实例。"

#!/bin/zsh
set -eu
TASK_ROOT="${0:A:h}"
cd "$TASK_ROOT/api-platform"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  print "请先安装 uv（https://docs.astral.sh/uv/）。"
  read '?按回车退出'
  exit 1
fi
uv sync --frozen
uv run --frozen python launch.py

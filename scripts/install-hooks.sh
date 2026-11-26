#!/usr/bin/env bash
# 一次性安装：让 git 使用仓库内的 .githooks。
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x .githooks/pre-commit .githooks/pre-push scripts/pre-commit.sh
if [ "$(git config --get core.hooksPath || true)" = ".githooks" ]; then
  exit 0
fi
git config core.hooksPath .githooks
echo "已启用 .githooks（pre-commit 跑格式/风格/类型）"

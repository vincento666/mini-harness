#!/usr/bin/env bash
# 建一个 change 的骨架：分支、目录、契约、任务（含固定收尾四项）。
# 用法：scripts/new-change.sh <change-id> [capability]
set -euo pipefail
cd "$(dirname "$0")/.."

id="${1:?用法: scripts/new-change.sh <change-id> [capability]}"
capability="${2:-core}"
dir="openspec/changes/$id"

if [ -e "$dir" ]; then
  echo "已存在：$dir" >&2
  exit 1
fi

git checkout -b "change/$id"
mkdir -p "$dir/specs/$capability"
printf 'schema: spec-driven\ncreated: %s\n' "$(date +%F)" > "$dir/.openspec.yaml"

cp docs/verification/verification-contract-template.md "$dir/verification-contract.md"

cat > "$dir/tasks.md" <<EOF
# Tasks

## 1. 实现

- [ ] 1.1 写第一条判据（断言日志或外部行为）
- [ ] 1.2 实现到判据变绿

## 2. 收尾

- [ ] 2.1 真实端点验收
- [ ] 2.2 UAT 验收（人跑；场次手册 \`docs/verification/$id-uat.md\`）
- [ ] 2.3 变异测试一轮（记录 \`docs/verification/$id-mutation.md\`）
- [ ] 2.4 Learning Gate
EOF

echo "已建 $dir（分支 change/$id）。下一步：写契约与 specs/$capability/spec.md。"

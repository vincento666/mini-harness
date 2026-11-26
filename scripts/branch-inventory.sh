#!/usr/bin/env bash
# branch-inventory.sh — 只读盘点：未合并分支 + 未归档 change（2026-11-26 人裁，A+B 两个检查点共用）
# 用途：接手/propose/apply 前跑一次做提醒；归档/合入 main 前必跑，输出交人逐条确认后才合。
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "=== 未合并远程分支（相对 main：领先/落后 · 末次提交） ==="
unmerged=$(git branch -r --no-merged main 2>/dev/null | sed 's/^ *//' || true)
if [ -z "$unmerged" ]; then
    echo "（无）"
else
    printf "%-42s %6s %6s  %s\n" "分支" "领先" "落后" "末次提交"
    for b in $unmerged; do
        ahead=$(git rev-list --count "main..${b}" 2>/dev/null || echo "?")
        behind=$(git rev-list --count "${b}..main" 2>/dev/null || echo "?")
        last=$(git log -1 --format='%ci' "${b}" 2>/dev/null | cut -c1-10 || echo "?")
        printf "%-42s %6s %6s  %s\n" "$b" "$ahead" "$behind" "$last"
    done
fi

echo
echo "=== 未归档 change（勾选率） ==="
changes=$(find openspec/changes -maxdepth 1 -mindepth 1 -type d ! -name archive 2>/dev/null || true)
if [ -z "$changes" ]; then
    echo "（无）"
else
    for d in $changes; do
        name=$(basename "$d")
        tasks="$d/tasks.md"
        if [ -f "$tasks" ]; then
            done_n=$(grep -c '^- \[x\]' "$tasks" || true)
            todo_n=$(grep -c '^- \[ \]' "$tasks" || true)
            printf "%-42s %3d/%d 完成\n" "$name" "$done_n" "$((done_n + todo_n))"
        else
            printf "%-42s （无 tasks.md）\n" "$name"
        fi
    done
fi

echo
echo "（处置建议：合并 / 放弃 / 保留理由——合入 main 前逐条经人确认）"

#!/usr/bin/env bash
# 流水线纯函数测试。不访问 GitHub，不调用编码 agent。
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../lib/agent-pipeline-common.sh
source "$ROOT/scripts/lib/agent-pipeline-common.sh"

FAIL=0

assert_eq() {
  local name="$1" got="$2" want="$3"
  if [[ "$got" != "$want" ]]; then
    printf 'FAIL %s\n  got  [%s]\n  want [%s]\n' "$name" "$got" "$want" >&2
    FAIL=1
  else
    printf 'ok %s\n' "$name"
  fi
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/issue.md" <<'EOF'
## Goal

<!-- placeholder -->

把健康检查写进 README。

## Acceptance

- 读者能看到检查命令

## Only-edit

python_scripts/service.py
docs/**

## 其他

不要改这里。
EOF

if missing=$(agent_pipeline_py missing-sections "$TMP/issue.md"); then
  assert_eq "完整 Issue 通过小节检查" "$missing" ""
else
  printf 'FAIL 完整 Issue 被拒绝: %s\n' "$missing" >&2
  FAIL=1
fi

cat > "$TMP/empty.md" <<'EOF'
## Goal

<!-- 只有注释 -->

## Acceptance

## Notes

有别的标题也不算数。
EOF
if missing=$(agent_pipeline_py missing-sections "$TMP/empty.md"); then
  printf 'FAIL 空 Issue 不应通过\n' >&2
  FAIL=1
else
  assert_eq "空小节被点名" "$missing" "$(printf 'Goal\nAcceptance\nOnly-edit')"
fi

agent_pipeline_py extract "$TMP/issue.md" "Goal" > "$TMP/goal.txt"
if grep -q "把健康检查写进 README" "$TMP/goal.txt" && ! grep -q "读者能看到" "$TMP/goal.txt"; then
  printf 'ok 抽取 Goal\n'
else
  printf 'FAIL 抽取 Goal\n' >&2
  FAIL=1
fi

agent_pipeline_py extract "$TMP/issue.md" "Only-edit" > "$TMP/only.txt"
printf '%s\n' "python_scripts/service.py" "docs/agent-pipeline.md" "README.md" > "$TMP/files.txt"
only_out=$(agent_pipeline_py only-edit "$TMP/only.txt" "$TMP/files.txt")
only_status=$(printf '%s\n' "$only_out" | head -n 1)
only_bad=$(printf '%s\n' "$only_out" | tail -n +2)
assert_eq "Only-edit 越界状态" "$only_status" "fail"
assert_eq "Only-edit 越界文件" "$only_bad" "README.md"

printf '%s\n' "没有路径，只有一段说明。" > "$TMP/prose.txt"
printf '%s\n' "README.md" > "$TMP/one-file.txt"
prose_out=$(agent_pipeline_py only-edit "$TMP/prose.txt" "$TMP/one-file.txt")
assert_eq "散文 Only-edit 交给审查者" "$(printf '%s\n' "$prose_out" | head -n 1)" "skip"

cat > "$TMP/verdict.txt" <<'EOF'
先看一眼。
VERDICT: FIX
NOTES: 补上测试
第二行仍算说明
EOF
assert_eq "解析 FIX" "$(agent_pipeline_py verdict "$TMP/verdict.txt")" "FIX"
assert_eq "解析 NOTES" "$(agent_pipeline_py notes "$TMP/verdict.txt")" "$(printf '补上测试\n第二行仍算说明')"

cat > "$TMP/prs.json" <<'EOF'
[
  {"number": 4, "title": "pipeline", "body": "Fixes #9\n\n<!-- agent-pipeline:issue=9 -->\n"},
  {"number": 5, "title": "human", "body": "This closes #9 now."},
  {"number": 6, "title": "other", "body": "Fixes #8"}
]
EOF
assert_eq "区分流水线 PR 和人工 PR" \
  "$(agent_pipeline_py match-prs "$TMP/prs.json" 9)" \
  "$(printf 'pipeline\t4\nhuman\t5')"

printf '%s\n' '[{"bucket":"pass"},{"bucket":"skipping"}]' > "$TMP/checks-pass.json"
printf '%s\n' '[{"bucket":"pending"},{"bucket":"pass"}]' > "$TMP/checks-pending.json"
printf '%s\n' '[{"bucket":"fail"}]' > "$TMP/checks-fail.json"
printf '%s\n' '[]' > "$TMP/checks-none.json"
assert_eq "checks pass" "$(agent_pipeline_py classify-checks "$TMP/checks-pass.json")" "pass"
assert_eq "checks pending" "$(agent_pipeline_py classify-checks "$TMP/checks-pending.json")" "pending"
assert_eq "checks fail" "$(agent_pipeline_py classify-checks "$TMP/checks-fail.json")" "fail"
assert_eq "checks none" "$(agent_pipeline_py classify-checks "$TMP/checks-none.json")" "none"

assert_eq "新 Issue 去实现" "$(agent_pipeline_issue_action "" "" "sha" "" none)" "implement"
assert_eq "已有流水线 PR 则认领" "$(agent_pipeline_issue_action "" "" "sha" "" pipeline)" "adopt"
assert_eq "已有人工 PR 则停下" "$(agent_pipeline_issue_action "" "" "sha" "" human)" "block_human"
assert_eq "需要修复" "$(agent_pipeline_issue_action needs_fix "" "sha" "sha" pipeline)" "fix"
assert_eq "打开的 PR 不再次实现" "$(agent_pipeline_issue_action pr_open "" "sha" "sha" pipeline)" "skip"
assert_eq "REJECT 后不重试" "$(agent_pipeline_issue_action rejected "" "sha" "sha" none)" "skip"
assert_eq "正文没变的 malformed 不重试" "$(agent_pipeline_issue_action stopped malformed "sha" "sha" none)" "skip"
assert_eq "正文变了的 malformed 再看一次" "$(agent_pipeline_issue_action stopped malformed "new" "old" none)" "implement"
assert_eq "其他停止原因不因正文变化重开" "$(agent_pipeline_issue_action stopped tests_failed "new" "old" none)" "skip"

assert_eq "活进程算进行中" "$(agent_pipeline_inflight implementing 1)" "busy"
assert_eq "死进程算崩溃" "$(agent_pipeline_inflight reviewing 0)" "crashed"
assert_eq "普通状态不算进行中" "$(agent_pipeline_inflight pr_open 0)" "free"

assert_eq "第一轮 FIX 放行" "$(agent_pipeline_apply_verdict FIX 0 2)" "fix"
assert_eq "第二轮 FIX 放行" "$(agent_pipeline_apply_verdict FIX 1 2)" "fix"
assert_eq "第三轮 FIX 变成 REJECT" "$(agent_pipeline_apply_verdict FIX 2 2)" "reject_exhausted"
assert_eq "ACCEPT 保持" "$(agent_pipeline_apply_verdict ACCEPT 2 2)" "accept"
assert_eq "乱写的裁决无效" "$(agent_pipeline_apply_verdict MAYBE 0 2)" "invalid"

assert_eq "新 PR 要审查" "$(agent_pipeline_review_action pr_open abc "" 0 3)" "review"
assert_eq "同一 SHA 不重复审查" "$(agent_pipeline_review_action pr_open abc abc 1 3)" "skip"
assert_eq "pending 只复查 checks" "$(agent_pipeline_review_action awaiting_checks abc abc 1 3)" "recheck"
assert_eq "head 变了要再审" "$(agent_pipeline_review_action awaiting_checks def abc 1 3)" "review"
assert_eq "审查次数用尽" "$(agent_pipeline_review_action pr_open def abc 3 3)" "cap"

assert_eq "ACCEPT 且无远端 checks 可以合并" "$(agent_pipeline_merge_gate accept pass none pass)" "merge"
assert_eq "ACCEPT 且 checks 在跑要等" "$(agent_pipeline_merge_gate accept pass pending pass)" "wait"
assert_eq "测试失败不准合并" "$(agent_pipeline_merge_gate accept fail pass pass)" "stop"
assert_eq "越界不准合并" "$(agent_pipeline_merge_gate accept pass pass fail)" "stop"
assert_eq "FIX 不走合并闸门" "$(agent_pipeline_merge_gate fix pass pass pass)" "ignore"
assert_eq "checks 等待未到上限" "$(agent_pipeline_checks_wait 9 10)" "wait"
assert_eq "checks 等待到达上限" "$(agent_pipeline_checks_wait 10 10)" "timeout"

state_file="$TMP/state"
agent_pipeline_state_put "$state_file" status pr_open
agent_pipeline_state_put "$state_file" fix_rounds 1
agent_pipeline_state_put "$state_file" status needs_fix
assert_eq "状态可更新" "$(agent_pipeline_state_get "$state_file" status)" "needs_fix"
assert_eq "其他键还在" "$(agent_pipeline_state_get "$state_file" fix_rounds)" "1"

for script in agent-implement.sh agent-review.sh agent-poll.sh; do
  bash -n "$ROOT/scripts/$script"
  "$ROOT/scripts/$script" --help >/dev/null
  printf 'ok %s --help\n' "$script"
done
bash -n "$ROOT/scripts/lib/agent-pipeline-common.sh"
printf 'ok bash -n\n'

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
printf 'all agent pipeline tests passed\n'

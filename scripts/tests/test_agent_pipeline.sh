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

HEAD_SHA="0123456789abcdef0123456789abcdef01234567"
cat > "$TMP/accept.txt" <<EOF
VERDICT: ACCEPT
unit: ran ${HEAD_SHA}
console/SSE: not run
live provider: not run
NOTES: 可以合并
EOF
printf '%s\n' "读者能看到检查命令" > "$TMP/acceptance-plain.txt"
assert_eq "检查声明不进 NOTES" "$(agent_pipeline_py notes "$TMP/accept.txt")" "可以合并"
assert_eq "三项声明按固定顺序" "$(agent_pipeline_py checks-block "$TMP/accept.txt")" "$(printf 'unit: ran %s\nconsole/SSE: not run\nlive provider: not run' "$HEAD_SHA")"
assert_eq "默认只要求 unit" "$(agent_pipeline_py checks-gate "$TMP/acceptance-plain.txt" "$TMP/accept.txt" "$HEAD_SHA")" "pass"

cat > "$TMP/accept-short.txt" <<'EOF'
VERDICT: ACCEPT
console/SSE: not run
live provider: not run
unit: ran 0123456
EOF
assert_eq "短 sha 对得上 head" "$(agent_pipeline_py checks-gate "$TMP/acceptance-plain.txt" "$TMP/accept-short.txt" "$HEAD_SHA")" "pass"

cat > "$TMP/accept-missing.txt" <<EOF
VERDICT: ACCEPT
unit: ran ${HEAD_SHA}
live provider: not run
EOF
assert_eq "少一行则不能合并" "$(agent_pipeline_py checks-gate "$TMP/acceptance-plain.txt" "$TMP/accept-missing.txt" "$HEAD_SHA")" "$(printf 'stop\nmissing')"

cat > "$TMP/accept-unit-skip.txt" <<'EOF'
VERDICT: ACCEPT
unit: not run
console/SSE: not run
live provider: not run
EOF
assert_eq "默认 unit 没跑不能合并" "$(agent_pipeline_py checks-gate "$TMP/acceptance-plain.txt" "$TMP/accept-unit-skip.txt" "$HEAD_SHA")" "$(printf 'stop\nnot-run unit')"

printf '%s\n' "console/SSE: required" > "$TMP/acceptance-console.txt"
assert_eq "点名的 console 没跑不能合并" "$(agent_pipeline_py checks-gate "$TMP/acceptance-console.txt" "$TMP/accept.txt" "$HEAD_SHA")" "$(printf 'stop\nnot-run console/SSE')"

printf '%s\n' "- live provider: required" > "$TMP/acceptance-live.txt"
cat > "$TMP/accept-live.txt" <<EOF
VERDICT: ACCEPT
unit: ran ${HEAD_SHA}
console/SSE: not run
live provider: ran deadbeef
EOF
assert_eq "ran 的 sha 不是这个 head" "$(agent_pipeline_py checks-gate "$TMP/acceptance-live.txt" "$TMP/accept-live.txt" "$HEAD_SHA")" "$(printf 'stop\nsha live provider')"

printf '%s\n' "unit: not required" > "$TMP/acceptance-no-unit.txt"
assert_eq "写明 unit 不必查时可以 not run" "$(agent_pipeline_py checks-gate "$TMP/acceptance-no-unit.txt" "$TMP/accept-unit-skip.txt" "$HEAD_SHA")" "pass"
assert_eq "FIX 不走检查声明闸门" "$(agent_pipeline_py checks-gate "$TMP/acceptance-plain.txt" "$TMP/verdict.txt" "$HEAD_SHA")" "ignore"

cat > "$TMP/lessons.md" <<'EOF'
# Lessons

### 这段在仍有效之外，不该被扫到

- Seen 3× (2026-01-01, 2026-01-02, 2026-01-03)

## 仍有效

### 记录跑过的检查

- Evidence: #1 合入时没写跑了什么
- Seen 3× (2026-07-01, 2026-07-02, 2026-07-03)

### 旧规则还没满三次

- Seen 1× (2026-07-28).

### 九十天前正好还留着

- Seen 1x (2026-07-29)

### 最近只出现一次

- Seen 1× (2026-10-20)

### 次数和日期对不上

- Seen 2× (2026-10-20)

## 归档

### 已经归档的不再处理

- Seen 1× (2026-01-01)
EOF
assert_eq "错题本升格、归档和格式" \
  "$(agent_pipeline_py lesson-status "$TMP/lessons.md" 2026-10-27)" \
  "$(printf '%s\n' \
    'promote	记录跑过的检查	2026-07-01, 2026-07-02, 2026-07-03' \
    'archive	旧规则还没满三次	2026-07-28' \
    'ok	九十天前正好还留着' \
    'ok	最近只出现一次' \
    'bad	次数和日期对不上	Seen count does not match dates')"

set +e
"$ROOT/scripts/agent-night-review.sh" --check --lessons "$TMP/lessons.md" --date 2026-10-27 >/dev/null
night_rc=$?
set -e
assert_eq "夜审核对发现升格或归档时退出 2" "$night_rc" "2"

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

AGENT_PIPELINE_LIVE_PROVIDER=0 AGENT_PIPELINE_STATE_DIR="$TMP/night-state" "$ROOT/scripts/agent-night-review.sh" --packet --date 2026-10-27 >/dev/null
packet="$TMP/night-state/night-review/2026-10-27.md"
if [[ -f "$packet" ]] && grep -q "夜审" "$packet" && grep -q "契约文件" "$packet" && grep -q "live provider: skipped by environment" "$packet"; then
  printf 'ok 夜审证据包\n'
else
  printf 'FAIL 夜审证据包\n' >&2
  FAIL=1
fi

cat > "$TMP/unit-ok.log" <<'EOF'
test_console_journey_probe_chat_and_diagnostics (python_scripts.tests.test_public_contract.PublicContractTests.test_console_journey_probe_chat_and_diagnostics) ... ok
test_process_stream_reaches_done (python_scripts.tests.test_public_contract.ProcessStreamContractTests.test_process_stream_reaches_done) ... ok
----------------------------------------------------------------------
Ran 2 tests in 0.1s

OK
EOF
assert_eq "质量闸门通过" "$(agent_pipeline_py quality-gate "$TMP/unit-ok.log" 2 2 abcdef abcdef)" "pass"
dropped=$(agent_pipeline_py quality-gate "$TMP/unit-ok.log" 3 2 abcdef abcdef)
assert_eq "用例变少不能过" "${dropped%%$'\n'*}" "stop"
changed=$(agent_pipeline_py quality-gate "$TMP/unit-ok.log" 2 2 abcdef 123456)
assert_eq "契约文件变了不能过" "${changed%%$'\n'*}" "stop"
printf '%s\n' "FAILED" > "$TMP/unit-bad.log"
bad_log=$(agent_pipeline_py quality-gate "$TMP/unit-bad.log" 2 2 abcdef abcdef)
assert_eq "日志没有 OK 不能过" "${bad_log%%$'\n'*}" "stop"

printf '%s\n' "console/SSE: required" > "$TMP/need-console.txt"
console_gate=$(agent_pipeline_py surface-gate "$TMP/need-console.txt" "$TMP/unit-bad.log")
assert_eq "点名的控制台旅程没在日志里" "${console_gate%%$'\n'*}" "stop"
console_ok=$(agent_pipeline_py surface-gate "$TMP/need-console.txt" "$TMP/unit-ok.log")
assert_eq "日志里的控制台旅程可以过" "$console_ok" "pass"
printf '%s\n' "live provider: required" > "$TMP/need-live.txt"
printf '%s\n' "live provider: skipped no key" > "$TMP/live-skip.log"
live_skip=$(agent_pipeline_py surface-gate "$TMP/need-live.txt" "$TMP/live-skip.log")
assert_eq "跳过真实 provider 不算跑过" "${live_skip%%$'\n'*}" "stop"
printf '%s\n' "live provider: ok" > "$TMP/live-ok.log"
assert_eq "真实 provider 通过" "$(agent_pipeline_py surface-gate "$TMP/need-live.txt" "$TMP/live-ok.log")" "pass"
assert_eq "默认不要求 live" "$(agent_pipeline_py check-required "$TMP/acceptance-plain.txt" "live provider")" "no"
assert_eq "点名后要求 live" "$(agent_pipeline_py check-required "$TMP/need-live.txt" "live provider")" "yes"

defs=$(agent_pipeline_count_test_defs "$ROOT")
if [[ "$defs" -gt 0 ]]; then
  printf 'ok 工作区测试方法计数\n'
else
  printf 'FAIL 工作区测试方法计数\n' >&2
  FAIL=1
fi
assert_eq "契约哈希等于工作区文件" \
  "$(agent_pipeline_contract_hash "$ROOT")" \
  "$(git -C "$ROOT" hash-object python_scripts/tests/test_public_contract.py)"

empty_repo=$(mktemp -d)
set +e
agent_pipeline_run_project_tests "$empty_repo" "$TMP/missing-tests.log" main
missing_rc=$?
set -e
assert_eq "没有测试目录时失败" "$missing_rc" "1"
if grep -q "missing python_scripts/tests" "$TMP/missing-tests.log"; then
  printf 'ok 缺失测试目录写进日志\n'
else
  printf 'FAIL 缺失测试目录写进日志\n' >&2
  FAIL=1
fi

for script in agent-implement.sh agent-review.sh agent-poll.sh agent-night-review.sh; do
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

#!/usr/bin/env bash
# 审查者 B。约定见 docs/agent-pipeline.md。
# 用法: scripts/agent-review.sh <pr-number> [--dry-run] [--no-merge]
#
# 这是一个新进程：不读取实现者的对话，只读 Issue、diff 和测试日志。
# ACCEPT 且检查通过时 gh pr merge --squash（可用环境变量改策略）。
# REJECT，或两轮 FIX 之后仍然 FIX，则评论并停止。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib/agent-pipeline-common.sh
source "$SCRIPT_DIR/lib/agent-pipeline-common.sh"

usage() {
  cat <<'EOF'
用法: scripts/agent-review.sh <pr-number> [--dry-run] [--no-merge]

在新 worktree 里审查流水线 PR（正文含 agent-pipeline:issue=N）。
解析 VERDICT: ACCEPT|REJECT|FIX。
ACCEPT 且本地测试、Only-edit、GitHub checks 都允许时，squash 合并。

--dry-run   不调用 agent，不评论，不合并
--no-merge  即使 ACCEPT 也不执行 gh pr merge
EOF
}

PR=""
DRY=0
MERGE="${AGENT_PIPELINE_MERGE:-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY=1
      ;;
    --no-merge)
      MERGE=0
      ;;
    --fix)
      agent_pipeline_die "--fix 属于 agent-implement.sh"
      ;;
    --*)
      agent_pipeline_die "未知参数: $1（试试 --help）"
      ;;
    *)
      if [[ -n "$PR" ]]; then
        agent_pipeline_die "多余参数: $1"
      fi
      PR="$1"
      ;;
  esac
  shift
done

if [[ -z "$PR" ]]; then
  usage >&2
  exit 2
fi

agent_pipeline_require_number "$PR"
agent_pipeline_require_tools
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  agent_pipeline_die "请在 git 工作区里运行"
fi
agent_pipeline_init "$(git rev-parse --show-toplevel)"
cd "$AGENT_PIPELINE_MAIN_ROOT"
export GH_PROMPT_DISABLED=1
export GIT_TERMINAL_PROMPT=0
if [[ "$DRY" -eq 1 ]]; then
  export AGENT_PIPELINE_DRY_RUN=1
fi

WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-review.XXXXXX")
STARTED=0
STATE_FILE=""
ISSUE=""

cleanup() {
  local rc=$?
  local cur
  if [[ "$STARTED" -eq 1 && "$rc" -ne 0 && -n "$STATE_FILE" ]]; then
    cur=$(agent_pipeline_state_get "$STATE_FILE" status || true)
    if [[ "$cur" == "reviewing" ]]; then
      agent_pipeline_state_put "$STATE_FILE" status stopped || true
      agent_pipeline_state_put "$STATE_FILE" reason crashed || true
      agent_pipeline_state_put "$STATE_FILE" owner_pid "" || true
    fi
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

stop_pipeline() {
  local reason="$1" marker="$2" message="$3"
  agent_pipeline_state_put "$STATE_FILE" status stopped
  agent_pipeline_state_put "$STATE_FILE" reason "$reason"
  agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  agent_pipeline_comment_once pr "$PR" "$marker" "$message"
  exit 0
}

gh pr view "$PR" --json number,title,body,state,url,headRefName,headRefOid,baseRefName > "$WORKDIR/pr.json"
pr_state=$(agent_pipeline_py json-str "$WORKDIR/pr.json" state)
agent_pipeline_py json-str "$WORKDIR/pr.json" body > "$WORKDIR/pr-body.md"
agent_pipeline_py json-str "$WORKDIR/pr.json" title > "$WORKDIR/pr-title.txt"
head_ref=$(agent_pipeline_py json-str "$WORKDIR/pr.json" headRefName)
head_sha=$(agent_pipeline_py json-str "$WORKDIR/pr.json" headRefOid)
base_ref=$(agent_pipeline_py json-str "$WORKDIR/pr.json" baseRefName)
pr_title=$(cat "$WORKDIR/pr-title.txt")

ISSUE=$(sed -n 's/.*agent-pipeline:issue=\([0-9][0-9]*\).*/\1/p' "$WORKDIR/pr-body.md" | head -n 1)
if [[ -z "$ISSUE" ]]; then
  agent_pipeline_die "PR #$PR 不是流水线 PR（正文没有 agent-pipeline:issue= 标记）"
fi
STATE_FILE=$(agent_pipeline_state_file "$ISSUE")

if [[ "$pr_state" == "MERGED" ]]; then
  if [[ "$DRY" -eq 0 ]]; then
    agent_pipeline_state_put "$STATE_FILE" status merged
    agent_pipeline_state_put "$STATE_FILE" pr "$PR"
    agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  fi
  agent_pipeline_log "PR #$PR 已合并"
  exit 0
fi
if [[ "$pr_state" != "OPEN" ]]; then
  if [[ "$DRY" -eq 1 ]]; then
    printf 'dry-run: PR #%s 状态是 %s\n' "$PR" "$pr_state"
    exit 0
  fi
  stop_pipeline pr_closed \
    "<!-- agent-pipeline:notice=pr-closed -->" \
    "PR #${PR} 已关闭且未合并。流水线停止。"
fi

status=$(agent_pipeline_state_get "$STATE_FILE" status)
last_reviewed=$(agent_pipeline_state_get "$STATE_FILE" last_reviewed_sha)
review_count=$(agent_pipeline_state_get "$STATE_FILE" review_count)
fix_rounds=$(agent_pipeline_state_get "$STATE_FILE" fix_rounds)
checks_polls=$(agent_pipeline_state_get "$STATE_FILE" checks_polls)
stored_local_tests=$(agent_pipeline_state_get "$STATE_FILE" local_tests)
stored_only_edit=$(agent_pipeline_state_get "$STATE_FILE" only_edit)
review_count=${review_count:-0}
fix_rounds=${fix_rounds:-0}
checks_polls=${checks_polls:-0}
status=${status:-pr_open}

owner_pid=$(agent_pipeline_state_get "$STATE_FILE" owner_pid)
if [[ "$status" == "reviewing" || "$status" == "implementing" ]]; then
  if agent_pipeline_pid_alive "$owner_pid"; then
    agent_pipeline_log "issue #$ISSUE 已有进程 $owner_pid 在跑，跳过审查"
    exit 0
  fi
fi

action=$(agent_pipeline_review_action "$status" "$head_sha" "$last_reviewed" "$review_count" "$AGENT_PIPELINE_MAX_REVIEWS")
agent_pipeline_log "PR #$PR issue #$ISSUE 审查动作=$action head=${head_sha:0:7}"

if [[ "$action" == "skip" ]]; then
  exit 0
fi

merge_pr() {
  local strategy flag merge_rc
  if [[ "$MERGE" != "1" ]]; then
    agent_pipeline_comment_once pr "$PR" \
      "<!-- agent-pipeline:notice=accept-no-merge sha=${head_sha} -->" \
      "审查结果是 ACCEPT，检查通过。AGENT_PIPELINE_MERGE=0，没有执行 gh pr merge。"
    agent_pipeline_state_put "$STATE_FILE" status accepted_unmerged
    agent_pipeline_state_put "$STATE_FILE" verdict ACCEPT
    agent_pipeline_state_put "$STATE_FILE" owner_pid ""
    agent_pipeline_state_put "$STATE_FILE" head_sha "$head_sha"
    agent_pipeline_state_put "$STATE_FILE" last_reviewed_sha "$head_sha"
    return 0
  fi
  strategy="${AGENT_PIPELINE_MERGE_STRATEGY:-squash}"
  case "$strategy" in
    squash) flag="--squash" ;;
    merge) flag="--merge" ;;
    rebase) flag="--rebase" ;;
    *) agent_pipeline_die "AGENT_PIPELINE_MERGE_STRATEGY 只能是 squash、merge 或 rebase" ;;
  esac
  agent_pipeline_comment_once pr "$PR" \
    "<!-- agent-pipeline:notice=merging sha=${head_sha} -->" \
    "ACCEPT，且约定检查通过。准备 ${strategy} 合并 ${head_sha}。"
  # 先卸掉 worktree，否则本机分支还被占用，gh pr merge --delete-branch 会失败。
  agent_pipeline_remove_worktree "$AGENT_PIPELINE_MAIN_ROOT/.worktrees/agent-pipeline/review-${PR}"
  agent_pipeline_remove_worktree "$AGENT_PIPELINE_MAIN_ROOT/.worktrees/agent-pipeline/issue-${ISSUE}"
  set +e
  gh pr merge "$PR" "$flag" --delete-branch --match-head-commit "$head_sha"
  merge_rc=$?
  set -e
  if [[ "$merge_rc" -ne 0 ]]; then
    stop_pipeline merge_failed \
      "<!-- agent-pipeline:notice=merge-failed sha=${head_sha} -->" \
      "gh pr merge 退出码 ${merge_rc}。流水线停止，没有自动重试。"
  fi
  issue_state=$(gh issue view "$ISSUE" --json state --jq .state || true)
  if [[ "$issue_state" == "OPEN" ]]; then
    gh issue close "$ISSUE" --reason completed --comment "PR #${PR} 已由本地 agent 流水线合并，关闭这个 Issue。"
  fi
  if agent_pipeline_branch_exists_local "$head_ref"; then
    git -C "$AGENT_PIPELINE_MAIN_ROOT" branch -D "$head_ref" || true
  fi
  agent_pipeline_state_put "$STATE_FILE" status merged
  agent_pipeline_state_put "$STATE_FILE" pr "$PR"
  agent_pipeline_state_put "$STATE_FILE" verdict ACCEPT
  agent_pipeline_state_put "$STATE_FILE" head_sha "$head_sha"
  agent_pipeline_state_put "$STATE_FILE" last_reviewed_sha "$head_sha"
  agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  agent_pipeline_state_put "$STATE_FILE" reason ""
  agent_pipeline_log "PR #$PR 已合并，issue #$ISSUE 关闭流程已走完"
}

apply_gate() {
  local gate="$1"
  local polls_now="$2"
  case "$gate" in
    merge)
      merge_pr
      ;;
    wait)
      local wait_result
      wait_result=$(agent_pipeline_checks_wait "$polls_now" "$AGENT_PIPELINE_CHECKS_MAX_POLLS")
      if [[ "$wait_result" == "timeout" ]]; then
        stop_pipeline checks_timeout \
          "<!-- agent-pipeline:notice=checks-timeout sha=${head_sha} -->" \
          "ACCEPT 之后 GitHub checks 一直 pending，已等待 ${polls_now} 轮。流水线停止。"
      fi
      agent_pipeline_state_put "$STATE_FILE" status awaiting_checks
      agent_pipeline_state_put "$STATE_FILE" verdict ACCEPT
      agent_pipeline_state_put "$STATE_FILE" checks_polls "$polls_now"
      agent_pipeline_state_put "$STATE_FILE" head_sha "$head_sha"
      agent_pipeline_state_put "$STATE_FILE" last_reviewed_sha "$head_sha"
      agent_pipeline_state_put "$STATE_FILE" owner_pid ""
      agent_pipeline_log "PR #$PR checks pending，已等待 ${polls_now}/${AGENT_PIPELINE_CHECKS_MAX_POLLS}"
      ;;
    stop)
      stop_pipeline checks_red \
        "<!-- agent-pipeline:notice=checks-red sha=${head_sha} -->" \
        "审查结果是 ACCEPT，但本地测试、Only-edit 或 GitHub checks 不允许合并。流水线停止，不会自动再修一轮。"
      ;;
    *)
      agent_pipeline_die "未知合并闸门: $gate"
      ;;
  esac
}

if [[ "$action" == "cap" ]]; then
  if [[ "$DRY" -eq 1 ]]; then
    printf 'dry-run: PR #%s 已达审查次数上限\n' "$PR"
    exit 0
  fi
  stop_pipeline review_cap \
    "<!-- agent-pipeline:notice=review-cap -->" \
    "审查次数已达 ${AGENT_PIPELINE_MAX_REVIEWS}。流水线停止。"
fi

if [[ "$action" == "recheck" ]]; then
  if [[ "$DRY" -eq 1 ]]; then
    printf 'dry-run: 将只复查 PR #%s 的 GitHub checks，不重新调用审查者\n' "$PR"
    exit 0
  fi
  checks_polls=$((checks_polls + 1))
  remote=$(agent_pipeline_classify_remote_checks "$PR" "$WORKDIR/checks.json" "$WORKDIR/checks.err")
  gate=$(agent_pipeline_merge_gate accept "${stored_local_tests:-pass}" "$remote" "${stored_only_edit:-skip}")
  apply_gate "$gate" "$checks_polls"
  exit 0
fi

# action == review
if [[ "$DRY" -eq 1 ]]; then
  printf 'dry-run: 将在新 worktree 审查 PR #%s（issue #%s）\n' "$PR" "$ISSUE"
  printf 'dry-run: 分支 %s @ %s，基于 %s\n' "$head_ref" "$head_sha" "$base_ref"
  printf 'dry-run: agent=%s。ACCEPT 后 merge=%s\n' "${AGENT_BIN:-agent}" "$MERGE"
  exit 0
fi

agent_pipeline_state_put "$STATE_FILE" status reviewing
agent_pipeline_state_put "$STATE_FILE" owner_pid "$$"
agent_pipeline_state_put "$STATE_FILE" pr "$PR"
agent_pipeline_state_put "$STATE_FILE" branch "$head_ref"
agent_pipeline_state_put "$STATE_FILE" base "$base_ref"
agent_pipeline_state_put "$STATE_FILE" reason ""
STARTED=1

wt="$AGENT_PIPELINE_MAIN_ROOT/.worktrees/agent-pipeline/review-${PR}"
git -C "$AGENT_PIPELINE_MAIN_ROOT" fetch origin "$base_ref" "$head_ref"
agent_pipeline_prepare_detached_worktree "$wt" "$head_sha"

mkdir -p "$AGENT_PIPELINE_STATE_DIR/reviews" "$AGENT_PIPELINE_STATE_DIR/prompts" "$AGENT_PIPELINE_STATE_DIR/issues"
diff_file="$AGENT_PIPELINE_STATE_DIR/reviews/pr-${PR}.diff"
stat_file="$AGENT_PIPELINE_STATE_DIR/reviews/pr-${PR}.stat"
test_log="$AGENT_PIPELINE_STATE_DIR/reviews/pr-${PR}.tests.log"
verdict_file="$AGENT_PIPELINE_STATE_DIR/reviews/pr-${PR}.verdict"
prompt_file="$AGENT_PIPELINE_STATE_DIR/prompts/review-${PR}.txt"
stdout_log="$AGENT_PIPELINE_STATE_DIR/prompts/review-${PR}.stdout"
rm -f "$verdict_file"

git -C "$wt" diff --stat "origin/${base_ref}...HEAD" > "$stat_file"
git -C "$wt" diff "origin/${base_ref}...HEAD" > "$diff_file"
git -C "$wt" diff --name-only "origin/${base_ref}...HEAD" > "$WORKDIR/changed.txt"

body_snapshot="$AGENT_PIPELINE_STATE_DIR/issues/${ISSUE}.body.md"
if [[ ! -f "$body_snapshot" ]]; then
  gh issue view "$ISSUE" --json body --jq .body > "$body_snapshot"
fi
agent_pipeline_py extract "$body_snapshot" "Goal" > "$WORKDIR/goal.txt"
agent_pipeline_py extract "$body_snapshot" "Acceptance" > "$WORKDIR/acceptance.txt"
agent_pipeline_py extract "$body_snapshot" "Only-edit" > "$WORKDIR/only-edit.txt"
only_result=$(agent_pipeline_py only-edit "$WORKDIR/only-edit.txt" "$WORKDIR/changed.txt")
only_status=$(printf '%s\n' "$only_result" | head -n 1)
only_bad=$(printf '%s\n' "$only_result" | tail -n +2)

set +e
agent_pipeline_run_project_tests "$wt" "$test_log"
test_rc=$?
set -e
if [[ "$test_rc" -eq 0 ]]; then
  local_tests="pass"
else
  local_tests="fail"
fi

{
  cat "$AGENT_PIPELINE_MAIN_ROOT/docs/agent-pipeline/reviewer-brief.md"
  printf '\n## 交接\n\n'
  printf '这是新进程。你没有实现者的对话。\n'
  printf 'PR: #%s %s\n' "$PR" "$pr_title"
  printf 'Issue: #%s\n' "$ISSUE"
  printf 'Head: %s\n' "$head_sha"
  printf '已完成的 FIX 轮次: %s / %s\n' "$fix_rounds" "$AGENT_PIPELINE_MAX_FIX_ROUNDS"
  printf '裁决文件（必须写入这个绝对路径）: %s\n' "$verdict_file"
  printf 'Diff 文件: %s\n' "$diff_file"
  printf '测试日志: %s\n' "$test_log"
  printf '本地测试: %s\n' "$local_tests"
  printf 'Only-edit 机械检查: %s\n' "$only_status"
  if [[ -n "$only_bad" ]]; then
    printf '机械检查认为越界的文件:\n%s\n' "$only_bad"
  fi
  printf '\nDiff stat:\n\n'
  cat "$stat_file"
  printf '\n\n## Goal\n\n'
  cat "$WORKDIR/goal.txt"
  printf '\n\n## Acceptance\n\n'
  cat "$WORKDIR/acceptance.txt"
  printf '\n\n## Only-edit\n\n'
  cat "$WORKDIR/only-edit.txt"
  printf '\n'
} > "$prompt_file"

set +e
agent_pipeline_invoke "$wt" "$prompt_file" "$stdout_log"
invoke_rc=$?
set -e
if [[ "$invoke_rc" -ne 0 ]]; then
  reason="agent_failed"
  if [[ "$invoke_rc" -eq 124 ]]; then
    reason="timeout"
  fi
  stop_pipeline "$reason" \
    "<!-- agent-pipeline:notice=review-${reason} -->" \
    "审查者进程退出码 ${invoke_rc}。流水线停止。日志: ${stdout_log}"
fi

if [[ -n "$(git -C "$wt" status --porcelain)" ]]; then
  stop_pipeline reviewer_modified_tree \
    "<!-- agent-pipeline:notice=reviewer-dirty sha=${head_sha} -->" \
    "审查者改动了 worktree。审查必须只读。这次结果作废，流水线停止。"
fi

verdict=""
if verdict=$(agent_pipeline_py verdict "$verdict_file"); then
  :
elif verdict=$(agent_pipeline_py verdict "$stdout_log"); then
  :
else
  verdict=""
fi
if [[ -z "$verdict" ]]; then
  stop_pipeline no_verdict \
    "<!-- agent-pipeline:notice=no-verdict sha=${head_sha} -->" \
    "审查者没有写出 VERDICT: ACCEPT、REJECT 或 FIX。流水线停止。期望文件: ${verdict_file}"
fi

notes=""
if [[ -f "$verdict_file" ]]; then
  notes=$(agent_pipeline_py notes "$verdict_file" || true)
fi
if [[ -z "$notes" ]]; then
  notes=$(agent_pipeline_py notes "$stdout_log" || true)
fi
printf '%s\n' "$notes" > "$AGENT_PIPELINE_STATE_DIR/issues/${ISSUE}.notes"

review_count=$((review_count + 1))
applied=$(agent_pipeline_apply_verdict "$verdict" "$fix_rounds" "$AGENT_PIPELINE_MAX_FIX_ROUNDS")
agent_pipeline_state_put "$STATE_FILE" review_count "$review_count"
agent_pipeline_state_put "$STATE_FILE" verdict "$verdict"
agent_pipeline_state_put "$STATE_FILE" head_sha "$head_sha"
agent_pipeline_state_put "$STATE_FILE" last_reviewed_sha "$head_sha"
agent_pipeline_state_put "$STATE_FILE" local_tests "$local_tests"
agent_pipeline_state_put "$STATE_FILE" only_edit "$only_status"
agent_pipeline_state_put "$STATE_FILE" owner_pid ""

case "$applied" in
  accept)
    remote=$(agent_pipeline_classify_remote_checks "$PR" "$WORKDIR/checks.json" "$WORKDIR/checks.err")
    gate=$(agent_pipeline_merge_gate accept "$local_tests" "$remote" "$only_status")
    apply_gate "$gate" 0
    ;;
  fix)
    fix_rounds=$((fix_rounds + 1))
    agent_pipeline_state_put "$STATE_FILE" fix_rounds "$fix_rounds"
    agent_pipeline_state_put "$STATE_FILE" status needs_fix
    agent_pipeline_comment_once pr "$PR" \
      "<!-- agent-pipeline:notice=fix sha=${head_sha} round=${fix_rounds} -->" \
      "审查结果 FIX（第 ${fix_rounds}/${AGENT_PIPELINE_MAX_FIX_ROUNDS} 轮）。下一轮实现者只会看到这些 NOTES:

${notes}"
    ;;
  reject|reject_exhausted)
    reason="rejected"
    extra=""
    if [[ "$applied" == "reject_exhausted" ]]; then
      reason="fix_rounds_exhausted"
      extra="已经用完 ${AGENT_PIPELINE_MAX_FIX_ROUNDS} 轮 FIX，本次 FIX 按 REJECT 停止。"
    fi
    agent_pipeline_state_put "$STATE_FILE" status rejected
    agent_pipeline_state_put "$STATE_FILE" reason "$reason"
    agent_pipeline_comment_once pr "$PR" \
      "<!-- agent-pipeline:notice=reject sha=${head_sha} -->" \
      "审查结果 ${verdict}。流水线停止，不会再自动修改。${extra}

${notes}"
    agent_pipeline_remove_worktree "$wt"
    ;;
  *)
    stop_pipeline bad_verdict \
      "<!-- agent-pipeline:notice=bad-verdict sha=${head_sha} -->" \
      "无法使用裁决 ${verdict}。流水线停止。"
    ;;
esac

STARTED=0
agent_pipeline_log "PR #$PR 审查结束: $applied"

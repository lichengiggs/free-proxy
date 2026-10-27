#!/usr/bin/env bash
# 实现者 A。约定见 docs/agent-pipeline.md。
# 用法: scripts/agent-implement.sh <issue-number> [--dry-run] [--fix]
#
# 假设:
# - 在 git 仓库里执行，GitHub 远程名是 origin。
# - 编码 CLI 由 AGENT_BIN 决定，默认 agent。精确参数见
#   scripts/lib/agent-pipeline-common.sh 里的 agent_pipeline_invoke。
# - 本脚本会提交、跑测试、push、开 PR。agent 只改 worktree。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib/agent-pipeline-common.sh
source "$SCRIPT_DIR/lib/agent-pipeline-common.sh"

usage() {
  cat <<'EOF'
用法: scripts/agent-implement.sh <issue-number> [--dry-run] [--fix]

读取带 ready 标签、且包含 Goal / Acceptance / Only-edit 的 Issue。
创建 worktree 和分支 agent/fix-<issue>，调用本地编码 agent，
测试通过后 gh pr create，并在正文里关联这个 Issue。

--fix      在已有分支上再改一轮，不新开 PR
--dry-run  只核对 Issue 并打印计划，不改 git，不评论
EOF
}

ISSUE=""
FIX=0
DRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      DRY=1
      ;;
    --fix)
      FIX=1
      ;;
    --no-merge)
      ;;
    --*)
      agent_pipeline_die "未知参数: $1（试试 --help）"
      ;;
    *)
      if [[ -n "$ISSUE" ]]; then
        agent_pipeline_die "多余参数: $1"
      fi
      ISSUE="$1"
      ;;
  esac
  shift
done

if [[ -z "$ISSUE" ]]; then
  usage >&2
  exit 2
fi

agent_pipeline_require_number "$ISSUE"
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

WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-implement.XXXXXX")
STATE_FILE=$(agent_pipeline_state_file "$ISSUE")
STARTED=0

cleanup() {
  local rc=$?
  local cur
  if [[ "$STARTED" -eq 1 && "$rc" -ne 0 && -n "$STATE_FILE" ]]; then
    cur=$(agent_pipeline_state_get "$STATE_FILE" status || true)
    if [[ "$cur" == "implementing" ]]; then
      agent_pipeline_state_put "$STATE_FILE" status stopped || true
      agent_pipeline_state_put "$STATE_FILE" reason crashed || true
      agent_pipeline_state_put "$STATE_FILE" owner_pid "" || true
    fi
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

stop_issue() {
  local reason="$1" marker="$2" message="$3"
  agent_pipeline_state_put "$STATE_FILE" status stopped
  agent_pipeline_state_put "$STATE_FILE" reason "$reason"
  agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  agent_pipeline_comment_once issue "$ISSUE" "$marker" "$message"
  exit 0
}

gh issue view "$ISSUE" --json number,title,body,state,url,labels > "$WORKDIR/issue.json"
issue_state=$(agent_pipeline_py json-str "$WORKDIR/issue.json" state)
agent_pipeline_py json-str "$WORKDIR/issue.json" title > "$WORKDIR/title.txt"
agent_pipeline_py json-str "$WORKDIR/issue.json" body > "$WORKDIR/body.md"
agent_pipeline_py json-str "$WORKDIR/issue.json" url > "$WORKDIR/url.txt"
title=$(cat "$WORKDIR/title.txt")
issue_url=$(cat "$WORKDIR/url.txt")
body_sha=$(agent_pipeline_hash_file "$WORKDIR/body.md")

if [[ "$issue_state" != "OPEN" ]]; then
  agent_pipeline_die "issue #$ISSUE 不是打开状态（当前 $issue_state）"
fi
if ! agent_pipeline_py has-label "$WORKDIR/issue.json" "ready"; then
  agent_pipeline_die "issue #$ISSUE 没有标签 ready"
fi

missing=""
if ! missing=$(agent_pipeline_py missing-sections "$WORKDIR/body.md"); then
  agent_pipeline_log "issue #$ISSUE 缺少小节: $missing"
  if [[ "$DRY" -eq 1 ]]; then
    printf 'issue #%s 缺少或空着这些小节: %s\n' "$ISSUE" "$missing" >&2
    exit 2
  fi
  agent_pipeline_state_put "$STATE_FILE" status stopped
  agent_pipeline_state_put "$STATE_FILE" reason malformed
  agent_pipeline_state_put "$STATE_FILE" body_sha "$body_sha"
  agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  agent_pipeline_comment_once issue "$ISSUE" \
    "<!-- agent-pipeline:notice=malformed sha=${body_sha} -->" \
    "流水线没有启动实现者。Issue 需要非空的 ## Goal、## Acceptance、## Only-edit。当前缺少: ${missing}"
  exit 0
fi

agent_pipeline_py extract "$WORKDIR/body.md" "Only-edit" > "$WORKDIR/only-edit.txt"
agent_pipeline_fetch_open_prs_json "$WORKDIR/prs.json"
agent_pipeline_py match-prs "$WORKDIR/prs.json" "$ISSUE" > "$WORKDIR/matches.txt"
pipeline_pr=""
human_pr=""
while IFS=$'\t' read -r kind number; do
  [[ -n "${kind:-}" ]] || continue
  if [[ "$kind" == "pipeline" && -z "$pipeline_pr" ]]; then
    pipeline_pr="$number"
  elif [[ "$kind" == "human" && -z "$human_pr" ]]; then
    human_pr="$number"
  fi
done < "$WORKDIR/matches.txt"

if [[ "$FIX" -eq 0 && -n "$pipeline_pr" ]]; then
  agent_pipeline_log "issue #$ISSUE 已有流水线 PR #$pipeline_pr，不再另开"
  if [[ "$DRY" -eq 1 ]]; then
    exit 0
  fi
  current_status=$(agent_pipeline_state_get "$STATE_FILE" status)
  case "$current_status" in
    pr_open|awaiting_checks|needs_fix|reviewing|implementing|merged|rejected)
      exit 0
      ;;
  esac
  head_ref=$(gh pr view "$pipeline_pr" --json headRefName --jq .headRefName)
  base_ref=$(gh pr view "$pipeline_pr" --json baseRefName --jq .baseRefName)
  agent_pipeline_state_put "$STATE_FILE" status pr_open
  agent_pipeline_state_put "$STATE_FILE" pr "$pipeline_pr"
  agent_pipeline_state_put "$STATE_FILE" branch "$head_ref"
  agent_pipeline_state_put "$STATE_FILE" base "$base_ref"
  agent_pipeline_state_put "$STATE_FILE" body_sha "$body_sha"
  agent_pipeline_state_put "$STATE_FILE" owner_pid ""
  agent_pipeline_state_put "$STATE_FILE" fix_rounds 0
  agent_pipeline_state_put "$STATE_FILE" review_count 0
  exit 0
fi

if [[ "$FIX" -eq 0 && -n "$human_pr" ]]; then
  agent_pipeline_log "issue #$ISSUE 已有非流水线 PR #$human_pr"
  if [[ "$DRY" -eq 1 ]]; then
    printf 'issue #%s 已有 PR #%s，但正文没有流水线标记\n' "$ISSUE" "$human_pr" >&2
    exit 2
  fi
  stop_issue human_pr \
    "<!-- agent-pipeline:notice=human-pr ${human_pr} -->" \
    "流水线没有启动。已有 PR #${human_pr} 关联了这个 Issue，但它不是流水线 PR（正文缺少 agent-pipeline:issue 标记）。"
fi

status=$(agent_pipeline_state_get "$STATE_FILE" status)
owner_pid=$(agent_pipeline_state_get "$STATE_FILE" owner_pid)
if [[ "$status" == "implementing" || "$status" == "reviewing" ]]; then
  if agent_pipeline_pid_alive "$owner_pid"; then
    agent_pipeline_log "issue #$ISSUE 已有进程 $owner_pid 在跑，跳过"
    exit 0
  fi
fi
if [[ "$status" == "merged" ]]; then
  agent_pipeline_die "issue #$ISSUE 的流水线状态已是 merged"
fi

base=$(agent_pipeline_default_branch)
branch="agent/fix-${ISSUE}"
if [[ "$FIX" -eq 1 ]]; then
  stored_branch=$(agent_pipeline_state_get "$STATE_FILE" branch)
  if [[ -n "$stored_branch" ]]; then
    branch="$stored_branch"
  fi
  if ! agent_pipeline_branch_exists_local "$branch" && ! agent_pipeline_branch_exists_remote "$branch"; then
    agent_pipeline_die "找不到分支 $branch，无法 --fix"
  fi
fi

short=$(printf '%.72s' "$title")
wt="$AGENT_PIPELINE_MAIN_ROOT/.worktrees/agent-pipeline/issue-${ISSUE}"
agent_pipeline_log "issue #$ISSUE base=$base branch=$branch worktree=$wt fix=$FIX"

if [[ "$DRY" -eq 1 ]]; then
  printf 'dry-run: 将处理 issue #%s\n' "$ISSUE"
  printf 'dry-run: 分支 %s，基于 origin/%s\n' "$branch" "$base"
  printf 'dry-run: worktree %s\n' "$wt"
  printf 'dry-run: agent=%s，然后跑 unittest，再 gh pr create\n' "${AGENT_BIN:-agent}"
  exit 0
fi

if [[ "$FIX" -eq 0 ]]; then
  if agent_pipeline_branch_exists_local "$branch" || agent_pipeline_branch_exists_remote "$branch"; then
    stop_issue branch_exists \
      "<!-- agent-pipeline:notice=branch-exists ${branch} -->" \
      "分支 ${branch} 已经存在。流水线没有另开分支。查看 .worktrees/agent-pipeline/issue-${ISSUE}，确认后删掉该分支再重新武装。"
  fi
fi

fix_rounds=$(agent_pipeline_state_get "$STATE_FILE" fix_rounds)
review_count=$(agent_pipeline_state_get "$STATE_FILE" review_count)
fix_rounds=${fix_rounds:-0}
review_count=${review_count:-0}
if [[ "$FIX" -eq 0 ]]; then
  fix_rounds=0
  review_count=0
fi

agent_pipeline_state_put "$STATE_FILE" status implementing
agent_pipeline_state_put "$STATE_FILE" owner_pid "$$"
agent_pipeline_state_put "$STATE_FILE" reason ""
agent_pipeline_state_put "$STATE_FILE" body_sha "$body_sha"
agent_pipeline_state_put "$STATE_FILE" branch "$branch"
agent_pipeline_state_put "$STATE_FILE" base "$base"
agent_pipeline_state_put "$STATE_FILE" fix_rounds "$fix_rounds"
agent_pipeline_state_put "$STATE_FILE" review_count "$review_count"
STARTED=1

mkdir -p "$AGENT_PIPELINE_STATE_DIR/issues" "$AGENT_PIPELINE_STATE_DIR/prompts"
cp "$WORKDIR/body.md" "$AGENT_PIPELINE_STATE_DIR/issues/${ISSUE}.body.md"
if [[ "$FIX" -eq 1 ]]; then
  agent_pipeline_prepare_existing_worktree "$wt" "$branch"
else
  agent_pipeline_prepare_new_worktree "$wt" "$branch" "$base"
fi

notes_file="$AGENT_PIPELINE_STATE_DIR/issues/${ISSUE}.notes"
prompt_file="$AGENT_PIPELINE_STATE_DIR/prompts/implement-${ISSUE}.txt"
stdout_log="$AGENT_PIPELINE_STATE_DIR/prompts/implement-${ISSUE}.stdout"
{
  cat "$AGENT_PIPELINE_MAIN_ROOT/docs/agent-pipeline/implementer-brief.md"
  printf '\n## 交接\n\n'
  printf 'Issue: #%s\n' "$ISSUE"
  printf 'URL: %s\n' "$issue_url"
  printf '标题: %s\n' "$title"
  printf '模式: %s\n' "$([[ "$FIX" -eq 1 ]] && printf 'fix' || printf 'initial')"
  printf '修复轮次计数（已完成的 FIX 次数）: %s / %s\n' "$fix_rounds" "$AGENT_PIPELINE_MAX_FIX_ROUNDS"
  printf 'Worktree: %s\n' "$wt"
  printf '只允许修改 Only-edit 中的路径。\n\n'
  if [[ "$FIX" -eq 1 && -f "$notes_file" ]]; then
    printf '上一轮审查 NOTES:\n\n'
    cat "$notes_file"
    printf '\n\n'
  fi
  printf 'Issue 正文:\n\n'
  cat "$WORKDIR/body.md"
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
  stop_issue "$reason" \
    "<!-- agent-pipeline:notice=${reason} -->" \
    "实现者进程退出码 ${invoke_rc}。流水线已停止，不会自动重试。日志: ${stdout_log}"
fi

git -C "$wt" add -A
git -C "$wt" reset -q -- .env .venv .agent-pipeline || true
if git -C "$wt" diff --cached --name-only | grep -E '(^|/)\.env$|(^|/)\.venv(/|$)' >/dev/null; then
  agent_pipeline_die "拒绝提交 .env 或 .venv"
fi
if git -C "$wt" diff --cached | grep -E 'sk-or-|gsk-|ak_|AIza|csk-|ghp_' >/dev/null; then
  agent_pipeline_die "拒绝提交看起来像 API key 的 diff"
fi
if ! git -C "$wt" diff --cached --quiet; then
  if ! git -C "$wt" config user.email >/dev/null || ! git -C "$wt" config user.name >/dev/null; then
    agent_pipeline_die "git 没有 user.name / user.email，无法代为实现者提交"
  fi
  git -C "$wt" commit -m "fix #${ISSUE}: ${short}"
fi

ahead=$(git -C "$wt" rev-list --count "origin/${base}..HEAD")
if [[ "$ahead" -eq 0 ]]; then
  stop_issue no_changes \
    "<!-- agent-pipeline:notice=no-changes sha=${body_sha} -->" \
    "实现者没有产生相对 origin/${base} 的新提交。流水线已停止。"
fi

git -C "$wt" diff --name-only "origin/${base}...HEAD" > "$WORKDIR/changed.txt"
only_result=$(agent_pipeline_py only-edit "$WORKDIR/only-edit.txt" "$WORKDIR/changed.txt")
only_status=$(printf '%s\n' "$only_result" | head -n 1)
only_bad=$(printf '%s\n' "$only_result" | tail -n +2)
if [[ "$only_status" == "fail" ]]; then
  stop_issue only_edit \
    "<!-- agent-pipeline:notice=only-edit sha=${body_sha} -->" \
    "这些文件不在 Only-edit 里，流水线没有 push: ${only_bad}"
fi

test_log="$AGENT_PIPELINE_STATE_DIR/reviews/issue-${ISSUE}.tests.log"
set +e
agent_pipeline_run_project_tests "$wt" "$test_log"
test_rc=$?
set -e
if [[ "$test_rc" -ne 0 ]]; then
  test_tail=$(tail -n 30 "$test_log" || true)
  stop_issue tests_failed \
    "<!-- agent-pipeline:notice=tests-failed sha=${body_sha} -->" \
    "开 PR 前本地测试失败（退出码 ${test_rc}）。流水线没有 push。日志尾部:

${test_tail}"
fi

git -C "$wt" push -u origin "HEAD:${branch}"
head_sha=$(git -C "$wt" rev-parse HEAD)

existing_pr=$(agent_pipeline_state_get "$STATE_FILE" pr)
if [[ "$FIX" -eq 1 && -n "$existing_pr" ]]; then
  pr_number="$existing_pr"
  agent_pipeline_comment_once pr "$pr_number" \
    "<!-- agent-pipeline:notice=fix-pushed sha=${head_sha} -->" \
    "修复轮次已推到 ${head_sha}。审查会在另一个进程里进行。"
else
  cat > "$WORKDIR/pr-body.md" <<EOF
Fixes #${ISSUE}

<!-- agent-pipeline:issue=${ISSUE} -->

## Summary

实现 Issue #${ISSUE}: ${title}

## Only-edit

$(cat "$WORKDIR/only-edit.txt")

本地测试在开 PR 前已通过。由 scripts/agent-implement.sh 打开。审查者在另一个进程里运行。

审查评论里的检查声明固定为这三行，没跑的写成 not run：

- unit
- console/SSE
- live provider
EOF
  gh pr create --base "$base" --head "$branch" --title "[agent] ${short}" --body-file "$WORKDIR/pr-body.md"
  pr_number=$(gh pr view "$branch" --json number --jq .number)
  agent_pipeline_comment_once issue "$ISSUE" \
    "<!-- agent-pipeline:notice=pr-opened ${pr_number} -->" \
    "实现者已打开 PR #${pr_number}。"
fi

agent_pipeline_state_put "$STATE_FILE" status pr_open
agent_pipeline_state_put "$STATE_FILE" pr "$pr_number"
agent_pipeline_state_put "$STATE_FILE" branch "$branch"
agent_pipeline_state_put "$STATE_FILE" base "$base"
agent_pipeline_state_put "$STATE_FILE" head_sha "$head_sha"
agent_pipeline_state_put "$STATE_FILE" last_reviewed_sha ""
agent_pipeline_state_put "$STATE_FILE" verdict ""
agent_pipeline_state_put "$STATE_FILE" local_tests pass
agent_pipeline_state_put "$STATE_FILE" only_edit "$only_status"
agent_pipeline_state_put "$STATE_FILE" checks_polls 0
agent_pipeline_state_put "$STATE_FILE" owner_pid ""
agent_pipeline_state_put "$STATE_FILE" reason ""
agent_pipeline_log "issue #$ISSUE -> PR #$pr_number ($head_sha)"
STARTED=0

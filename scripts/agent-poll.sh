#!/usr/bin/env bash
# 本机轮询。约定见 docs/agent-pipeline.md。
# 用法: scripts/agent-poll.sh [--once] [--interval SEC] [--dry-run] [--no-merge]
#
# 只处理带 ready 标签的打开 Issue。每一轮每个 Issue 只推进一步。
# 同一时间只跑一个实现者或审查者。Ctrl-C 结束。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=lib/agent-pipeline-common.sh
source "$SCRIPT_DIR/lib/agent-pipeline-common.sh"

usage() {
  cat <<'EOF'
用法: scripts/agent-poll.sh [--once] [--interval SEC] [--dry-run] [--no-merge]

前台轮询打开的、带 ready 标签的 Issue，以及本流水线打开的 PR。
没有公网 webhook。Cloud Agent 和 GitHub Actions 不在这个脚本里。

--once       只跑一轮
--interval   两轮之间的秒数，默认 60，也可用 AGENT_PIPELINE_INTERVAL
--dry-run    只读。不调用编码 agent，不开 PR，不合并
--no-merge   传给审查脚本，ACCEPT 后也不合并
EOF
}

ONCE=0
DRY=0
INTERVAL="${AGENT_PIPELINE_INTERVAL:-60}"
MERGE="${AGENT_PIPELINE_MERGE:-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --once)
      ONCE=1
      ;;
    --dry-run)
      DRY=1
      ;;
    --no-merge)
      MERGE=0
      ;;
    --interval)
      shift
      if [[ $# -lt 1 ]]; then
        agent_pipeline_die "--interval 需要一个秒数"
      fi
      INTERVAL="$1"
      ;;
    --*)
      agent_pipeline_die "未知参数: $1（试试 --help）"
      ;;
    *)
      agent_pipeline_die "多余参数: $1"
      ;;
  esac
  shift
done

case "$INTERVAL" in
  ""|*[!0-9]*)
    agent_pipeline_die "interval 必须是非负整数"
    ;;
esac

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
if [[ "$MERGE" != "1" ]]; then
  export AGENT_PIPELINE_MERGE=0
fi

LOCK_HELD=0
PRS_JSON=""
release_on_exit() {
  if [[ "$LOCK_HELD" -eq 1 ]]; then
    agent_pipeline_release_poll_lock
  fi
  if [[ "$DRY" -eq 1 && -n "$PRS_JSON" ]]; then
    rm -f "$PRS_JSON"
  fi
}
trap release_on_exit EXIT

if [[ "$DRY" -eq 0 ]]; then
  agent_pipeline_acquire_poll_lock
  LOCK_HELD=1
fi

# 打印两行：流水线 PR 编号、人工 PR 编号。没有则为空行。
classify_open_prs() {
  local issue="$1"
  local dest kind number pipeline="" human=""
  dest=$(mktemp)
  agent_pipeline_py match-prs "$PRS_JSON" "$issue" > "$dest"
  while IFS=$'\t' read -r kind number; do
    [[ -n "${kind:-}" ]] || continue
    if [[ "$kind" == "pipeline" && -z "$pipeline" ]]; then
      pipeline="$number"
    elif [[ "$kind" == "human" && -z "$human" ]]; then
      human="$number"
    fi
  done < "$dest"
  rm -f "$dest"
  printf '%s\n%s\n' "$pipeline" "$human"
}

process_issue() {
  local issue="$1"
  local state_file body_file body_sha status reason stored_sha pid alive flight
  local pr_lines pipeline_pr human_pr pr_kind action advanced
  local pr head_ref base_ref

  state_file=$(agent_pipeline_state_file "$issue")
  body_file=$(mktemp)
  gh issue view "$issue" --json body --jq .body > "$body_file"
  body_sha=$(agent_pipeline_hash_file "$body_file")
  rm -f "$body_file"

  status=$(agent_pipeline_state_get "$state_file" status)
  reason=$(agent_pipeline_state_get "$state_file" reason)
  stored_sha=$(agent_pipeline_state_get "$state_file" body_sha)
  pid=$(agent_pipeline_state_get "$state_file" owner_pid)
  if agent_pipeline_pid_alive "$pid"; then
    alive=1
  else
    alive=0
  fi
  flight=$(agent_pipeline_inflight "$status" "$alive")
  if [[ "$flight" == "busy" ]]; then
    agent_pipeline_log "issue #$issue 进行中 pid=$pid"
    return 0
  fi
  if [[ "$flight" == "crashed" ]]; then
    agent_pipeline_log "issue #$issue 上次进程已退出"
    if [[ "$DRY" -eq 1 ]]; then
      return 0
    fi
    agent_pipeline_state_put "$state_file" status stopped
    agent_pipeline_state_put "$state_file" reason crashed
    agent_pipeline_state_put "$state_file" owner_pid ""
    agent_pipeline_comment_once issue "$issue" \
      "<!-- agent-pipeline:notice=crashed -->" \
      "上次实现或审查进程已经不在。流水线停止。删掉 .agent-pipeline/issues/${issue} 才会再试。"
    return 0
  fi

  pr_lines=$(classify_open_prs "$issue")
  pipeline_pr=$(printf '%s\n' "$pr_lines" | sed -n '1p')
  human_pr=$(printf '%s\n' "$pr_lines" | sed -n '2p')
  if [[ -n "$pipeline_pr" ]]; then
    pr_kind="pipeline"
  elif [[ -n "$human_pr" ]]; then
    pr_kind="human"
  else
    pr_kind="none"
  fi

  action=$(agent_pipeline_issue_action "$status" "$reason" "$body_sha" "$stored_sha" "$pr_kind")
  agent_pipeline_log "issue #$issue 动作=$action 状态=${status:-new} pr=$pr_kind"
  advanced=0

  case "$action" in
    implement)
      advanced=1
      if ! run_implement "$issue" 0; then
        agent_pipeline_log "implement 失败: issue #$issue"
      fi
      ;;
    fix)
      advanced=1
      if ! run_implement "$issue" 1; then
        agent_pipeline_log "fix 失败: issue #$issue"
      fi
      ;;
    adopt)
      if [[ "$DRY" -eq 1 ]]; then
        agent_pipeline_log "dry-run: 将认领流水线 PR #$pipeline_pr 给 issue #$issue"
      else
        head_ref=$(gh pr view "$pipeline_pr" --json headRefName --jq .headRefName)
        base_ref=$(gh pr view "$pipeline_pr" --json baseRefName --jq .baseRefName)
        agent_pipeline_state_put "$state_file" status pr_open
        agent_pipeline_state_put "$state_file" pr "$pipeline_pr"
        agent_pipeline_state_put "$state_file" branch "$head_ref"
        agent_pipeline_state_put "$state_file" base "$base_ref"
        agent_pipeline_state_put "$state_file" body_sha "$body_sha"
        agent_pipeline_state_put "$state_file" fix_rounds 0
        agent_pipeline_state_put "$state_file" review_count 0
        agent_pipeline_state_put "$state_file" checks_polls 0
        agent_pipeline_state_put "$state_file" owner_pid ""
        agent_pipeline_state_put "$state_file" reason ""
        agent_pipeline_state_put "$state_file" verdict ""
        agent_pipeline_state_put "$state_file" last_reviewed_sha ""
      fi
      ;;
    block_human)
      if [[ "$DRY" -eq 1 ]]; then
        agent_pipeline_log "dry-run: issue #$issue 已有非流水线 PR #$human_pr"
      else
        agent_pipeline_state_put "$state_file" status stopped
        agent_pipeline_state_put "$state_file" reason human_pr
        agent_pipeline_state_put "$state_file" body_sha "$body_sha"
        agent_pipeline_state_put "$state_file" owner_pid ""
        agent_pipeline_comment_once issue "$issue" \
          "<!-- agent-pipeline:notice=human-pr ${human_pr} -->" \
          "已有 PR #${human_pr} 关联了这个 Issue，但它不是流水线 PR。流水线停止，避免再开一个。"
      fi
      ;;
    skip)
      ;;
  esac

  if [[ "$advanced" -eq 1 ]]; then
    return 0
  fi
  if [[ "$DRY" -eq 1 && "$action" == "adopt" ]]; then
    return 0
  fi

  status=$(agent_pipeline_state_get "$state_file" status)
  pr=$(agent_pipeline_state_get "$state_file" pr)
  if [[ -z "$pr" && -n "$pipeline_pr" ]]; then
    pr="$pipeline_pr"
  fi
  if [[ "$status" == "pr_open" || "$status" == "awaiting_checks" ]]; then
    if [[ -z "$pr" ]]; then
      return 0
    fi
    if ! run_review "$pr"; then
      agent_pipeline_log "review 失败: PR #$pr"
    fi
  fi
}

run_implement() {
  local issue="$1" fix="$2"
  if [[ "$DRY" -eq 1 && "$fix" -eq 1 ]]; then
    "$SCRIPT_DIR/agent-implement.sh" "$issue" --fix --dry-run
  elif [[ "$DRY" -eq 1 ]]; then
    "$SCRIPT_DIR/agent-implement.sh" "$issue" --dry-run
  elif [[ "$fix" -eq 1 ]]; then
    "$SCRIPT_DIR/agent-implement.sh" "$issue" --fix
  else
    "$SCRIPT_DIR/agent-implement.sh" "$issue"
  fi
}

run_review() {
  local pr="$1"
  if [[ "$DRY" -eq 1 && "$MERGE" != "1" ]]; then
    "$SCRIPT_DIR/agent-review.sh" "$pr" --dry-run --no-merge
  elif [[ "$DRY" -eq 1 ]]; then
    "$SCRIPT_DIR/agent-review.sh" "$pr" --dry-run
  elif [[ "$MERGE" != "1" ]]; then
    "$SCRIPT_DIR/agent-review.sh" "$pr" --no-merge
  else
    "$SCRIPT_DIR/agent-review.sh" "$pr"
  fi
}

poll_once() {
  if ! agent_pipeline_label_exists "ready"; then
    agent_pipeline_die "标签 ready 不存在。本仓库应已有它（可以由agent接管开发的issues）。缺失时执行: gh label create ready --description \"可以由agent接管开发的issues\" --color 9d88c3"
  fi
  local issues_raw sorted issue
  issues_raw=$(gh issue list --label "ready" --state open --limit 50 --json number --jq '.[].number')
  if [[ "$DRY" -eq 1 ]]; then
    PRS_JSON=$(mktemp)
  else
    mkdir -p "$AGENT_PIPELINE_STATE_DIR"
    PRS_JSON="$AGENT_PIPELINE_STATE_DIR/poll-prs.json"
  fi
  agent_pipeline_fetch_open_prs_json "$PRS_JSON"
  sorted=$(printf '%s\n' "$issues_raw" | sed '/^$/d' | sort -n)
  while IFS= read -r issue; do
    [[ -n "$issue" ]] || continue
    process_issue "$issue"
  done <<EOF
$sorted
EOF
}

while true; do
  poll_once
  if [[ "$ONCE" -eq 1 ]]; then
    break
  fi
  agent_pipeline_log "下一轮在 ${INTERVAL}s 后"
  sleep "$INTERVAL"
done

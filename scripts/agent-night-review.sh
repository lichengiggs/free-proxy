#!/usr/bin/env bash
# 本机夜审。不调用编码 agent，不改 LESSONS.md，不合并。
# 用法:
#   scripts/agent-night-review.sh
#   scripts/agent-night-review.sh --check --lessons LESSONS.md --date 2026-10-27
#   scripts/agent-night-review.sh --packet --date 2026-10-27
#
# 默认先核对错题本，再把当天证据写成提示词，留给人交给 agent。

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SCRIPT_DIR/.." && pwd)
# shellcheck source=lib/agent-pipeline-common.sh
source "$SCRIPT_DIR/lib/agent-pipeline-common.sh"

usage() {
  cat <<'EOF'
用法: scripts/agent-night-review.sh [--check] [--packet] [--lessons 文件] [--date YYYY-MM-DD]

核对 LESSONS.md，并写出当天的证据包。不调用 agent，不改仓库。

不带 --check / --packet 时，两件事都做。
--check    打印仍有效条目里该升格、该归档或格式不对的行。有这类行时退出码为 2
--packet   把夜审说明、机械检查和当天 git 记录写到 .agent-pipeline/night-review/<date>.md
--lessons  要核对的错题本，默认仓库根目录的 LESSONS.md
--date     日历日，默认本机当天。归档按这一天往前数 90 天
EOF
}

CHECK=0
PACKET=0
LESSONS=""
DATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --check)
      CHECK=1
      ;;
    --packet)
      PACKET=1
      ;;
    --lessons)
      shift
      LESSONS="${1:-}"
      if [[ -z "$LESSONS" ]]; then
        agent_pipeline_die "--lessons 需要文件路径"
      fi
      ;;
    --date)
      shift
      DATE="${1:-}"
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

if [[ "$CHECK" -eq 0 && "$PACKET" -eq 0 ]]; then
  CHECK=1
  PACKET=1
fi

if [[ -z "$DATE" ]]; then
  DATE=$(date +%Y-%m-%d)
fi
case "$DATE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
    ;;
  *)
    agent_pipeline_die "--date 要用 YYYY-MM-DD，收到: $DATE"
    ;;
esac

if [[ -z "$LESSONS" ]]; then
  LESSONS="$REPO/LESSONS.md"
fi

NEXT_DATE=$(python3 - "$DATE" <<'PY'
import datetime, sys
day = datetime.date.fromisoformat(sys.argv[1])
print(day + datetime.timedelta(days=1))
PY
)

fail=0
status=$(agent_pipeline_py lesson-status "$LESSONS" "$DATE")

if [[ "$CHECK" -eq 1 ]]; then
  if [[ -z "$status" ]]; then
    printf 'LESSONS.md 没有需要升格或归档的条目\n'
  else
    printf '%s\n' "$status"
    if printf '%s\n' "$status" | grep -E '^(promote|archive|bad)[[:space:]]' >/dev/null; then
      fail=1
    fi
  fi
fi

if [[ "$PACKET" -eq 1 ]]; then
  if ! git -C "$REPO" rev-parse --show-toplevel >/dev/null 2>&1; then
    agent_pipeline_die "写证据包需要在 git 工作区里运行"
  fi
  agent_pipeline_init "$REPO"
  packet_dir="$AGENT_PIPELINE_STATE_DIR/night-review"
  mkdir -p "$packet_dir"
  packet="$packet_dir/${DATE}.md"
  {
    printf '# 夜审证据 %s\n\n' "$DATE"
    printf '这份文件由 scripts/agent-night-review.sh 生成。它不修改仓库。\n'
    printf '人把这份证据交给编码 agent 之后，才允许改 LESSONS.md；升格时才改 AGENTS.md。\n\n'
    cat "$REPO/docs/agent-pipeline/night-review.md"
    printf '\n\n## 机械检查\n\n'
    if [[ -n "$status" ]]; then
      printf '%s\n' "$status"
    else
      printf '没有需要升格或归档的条目。\n'
    fi
    printf '\n## 当天提交\n\n'
    git -C "$REPO" log \
      --since="${DATE} 00:00" \
      --until="${NEXT_DATE} 00:00" \
      --pretty=format:'%h %ad %s' \
      --date=short || true
    printf '\n\n## 本机审查记录\n\n'
    if [[ -d "$AGENT_PIPELINE_STATE_DIR/reviews" ]]; then
      find "$AGENT_PIPELINE_STATE_DIR/reviews" -type f \( -name '*.verdict' -o -name '*.tests.log' \) -print
    else
      printf '没有 reviews 目录。\n'
    fi
    printf '\n'
    if [[ -d "$AGENT_PIPELINE_STATE_DIR/issues" ]]; then
      find "$AGENT_PIPELINE_STATE_DIR/issues" -type f -name '*.notes' -print
    fi
    printf '\n'
  } > "$packet"
  printf '证据包: %s\n' "$packet"
fi

if [[ "$fail" -ne 0 ]]; then
  exit 2
fi

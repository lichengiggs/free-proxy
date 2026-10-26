#!/usr/bin/env bash
# Shared helpers for the local agent pipeline.
# Source this file. Do not execute it.
#
# Assumptions:
# - bash 3.2 or newer (macOS /bin/bash is enough). No associative arrays.
# - git remote for the GitHub repo is named origin.
# - python3 parses GitHub JSON and issue sections. gh --jq is not required.
# - State lives in <main-checkout>/.agent-pipeline and is gitignored.
# - Implementer and reviewer are separate processes. This file has no session.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' "source this file from scripts/agent-*.sh" >&2
  exit 1
fi

agent_pipeline_die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

agent_pipeline_init() {
  local top="$1"
  local common
  if [[ -z "$top" ]]; then
    top=$(git rev-parse --show-toplevel)
  fi
  if ! common=$(git -C "$top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null); then
    common=$(git -C "$top" rev-parse --git-common-dir)
    if [[ "$common" != /* ]]; then
      common="$top/$common"
    fi
    common=$(cd "$common" && pwd)
  fi
  AGENT_PIPELINE_MAIN_ROOT=$(cd "$common/.." && pwd)
  if [[ -z "${AGENT_PIPELINE_STATE_DIR:-}" ]]; then
    AGENT_PIPELINE_STATE_DIR="$AGENT_PIPELINE_MAIN_ROOT/.agent-pipeline"
  fi
  AGENT_PIPELINE_MAX_FIX_ROUNDS="${AGENT_PIPELINE_MAX_FIX_ROUNDS:-2}"
  AGENT_PIPELINE_MAX_REVIEWS="${AGENT_PIPELINE_MAX_REVIEWS:-3}"
  AGENT_PIPELINE_CHECKS_MAX_POLLS="${AGENT_PIPELINE_CHECKS_MAX_POLLS:-10}"
  export AGENT_PIPELINE_MAIN_ROOT AGENT_PIPELINE_STATE_DIR
  export AGENT_PIPELINE_MAX_FIX_ROUNDS AGENT_PIPELINE_MAX_REVIEWS AGENT_PIPELINE_CHECKS_MAX_POLLS
}

agent_pipeline_log() {
  local stamp msg
  stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  msg="$*"
  printf '%s %s\n' "$stamp" "$msg" >&2
  if [[ "${AGENT_PIPELINE_DRY_RUN:-0}" == "1" ]]; then
    return 0
  fi
  if [[ -n "${AGENT_PIPELINE_STATE_DIR:-}" ]]; then
    mkdir -p "$AGENT_PIPELINE_STATE_DIR" 2>/dev/null || return 0
    printf '%s %s\n' "$stamp" "$msg" >> "$AGENT_PIPELINE_STATE_DIR/pipeline.log" || true
  fi
}

agent_pipeline_require_number() {
  case "$1" in
    ""|*[!0-9]*)
      agent_pipeline_die "expected a positive integer, got: ${1:-<empty>}"
      ;;
  esac
}

agent_pipeline_require_tools() {
  local missing=0
  local tool
  for tool in git gh python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      printf 'error: required tool not on PATH: %s\n' "$tool" >&2
      missing=1
    fi
  done
  if [[ "$missing" -ne 0 ]]; then
    exit 1
  fi
}

agent_pipeline_hash_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    agent_pipeline_die "need shasum or sha256sum to hash the issue body"
  fi
}

agent_pipeline_state_file() {
  printf '%s/issues/%s\n' "$AGENT_PIPELINE_STATE_DIR" "$1"
}

agent_pipeline_state_get() {
  local file="$1" key="$2" line
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      "$key"=*)
        printf '%s\n' "${line#"$key"=}"
        return 0
        ;;
    esac
  done < "$file"
}

agent_pipeline_state_put() {
  local file="$1" key="$2" value="$3"
  local dir tmp found line
  case "$key" in
    ""|*[!a-z0-9_]*)
      agent_pipeline_die "bad state key: $key"
      ;;
  esac
  case "$value" in
    *$'\n'*)
      agent_pipeline_die "state value for $key contains a newline"
      ;;
  esac
  dir=$(dirname "$file")
  mkdir -p "$dir"
  tmp=$(mktemp "$dir/.state.XXXXXX")
  found=0
  if [[ -f "$file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      case "$line" in
        "")
          ;;
        "$key"=*)
          printf '%s=%s\n' "$key" "$value" >> "$tmp"
          found=1
          ;;
        *)
          printf '%s\n' "$line" >> "$tmp"
          ;;
      esac
    done < "$file"
  fi
  if [[ "$found" -eq 0 ]]; then
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$file"
}

# Text and GitHub JSON helpers. The script is stdin; arguments are argv.
agent_pipeline_py() {
  python3 - "$@" <<'PY'
import json, os, re, sys

def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read().replace("\r\n", "\n").replace("\r", "\n")

def heading_sections(text):
    current = None
    found = {}
    for line in text.split("\n"):
        match = re.match(r"^##[ \t]+(.+?)[ \t]*$", line)
        if match:
            current = match.group(1)
            found.setdefault(current, [])
            continue
        if current is not None:
            found[current].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}

def strip_comments(text):
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)

def path_tokens(text):
    tokens = []
    for raw in strip_comments(text).splitlines():
        line = raw.strip()
        line = re.sub(r"^[-*][ \t]+", "", line)
        line = re.sub(r"^[0-9]+\.[ \t]+", "", line)
        if len(line) >= 2 and line.startswith("`") and line.endswith("`"):
            line = line[1:-1].strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^[A-Za-z0-9_./@*+-]+$", line):
            tokens.append(line)
    return tokens

def path_match(file_path, pattern):
    if pattern.endswith("/**"):
        pattern = pattern[:-3]
    pattern = pattern.rstrip("/")
    if not pattern:
        return False
    if any(ch in pattern for ch in "*?"):
        import fnmatch
        return fnmatch.fnmatch(file_path, pattern)
    return file_path == pattern or file_path.startswith(pattern + "/")

def cmd_missing_sections(path):
    sections = heading_sections(read_text(path))
    missing = []
    for name in ("Goal", "Acceptance", "Only-edit"):
        body = strip_comments(sections.get(name, ""))
        if not body.strip():
            missing.append(name)
    if missing:
        sys.stdout.write("\n".join(missing))
        return 1
    return 0

def cmd_extract(path, heading):
    sections = heading_sections(read_text(path))
    sys.stdout.write(sections.get(heading, ""))
    return 0

def cmd_only_edit(section_path, files_path):
    tokens = path_tokens(read_text(section_path))
    files = [line.strip() for line in read_text(files_path).splitlines() if line.strip()]
    if not tokens:
        sys.stdout.write("skip\n")
        return 0
    bad = [item for item in files if not any(path_match(item, token) for token in tokens)]
    if bad:
        sys.stdout.write("fail\n" + "\n".join(bad))
        return 0
    sys.stdout.write("pass\n")
    return 0

def cmd_verdict(path):
    if not os.path.isfile(path):
        return 1
    for raw in read_text(path).splitlines():
        match = re.match(r"^VERDICT:[ \t]*(ACCEPT|REJECT|FIX)$", raw.strip())
        if match:
            sys.stdout.write(match.group(1))
            return 0
    return 1

def cmd_notes(path):
    if not os.path.isfile(path):
        return 0
    started = False
    notes = []
    for raw in read_text(path).splitlines():
        if not started:
            if re.match(r"^VERDICT:[ \t]*(ACCEPT|REJECT|FIX)$", raw.strip()):
                started = True
            continue
        match = re.match(r"^NOTES:[ \t]?(.*)$", raw)
        notes.append(match.group(1) if match else raw)
    text = "\n".join(notes).strip()
    if text:
        sys.stdout.write(text)
    return 0

def cmd_match_prs(path, issue):
    data = json.loads(read_text(path) or "[]")
    marker = re.compile(r"agent-pipeline:issue=(\d+)")
    fixes = re.compile(
        r"(?i)(?:^|[\s(])(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)\b"
    )
    issue = str(issue)
    for pr in data:
        body = pr.get("body") or ""
        title = pr.get("title") or ""
        blob = title + "\n" + body
        number = pr.get("number")
        found = marker.search(blob)
        if found and found.group(1) == issue:
            sys.stdout.write("pipeline\t%s\n" % number)
            continue
        if any(match.group(1) == issue for match in fixes.finditer(blob)):
            sys.stdout.write("human\t%s\n" % number)
    return 0

def cmd_classify_checks(path):
    raw = read_text(path).strip() if os.path.isfile(path) else ""
    if not raw:
        sys.stdout.write("none")
        return 0
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        sys.stdout.write("none")
        return 0
    buckets = []
    for item in data:
        buckets.append(str(item.get("bucket") or "").lower())
    if any(bucket in ("fail", "failure", "cancel", "cancelled", "canceled") for bucket in buckets):
        sys.stdout.write("fail")
    elif any(bucket == "pending" for bucket in buckets):
        sys.stdout.write("pending")
    else:
        sys.stdout.write("pass")
    return 0

def cmd_json_str(path, key):
    data = json.loads(read_text(path))
    value = data
    for part in key.split("."):
        if isinstance(value, dict):
            value = value.get(part, "")
        else:
            value = ""
            break
    if value is None:
        value = ""
    if isinstance(value, (dict, list)):
        sys.stdout.write(json.dumps(value))
    else:
        sys.stdout.write(str(value))
    return 0

def cmd_has_label(path, label):
    data = json.loads(read_text(path))
    names = []
    for item in data.get("labels") or []:
        if isinstance(item, dict):
            names.append(item.get("name", ""))
        else:
            names.append(str(item))
    return 0 if label in names else 1

def main(argv):
    if not argv:
        return 2
    cmd, args = argv[0], argv[1:]
    commands = {
        "missing-sections": (cmd_missing_sections, 1),
        "extract": (cmd_extract, 2),
        "only-edit": (cmd_only_edit, 2),
        "verdict": (cmd_verdict, 1),
        "notes": (cmd_notes, 1),
        "match-prs": (cmd_match_prs, 2),
        "classify-checks": (cmd_classify_checks, 1),
        "json-str": (cmd_json_str, 2),
        "has-label": (cmd_has_label, 2),
    }
    if cmd not in commands:
        sys.stderr.write("unknown helper: %s\n" % cmd)
        return 2
    func, nargs = commands[cmd]
    if len(args) != nargs:
        sys.stderr.write("%s expects %s args\n" % (cmd, nargs))
        return 2
    return func(*args)

raise SystemExit(main(sys.argv[1:]))
PY
}

# Poll decision: implement | fix | adopt | block_human | skip
# pr_kind is none, pipeline, or human.
agent_pipeline_issue_action() {
  local status="$1" reason="$2" body_sha="$3" stored_sha="$4" pr_kind="$5"
  case "$status" in
    "")
      case "$pr_kind" in
        none) printf '%s\n' implement ;;
        pipeline) printf '%s\n' adopt ;;
        human) printf '%s\n' block_human ;;
        *) printf '%s\n' skip ;;
      esac
      ;;
    needs_fix)
      printf '%s\n' fix
      ;;
    stopped)
      if [[ "$reason" == "malformed" && -n "$body_sha" && "$body_sha" != "$stored_sha" ]]; then
        printf '%s\n' implement
      else
        printf '%s\n' skip
      fi
      ;;
    *)
      printf '%s\n' skip
      ;;
  esac
}

# busy | crashed | free
agent_pipeline_inflight() {
  local status="$1" alive="$2"
  case "$status" in
    implementing|reviewing)
      if [[ "$alive" == "1" ]]; then
        printf '%s\n' busy
      else
        printf '%s\n' crashed
      fi
      ;;
    *)
      printf '%s\n' free
      ;;
  esac
}

# accept | reject | fix | reject_exhausted | invalid
agent_pipeline_apply_verdict() {
  local verdict="$1" rounds="$2" max_rounds="$3"
  case "$verdict" in
    ACCEPT)
      printf '%s\n' accept
      ;;
    REJECT)
      printf '%s\n' reject
      ;;
    FIX)
      if [[ "$rounds" -ge "$max_rounds" ]]; then
        printf '%s\n' reject_exhausted
      else
        printf '%s\n' fix
      fi
      ;;
    *)
      printf '%s\n' invalid
      ;;
  esac
}

# review | recheck | cap | skip
agent_pipeline_review_action() {
  local status="$1" head="$2" last="$3" review_count="$4" max_reviews="$5"
  case "$status" in
    awaiting_checks)
      if [[ -n "$head" && "$head" != "$last" ]]; then
        if [[ "$review_count" -ge "$max_reviews" ]]; then
          printf '%s\n' cap
        else
          printf '%s\n' review
        fi
      else
        printf '%s\n' recheck
      fi
      ;;
    pr_open)
      if [[ "$review_count" -ge "$max_reviews" ]]; then
        printf '%s\n' cap
      elif [[ -n "$last" && "$head" == "$last" ]]; then
        printf '%s\n' skip
      else
        printf '%s\n' review
      fi
      ;;
    *)
      printf '%s\n' skip
      ;;
  esac
}

# merge | wait | stop | ignore
# only_edit is pass, skip, or fail. skip means Only-edit had no path tokens.
agent_pipeline_merge_gate() {
  local action="$1" local_tests="$2" remote="$3" only_edit="$4"
  if [[ "$action" != "accept" ]]; then
    printf '%s\n' ignore
    return 0
  fi
  if [[ "$local_tests" != "pass" || "$only_edit" == "fail" ]]; then
    printf '%s\n' stop
    return 0
  fi
  case "$remote" in
    pass|none)
      printf '%s\n' merge
      ;;
    pending)
      printf '%s\n' wait
      ;;
    *)
      printf '%s\n' stop
      ;;
  esac
}

# wait | timeout
agent_pipeline_checks_wait() {
  local polls="$1" max_polls="$2"
  if [[ "$polls" -ge "$max_polls" ]]; then
    printf '%s\n' timeout
  else
    printf '%s\n' wait
  fi
}

agent_pipeline_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

agent_pipeline_default_branch() {
  local name
  if name=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null); then
    if [[ -n "$name" && "$name" != "null" ]]; then
      printf '%s\n' "$name"
      return 0
    fi
  fi
  name=$(git -C "$AGENT_PIPELINE_MAIN_ROOT" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)
  name=${name#origin/}
  if [[ -z "$name" ]]; then
    agent_pipeline_die "could not determine the default branch"
  fi
  printf '%s\n' "$name"
}

agent_pipeline_acquire_poll_lock() {
  local dir="$AGENT_PIPELINE_STATE_DIR/poll.lockdir"
  mkdir -p "$AGENT_PIPELINE_STATE_DIR"
  if mkdir "$dir" 2>/dev/null; then
    printf '%s\n' "$$" > "$dir/pid"
    return 0
  fi
  local pid
  pid=$(cat "$dir/pid" 2>/dev/null || true)
  if agent_pipeline_pid_alive "$pid"; then
    agent_pipeline_die "another agent-poll is running (pid $pid)"
  fi
  rm -rf "$dir"
  mkdir "$dir"
  printf '%s\n' "$$" > "$dir/pid"
}

agent_pipeline_release_poll_lock() {
  if [[ -n "${AGENT_PIPELINE_STATE_DIR:-}" ]]; then
    rm -rf "$AGENT_PIPELINE_STATE_DIR/poll.lockdir"
  fi
}

agent_pipeline_run_timeout() {
  local secs="${AGENT_TIMEOUT:-1800}"
  if [[ "$secs" == "0" ]] || ! command -v timeout >/dev/null 2>&1; then
    if [[ "$secs" != "0" ]] && ! command -v timeout >/dev/null 2>&1; then
      agent_pipeline_log "timeout(1) is not installed; running the agent without a time limit"
    fi
    "$@"
    return
  fi
  timeout "$secs" "$@"
}

# Invoke the local coding agent in workdir. stdout is copied to stdout_log.
#   agent -p --trust --force "<prompt>"      headless Cursor agent; default
#   opencode run --format json "<prompt>"    non-interactive; do not open the TUI
# A new worktree is untrusted. --trust --force keeps the headless agent from
# stopping on a trust or approval prompt. Set AGENT_BIN=opencode to use opencode.
# If the prompt is too long for argv, set AGENT_PROMPT_VIA=stdin.
# Optional model pin: AGENT_MODEL. This does not default to free-proxy/auto.
agent_pipeline_invoke() {
  local workdir="$1" prompt_file="$2" stdout_log="$3"
  local bin="${AGENT_BIN:-agent}"
  local base prompt
  if [[ "${AGENT_PIPELINE_DRY_RUN:-0}" == "1" ]]; then
    agent_pipeline_log "dry-run: not invoking $bin (prompt $prompt_file)"
    return 0
  fi
  if ! command -v "$bin" >/dev/null 2>&1; then
    agent_pipeline_die "agent binary not on PATH: $bin. Set AGENT_BIN to opencode or agent."
  fi
  base=$(basename "$bin")
  mkdir -p "$(dirname "$stdout_log")"
  if [[ "${AGENT_PROMPT_VIA:-arg}" != "stdin" ]]; then
    prompt=$(cat "$prompt_file")
  fi
  case "$base" in
    opencode)
      if [[ -n "${AGENT_MODEL:-}" && "${AGENT_PROMPT_VIA:-arg}" == "stdin" ]]; then
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" run --format json -m "$AGENT_MODEL") < "$prompt_file" | tee "$stdout_log"
      elif [[ -n "${AGENT_MODEL:-}" ]]; then
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" run --format json -m "$AGENT_MODEL" "$prompt") | tee "$stdout_log"
      elif [[ "${AGENT_PROMPT_VIA:-arg}" == "stdin" ]]; then
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" run --format json) < "$prompt_file" | tee "$stdout_log"
      else
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" run --format json "$prompt") | tee "$stdout_log"
      fi
      ;;
    agent)
      local -a agent_args=(-p --trust --force)
      if [[ -n "${AGENT_MODEL:-}" ]]; then
        agent_args+=(--model "$AGENT_MODEL")
      fi
      if [[ "${AGENT_PROMPT_VIA:-arg}" == "stdin" ]]; then
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" "${agent_args[@]}") < "$prompt_file" | tee "$stdout_log"
      else
        (cd "$workdir" && agent_pipeline_run_timeout "$bin" "${agent_args[@]}" "$prompt") | tee "$stdout_log"
      fi
      ;;
    *)
      agent_pipeline_die "unsupported AGENT_BIN '$base'. Expected opencode or agent. Edit agent_pipeline_invoke in scripts/lib/agent-pipeline-common.sh."
      ;;
  esac
}

agent_pipeline_run_project_tests() {
  local wt="$1" log="$2"
  mkdir -p "$(dirname "$log")"
  if [[ ! -d "$wt/python_scripts/tests" ]]; then
    printf '%s\n' "no python_scripts/tests directory; local test gate skipped" | tee "$log"
    return 0
  fi
  # TODO: other stacks can add a command here. This repo's agreed check is unittest.
  if command -v uv >/dev/null 2>&1; then
    (cd "$wt" && uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py') >"$log" 2>&1
  else
    (cd "$wt" && python3 -m unittest discover -s python_scripts/tests -p 'test_*.py') >"$log" 2>&1
  fi
}

agent_pipeline_remove_worktree() {
  local wt="$1"
  if [[ -z "$wt" || ! -d "$wt" ]]; then
    return 0
  fi
  git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree remove --force "$wt" || rm -rf "$wt"
  git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree prune || true
}

agent_pipeline_branch_exists_local() {
  git -C "$AGENT_PIPELINE_MAIN_ROOT" show-ref --verify --quiet "refs/heads/$1"
}

agent_pipeline_branch_exists_remote() {
  git -C "$AGENT_PIPELINE_MAIN_ROOT" ls-remote --exit-code --heads origin "$1" >/dev/null 2>&1
}

agent_pipeline_prepare_new_worktree() {
  local wt="$1" branch="$2" base="$3"
  mkdir -p "$(dirname "$wt")"
  agent_pipeline_remove_worktree "$wt"
  git -C "$AGENT_PIPELINE_MAIN_ROOT" fetch origin "$base"
  git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree add -b "$branch" "$wt" "origin/$base"
}

# 审查用。detach 到指定 SHA，避免和实现者 worktree 抢同一个分支。
agent_pipeline_prepare_detached_worktree() {
  local wt="$1" sha="$2"
  mkdir -p "$(dirname "$wt")"
  agent_pipeline_remove_worktree "$wt"
  git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree add --detach "$wt" "$sha"
}

agent_pipeline_prepare_existing_worktree() {
  local wt="$1" branch="$2"
  mkdir -p "$(dirname "$wt")"
  agent_pipeline_remove_worktree "$wt"
  git -C "$AGENT_PIPELINE_MAIN_ROOT" fetch origin "$branch"
  if agent_pipeline_branch_exists_local "$branch"; then
    git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree add "$wt" "$branch"
    git -C "$wt" merge --ff-only "origin/$branch"
  else
    git -C "$AGENT_PIPELINE_MAIN_ROOT" worktree add -b "$branch" --track "$wt" "origin/$branch"
  fi
}

agent_pipeline_comment_once() {
  local kind="$1" number="$2" marker="$3" body="$4"
  local existing payload
  if [[ "${AGENT_PIPELINE_DRY_RUN:-0}" == "1" ]]; then
    agent_pipeline_log "dry-run: would comment on $kind #$number ($marker)"
    return 0
  fi
  if [[ "$kind" == "issue" ]]; then
    existing=$(gh issue view "$number" --json comments --jq '.comments[].body')
  else
    existing=$(gh pr view "$number" --json comments --jq '.comments[].body')
  fi
  case "$existing" in
    *"$marker"*)
      agent_pipeline_log "notice already posted ($marker)"
      return 0
      ;;
  esac
  payload="${body}

${marker}"
  if [[ "$kind" == "issue" ]]; then
    gh issue comment "$number" --body "$payload"
  else
    gh pr comment "$number" --body "$payload"
  fi
}

agent_pipeline_label_exists() {
  local name
  name=$(gh label list --search "$1" --limit 50 --json name --jq '.[] | select(.name=="'"$1"'") | .name' || true)
  [[ "$name" == "$1" ]]
}

agent_pipeline_fetch_open_prs_json() {
  local dest="$1"
  gh pr list --state open --limit 100 --json number,title,body > "$dest"
}

agent_pipeline_classify_remote_checks() {
  local pr="$1" dest="$2" err="$3"
  local rc
  set +e
  gh pr checks "$pr" --json bucket,name,state >"$dest" 2>"$err"
  rc=$?
  set -e
  # pending checks can exit 8 and still print JSON. Classify the file when it exists.
  if [[ -s "$dest" ]]; then
    agent_pipeline_py classify-checks "$dest"
    return 0
  fi
  if grep -q "no checks reported" "$err"; then
    printf '%s' none
    return 0
  fi
  agent_pipeline_log "gh pr checks failed for #$pr (exit $rc)"
  printf '%s' fail
}

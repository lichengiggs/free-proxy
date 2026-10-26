# 本地 agent 流水线

这是个人仓库用的本地脚手架，不改变 free-proxy 的运行行为。

人只做一件事：写好 GitHub Issue，加上标签 `ready`。之后由这台 Mac 上的脚本调用本地编码 CLI（`opencode` 或 `agent -p`）和 `gh`，完成实现、开 PR、审查、合并。

审查者给出 `ACCEPT`，并且约定检查是绿的，脚本就 squash 合并、关闭 Issue、删除分支。自动合并有风险，这个仓库的主人接受这个风险。

本阶段不做 Cloud Agent、GitHub Actions，也不做公网 webhook。编排方式是本机前台轮询。

触发标签是仓库里现成的 `ready`（可以由agent接管开发的issues）。正文写完再打上它。

## 阶段

```text
人写好 Goal / Acceptance / Only-edit
        |
        |  打上标签 ready
        v
scripts/agent-poll.sh          本机前台循环，不需要 webhook
        |
        |  每个 Issue 每一轮只推进一步，同一时间只跑一个 agent
        v
实现者 A                       scripts/agent-implement.sh
  新建 worktree，分支 agent/fix-<issue>
  独立进程里的编码 agent
  跑本地测试
  gh pr create（正文关联这个 Issue）
        |
        v
审查者 B                       scripts/agent-review.sh
  另一个进程，另一份全新 worktree
  不接收实现者的对话记录
  判断依据 = 测试日志 + diff 是否越出 Only-edit
        |
        +-- ACCEPT 且检查通过 --> gh pr merge --squash
        |                         关闭 Issue，删除分支
        +-- FIX 且还有修复轮次 --> 实现者 A 在同一分支上再改
        +-- 已经用完 2 轮 FIX   --> 当成 REJECT，停止
        +-- REJECT              --> 评论后停止
```

长的 agent 调用会挡住这一轮轮询。v1 不会并行跑两个 agent。

## Issue 约定

这个仓库已经有 `ready`。fork 里如果缺这个标签，按原样补上：

```bash
gh label create ready \
  --description "可以由agent接管开发的issues" \
  --color 9d88c3
```

Issue 必须是打开状态，并且包含这三个标题，大小写和连字符都要一致：

- `## Goal`
- `## Acceptance`
- `## Only-edit`

每一节都要有正文。只剩 HTML 注释不算有正文。缺节或空节时，流水线评论一次然后停止，不会启动实现者。

`Only-edit` 每行写一个允许修改的路径或 glob。带空格的行当作说明，不当作路径。脚本按下面的方式做机械检查：

- `python_scripts/service.py`：这个文件
- `python_scripts` 或 `python_scripts/`：这个目录以及下面的文件
- 以 `/**` 结尾：目录前缀
- `*` 和 `?`：glob，`*` 可以跨 `/`

如果 `Only-edit` 里没有像路径的行，脚本不去猜。审查者根据那段说明判断范围。

正文模板在 [`.github/ISSUE_TEMPLATE/agent-fix.md`](../.github/ISSUE_TEMPLATE/agent-fix.md)。模板不会自动加上 `ready`。正文写完再打这个标签。

## ACCEPT、REJECT、FIX

审查者只写裁决文件，不合并。

| 裁决 | 含义 | 脚本做什么 |
|---|---|---|
| `ACCEPT` | 满足 Acceptance，diff 在 Only-edit 内，测试日志是绿的。 | 本地测试通过、Only-edit 机械检查通过或跳过、GitHub checks 全绿或根本没有 checks 时，才 squash 合并。 |
| `FIX` | 还可以用一轮有限的修改补上。`NOTES` 写清要改什么。 | 在同一分支上再跑实现者，最多 2 轮。 |
| `REJECT` | 不要再自动改。 | 在 PR 上评论并停止。PR 和 Issue 保持打开。 |

模型说了 `ACCEPT`，但测试是红的、机械检查越界、或 GitHub checks 失败：不合并，也不会悄悄再开一轮修复。评论后停止。

GitHub checks 还在跑时，后续轮询继续等（默认 10 轮）。head SHA 没变就不再叫审查者。head 变了，原来的 `ACCEPT` 作废，在审查次数上限内重新审查。

## 不会无限重试

| 情况 | 结果 | 会不会自动再来 |
|---|---|---|
| 缺少 Goal、Acceptance 或 Only-edit | 评论，停止（`malformed`） | 只有 Issue 正文哈希变了才会再看一次 |
| 实现者没有产生提交 | 评论，停止 | 否 |
| diff 超出 Only-edit | 评论，停止 | 否 |
| 开 PR 前本地测试失败 | 评论，停止 | 否 |
| 审查者给出 FIX | 再实现一轮 | 最多 2 轮 |
| 2 轮 FIX 之后又是 FIX | 强制 REJECT，停止 | 否 |
| 审查者给出 REJECT | 评论，停止 | 否 |
| ACCEPT 但测试或 Only-edit 失败 | 不合并，停止 | 否 |
| ACCEPT 且 GitHub checks 还在跑 | 等待，不重新审查 | 到轮询上限后停止 |
| ACCEPT 且 checks 全绿，或没有 GitHub checks | squash 合并 | 不适用 |
| agent 非 0 退出、超时、或没有裁决 | 评论，停止 | 否 |
| 实现或审查进程中途挂了 | 评论，停止（`crashed`） | 否 |
| 已有别的 PR 用 Fixes/Closes 关联了这个 Issue，且不是本流水线的 PR | 评论，停止 | 否 |

流水线 PR 的身份是正文里的标记 `<!-- agent-pipeline:issue=N -->`。同时会写 `Fixes #N`，合并后由 GitHub 关闭 Issue。

两轮修复后停止的例子：

1. Issue `#12` 打上 `ready`。轮询启动实现者 A，分支 `agent/fix-12`，打开 PR `#40`。`fix_rounds=0`。
2. 审查者 B 在新进程里给出 `FIX`。`fix_rounds=1`。
3. 实现者 A 再次在 `agent/fix-12` 上修改，并推到 PR `#40`。
4. 审查者 B 再次 `FIX`。`fix_rounds=2`。
5. 实现者 A 做第二轮修复。
6. 审查者 B 第三次 `FIX`。脚本记成 `REJECT` 并停止。PR `#40` 留给人处理。

如果第 6 步是 `ACCEPT` 且检查通过，则 squash 合并，不会再开新循环。

## 角色

业务要求只写在 Issue 正文里。两份 brief 只规定角色、权限和交接：

- [实现者 brief](agent-pipeline/implementer-brief.md)
- [审查者 brief](agent-pipeline/reviewer-brief.md)

审查者 B 和实现者 A 不是同一个进程。轮询脚本另起 `agent-review.sh`，使用新的 worktree 和新的一次 agent 调用。修复轮次带回去的，只有审查者的 `NOTES`。

## 在本机怎么跑

需要：

- `git`
- 已登录这个仓库的 `gh`（`gh auth status`）
- `python3`（脚本用它读 JSON 和 Issue 小节）
- 想用和仓库一致的测试命令时，需要 `uv`
- 一个编码 CLI：默认 `opencode`，也可以是 `agent`。用 `AGENT_BIN` 指定

在仓库根目录：

```bash
# 语法和裁决表测试，不会写 GitHub
bash scripts/tests/test_agent_pipeline.sh

# 只读检查一个 Issue：核对标签和三个小节，打印计划
scripts/agent-implement.sh 123 --dry-run

# 只跑一轮轮询，仍然只读
scripts/agent-poll.sh --once --dry-run

# 前台守护。Ctrl-C 停止。
scripts/agent-poll.sh --interval 60
```

第一次真跑、先不要自动合并：

```bash
AGENT_PIPELINE_MERGE=0 scripts/agent-poll.sh --interval 60
```

审查者仍可以给出 `ACCEPT`。脚本会评论，并让 PR 保持打开，状态记为 `accepted_unmerged`。之后想合并，可以手动合并；也可以删掉 `.agent-pipeline/issues/<编号>`，再把 `AGENT_PIPELINE_MERGE` 设回 `1` 重新轮询。已有的流水线 PR 会被认领，而不是再开一个。

也可以手动推进一步：

```bash
scripts/agent-implement.sh 123
scripts/agent-review.sh 456
scripts/agent-implement.sh 123 --fix
```

手动执行 `agent-implement.sh` 会重新武装一个已停止的 Issue。轮询不会。状态已经是 `merged` 的，脚本不会再打开。

## 环境变量

| 变量 | 默认 | 含义 |
|---|---|---|
| `AGENT_BIN` | `opencode` | `opencode` 或 `agent` |
| `AGENT_MODEL` | 空 | 可选模型。不会默认成 `free-proxy/auto`。 |
| `AGENT_PROMPT_VIA` | `arg` | 提示词太长时改为 `stdin` |
| `AGENT_TIMEOUT` | `1800` | 秒。`0` 表示不限制。需要系统里有 `timeout`；没有的话不会杀进程。 |
| `AGENT_PIPELINE_DRY_RUN` | `0` | 只读。等同 `--dry-run`。 |
| `AGENT_PIPELINE_MERGE` | `1` | `0` 或 `--no-merge` 时不执行 `gh pr merge`。 |
| `AGENT_PIPELINE_MERGE_STRATEGY` | `squash` | `squash`、`merge` 或 `rebase` |
| `AGENT_PIPELINE_STATE_DIR` | `<主工作区>/.agent-pipeline` | 状态目录 |
| `AGENT_PIPELINE_MAX_FIX_ROUNDS` | `2` | 再出现 `FIX` 就变成 `REJECT` |
| `AGENT_PIPELINE_MAX_REVIEWS` | `3` | 审查次数上限，然后停止 |
| `AGENT_PIPELINE_CHECKS_MAX_POLLS` | `10` | GitHub checks 处于 pending 时最多再等多少轮 |

不要把 API key 写进仓库或这些脚本。`gh` 用它自己的登录态。编码 CLI 用它自己的配置。

## 状态、worktree、重新武装

运行时文件只留在本机：

```text
.agent-pipeline/issues/<n>          key=value 状态
.agent-pipeline/issues/<n>.notes    最近一次审查 NOTES
.agent-pipeline/issues/<n>.body.md  Issue 正文快照
.agent-pipeline/reviews/            裁决、diff、测试日志
.agent-pipeline/prompts/            发给每个进程的提示词
.agent-pipeline/pipeline.log
.worktrees/agent-pipeline/          实现和审查的检出目录
```

`.agent-pipeline/` 已加入 gitignore。`.worktrees/` 本来就忽略。

轮询时，主工作区不要停在 `agent/fix-*` 上。这些分支只放在 worktree 里，合并时脚本才能删掉本机分支。

想让轮询再处理某个 Issue：删掉 `.agent-pipeline/issues/<n>` 和 `.agent-pipeline/issues/<n>.notes`，标签留着。如果流水线 PR 还开着，下一轮会认领它，不会再开第二个。若要全新分支，先删掉残留的 `agent/fix-<n>`。

## 约定检查

实现工作区和审查工作区都跑：

```bash
uv run python -m unittest discover -s python_scripts/tests -p 'test_*.py'
```

没有 `uv` 时，脚本改用 `python3 -m unittest`，参数相同。没有 `python_scripts/tests` 时跳过，并在日志里写明。

GitHub 一侧用 `gh pr checks` 读取。这个脚手架不新增 Actions workflow。

- checks 全部通过：`ACCEPT` 后可以合并
- 没有任何 checks：以本地测试为准
- pending：等待，到达轮询上限后停止
- 失败：不合并

通过闸门时的合并命令：

```bash
gh pr merge <pr> --squash --delete-branch --match-head-commit <审查过的 sha>
```

`--match-head-commit` 用来拒绝合并审查者没看过的 SHA。策略用 `AGENT_PIPELINE_MERGE_STRATEGY` 改。

## 文件

| 路径 | 作用 |
|---|---|
| `scripts/agent-poll.sh` | 本机轮询 |
| `scripts/agent-implement.sh` | 实现者 A |
| `scripts/agent-review.sh` | 审查者 B |
| `scripts/lib/agent-pipeline-common.sh` | 解析、状态、调用 agent |
| `scripts/tests/test_agent_pipeline.sh` | 裁决表和解析测试 |
| `docs/agent-pipeline/implementer-brief.md` | 实现者角色卡 |
| `docs/agent-pipeline/reviewer-brief.md` | 审查者角色卡 |
| `.github/ISSUE_TEMPLATE/agent-fix.md` | Issue 正文模板 |

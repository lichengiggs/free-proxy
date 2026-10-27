# 夜审

本机手动跑，不进 GitHub Actions，也不由 `scripts/agent-poll.sh` 触发。脚本只核对和收集证据，不调用编码 agent，不改文件。

```bash
scripts/agent-night-review.sh
scripts/agent-night-review.sh --date 2026-10-27
```

证据写到 `.agent-pipeline/night-review/<日期>.md`。这个目录已在 gitignore 里。人把证据包交给一次新的编码会话，由那次会话改 `LESSONS.md`。升格进 `AGENTS.md` 时，人看过 diff 再提交。

## 扫什么

只看这一天已经进 main 的提交，以及本机 `.agent-pipeline` 里的审查裁决和 FIX 的 NOTES。

只记三件事：

- 修完又返工的
- 不该合进去的
- 验证太糙的

每条都要能执行。写成「某处有个 bug」的不算条目，夜审丢掉。没有 commit、PR 或 Issue 当证据的，也不记。

## 一条长什么样

写在 `LESSONS.md` 的「仍有效」下面：

```markdown
### 一句可执行的规则

- Evidence: 哪个 commit、PR 或 Issue，后果是什么
- Fix: 修好它的 commit
- Done right: 做对的例子
- Seen 1× (2026-10-27)
```

`Seen` 后面的次数必须等于括号里不同日期的个数。日期用 `YYYY-MM-DD`。同一天再遇到，不把次数加一，只保留原来的日期。

做对的例子用 `Done right:` 写在同一条下面。错题本里要有可以照着做的例子，不只是禁止。

## 升格和归档

`scripts/agent-night-review.sh --check` 按下面的规则打印：

| 输出 | 含义 | 接着做什么 |
|---|---|---|
| `ok` | 还不到升格或归档 | 留在「仍有效」 |
| `promote` | 3 个不同日期都出现过 | 把这一句规则写进 `AGENTS.md`，从「仍有效」删掉整条 |
| `archive` | 最后一次出现早于 90 天，且还没满 3 次 | 整条挪到「归档」 |
| `bad` | 没有 `Seen`，或次数和日期对不上 | 先改格式，再决定留还是删 |

又该升格又超过 90 天时，打印 `promote`。规则进 `AGENTS.md`，不进归档。

升格时只搬那一句规则。证据留在 git 历史里，不把整段错题复制进 `AGENTS.md`。

实现者和审查者只读「仍有效」。归档不放进每次任务的上下文。

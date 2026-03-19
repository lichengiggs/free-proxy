# Agent 经验教训

## Git 操作原则

**错误示例：**
```bash
# 过度复杂 - 不需要前置检查
snip git status
snip git diff --stat
snip git add README.md && git commit -m "..." && git push
```

**正确做法：**
```bash
git add README.md
git commit -m "docs: simplify README"
git push
```

**原则：**
1. 简单操作保持简单，不要添加不必要的检查步骤
2. 不需要用 snip 包装基础 git 命令
3. 三步走：add → commit → push，不要前置 status/diff
4. 除非用户明确要求查看变更，否则直接执行

## 最小够用原则

- 不要为简单任务添加复杂流程
- 用户说"做 X"，就做 X，不要做 X+Y+Z
- 如果操作失败，错误信息会告诉你，不需要提前检查

## KISS 原则

Keep It Simple, Stupid.

- 5 行能搞定的事，不要写成 50 行
- 一个命令能完成的，不要拆成多个
- 没有必要的参数，不要加

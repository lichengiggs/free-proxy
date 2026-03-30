# README Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the project README files so GitHub visitors immediately understand the project and beginners can start it safely with copy-paste-friendly steps.

**Architecture:** Keep the README as a landing page plus quickstart, not a full manual. Put the shortest successful path first, keep commands in clean code blocks, and move edge-case guidance into concise FAQ items.

**Tech Stack:** Markdown, existing project docs, current Python service behavior

---

### Task 1: Restructure Chinese README as landing page + quickstart

**Files:**
- Modify: `README.md`

- [ ] Audit current README sections and keep only the parts that help a first-time GitHub visitor decide and start quickly.
- [ ] Rewrite the opening so it explains value, target users, and stable public interface in plain language.
- [ ] Replace the current onboarding flow with a short, copy-safe quickstart that avoids mixed prose inside command blocks.
- [ ] Keep the most common integrations only and demote low-priority detail into FAQ.

### Task 2: Align English README with the same structure and current implementation

**Files:**
- Modify: `README_EN.md`

- [ ] Remove stale claims and align provider/model wording with the current codebase.
- [ ] Mirror the same landing-page structure used in the Chinese README.
- [ ] Keep the English version concise and easy to scan for GitHub visitors.

### Task 3: Verify readability and formatting

**Files:**
- Modify: `README.md`
- Modify: `README_EN.md`

- [ ] Check that every shell/code block contains only copyable content.
- [ ] Check heading order, list structure, and terminology consistency.
- [ ] Confirm the README matches the current stable aliases and endpoints: `free-proxy/auto`, `free-proxy/coding`, `GET /v1/models`, `POST /v1/chat/completions`.

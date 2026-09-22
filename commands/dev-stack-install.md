---
description: Scan this repo and recommend/install the matching Claude Code skills, plugins, and hooks.
---

Invoke the `dev-stack-installer` skill on the current working directory.

Follow its instructions exactly:
1. Detection pass (read-only).
2. Print the stack + recommended bundles.
3. Show what's already installed vs. missing.
4. Wait for the user's `Y / n / pick` reply.
5. Install approved items only. Show diffs for any `.claude/settings.json` or `CLAUDE.md` change before writing.

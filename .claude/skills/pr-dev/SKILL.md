---
name: pr-dev
description: Use when opening a pull request in this repo — pushes the current branch and opens the PR against `dev` (never `main`), with the gate output in the body and the other person as reviewer.
---

# Opening a PR against `dev`

Code goes to `dev` first. `main` only ever receives `dev` after review, so this skill never opens a
PR with `main` as the base.

## Before opening

1. `git branch --show-current` — refuse if it is `dev` or `main`. Work happens on a task branch
   (`scrum-NNN-short-name`), cut from `dev`.
2. `git status --short` — refuse if anything tracked is uncommitted. Untracked local files
   (`.env`, `.claude/settings.local.json`) stay out of the PR.
3. `git fetch origin dev` and check the branch is not behind: `git log --oneline HEAD..origin/dev`.
   If it prints anything, merge `origin/dev` in and re-run the checks before going on.
4. Run `make test` and the task's gate. Look at the output. If either fails, stop — do not open
   the PR to "see what CI says".
   - Exception, while the Odoo board is empty: the Odoo lines in `make doctor` and `odoo-board`
     MCP calls may fail (see `README.md`). Say so in the PR body; every other check must pass.

## Opening

```bash
git push -u origin HEAD
gh pr create --base dev --head "$(git branch --show-current)" --title "<what changed>" --body-file <file>
```

Title: what the change does, like a commit message. Body, in this order:

- **Task:** the board id (`SCRUM-NNN`) and its acceptance criterion, one line.
- **What changed:** two to five bullets.
- **Evidence:** the gate command and its real output, pasted, not summarised. A number not
  printed in this session does not go in.
- **Accepted failures:** only the Odoo-board exception above, if it applies.

No AI attribution and no co-author trailers in the title or body.

## After opening

- Request review from the other person (Builder ↔ Evaluator): `gh pr edit --add-reviewer <login>`.
- Report the PR URL with `request_review(<id>, ...)` on the board, if it is reachable.
- Do not merge it yourself. The Friday retro checks for zero self-merged PRs.

## Hard rules

| Never | Why |
|---|---|
| `--base main` | `main` only takes `dev`, after review |
| Open the PR with a failing test or gate | A gate is passed by its printed number, not by CI later |
| Merge or approve your own PR | No self-merges, ever |
| Put held-out cases or secrets in the diff | `evals/heldout/` is the Evaluator's; secrets live in `~/.config/` |

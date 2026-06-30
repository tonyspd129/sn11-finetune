---
name: git
description: Safe, effective git — inspect state/history, make atomic commits, manage branches, and undo changes correctly.
triggers: [git, commit, branch, merge, rebase, stash, diff, checkout, revert]
---

# Working with git

Always look before you act. Run `git status` and `git diff` (and `git log --oneline -n 20`)
to understand what has changed and where HEAD is *before* committing, switching, or resetting.

## Committing
- Stage deliberately: review `git diff` for what you're about to add, then `git add -p` or
  add specific paths rather than `git add -A` blindly.
- Keep commits **atomic** — one logical change per commit — with a clear message: a concise
  imperative summary line, then a body explaining *why* if it isn't obvious.
- Before committing, make sure the working tree builds/tests where relevant.

## Branches
- Create work on a branch: `git switch -c <name>` (or `git checkout -b <name>`).
- Check what branch you're on with `git status` before making changes.
- Integrate with `git merge` (preserves history) or `git rebase` (linear history) — prefer
  merge when others may share the branch; rebase only local, unpushed work.

## Inspecting & comparing
- `git log --oneline --graph --decorate` to see structure.
- `git diff <a>..<b>` to compare commits/branches; `git show <commit>` for one commit.
- `git blame <file>` to find when/why a line changed.

## Undoing safely (know which you need)
- Discard unstaged changes to a file: `git restore <file>` (destructive — confirm first).
- Unstage without losing work: `git restore --staged <file>`.
- Undo a commit but keep changes: `git reset --soft HEAD~1`.
- Undo a commit and discard changes: `git reset --hard HEAD~1` (destructive).
- Revert a *pushed* commit by making a new inverse commit: `git revert <commit>`.
- Stash work in progress: `git stash` / restore with `git stash pop`.

## Cautions
- Avoid `git push --force` on shared branches; prefer `--force-with-lease` and only on your
  own branches.
- Never commit secrets or large generated artifacts; check `git status` for surprises.
- If something looks wrong, stop and inspect (`git reflog` can recover lost commits) rather
  than running more destructive commands.

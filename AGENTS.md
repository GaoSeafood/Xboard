# Agent Guide — GaoSeafood Xboard fork

## Repository identity

- This repository is the `GaoSeafood/Xboard` fork of `cedar2025/Xboard`.
- The Git remotes are authoritative: `origin` must be `GaoSeafood/Xboard`; `upstream` is `cedar2025/Xboard`.
- Orca may display a cached upstream identity. Check `git remote -v` before pushing or opening a pull request. Never push to `upstream`.
- Use `origin/master` as the base for new task worktrees. Keep `master` protected and use focused task branches and pull requests.

## Development workflow

- The server development checkout and worktree locations are documented in `/home/opc/orca-projects/README.md`.
- Use an Orca-managed worktree for each independent task. Preserve existing branches, worktrees, and user changes.
- Before upstream sync, fetch both remotes and compare `origin/master` with `upstream/master`. Review the full change and retain GaoSeafood-owned commits; do not force-push or blindly merge a large upstream change.
- Review dependency, authentication, billing, database migration, and container-build changes before proposing a release.

## Production and private data

- Production configuration and runtime data are outside this repository. Never read or print populated `.env` files, credentials, SQLite/database contents, logs, customer records, uploads, or backups.
- Do not edit or restart production during ordinary development. A production update needs an explicit release instruction from the user.
- Before an authorized release, record the exact image digest, create a protected database/config backup, change one service at a time, verify the public health path, and keep the previous image available for rollback.
- A source commit or successful container build does not by itself prove that production runs that version; verify the live container image digest and application response.

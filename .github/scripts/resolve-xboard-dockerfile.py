#!/usr/bin/env python3
"""Keep the upstream runtime fixes while building the fork at an exact commit."""

from pathlib import Path
import re


path = Path("Dockerfile")
text = path.read_text()

security_version = re.search(
    r'version_compare\(PHP_VERSION,\s*"(\d+)\.(\d+)\.(\d+)"', text
)
if not security_version or tuple(map(int, security_version.groups())) < (8, 2, 35):
    raise SystemExit("upstream Dockerfile does not enforce PHP 8.2.35 or newer")

required_upstream_markers = (
    "COPY --from=redis:8-alpine /usr/local/bin/redis-* /usr/local/bin/",
    "FROM runtime AS app",
)
missing = [marker for marker in required_upstream_markers if marker not in text]
if missing:
    raise SystemExit(f"upstream Dockerfile no longer has the reviewed security fixes: {missing}")

repo_arg = "ARG REPO_URL=https://github.com/GaoSeafood/Xboard.git"
if text.count("ARG REPO_URL=") != 1:
    raise SystemExit("expected exactly one REPO_URL build argument")
text = text.replace(
    next(line for line in text.splitlines() if line.startswith("ARG REPO_URL=")),
    repo_arg,
)

branch_args = re.findall(r"(?m)^ARG BRANCH_NAME=.*$", text)
if len(branch_args) != 1:
    raise SystemExit("expected one upstream BRANCH_NAME build argument")
start_marker = branch_args[0]
end_marker = "git submodule update --init --recursive --force"
start = text.find(start_marker)
end = text.find(end_marker, start)
if start < 0 or end < 0 or text.count(end_marker) != 1:
    raise SystemExit("upstream Dockerfile clone section changed; resolve it manually")
end += len(end_marker)

clone_section = '''ARG SOURCE_SHA=

RUN rm -rf ./* ./.??* 2>/dev/null || true; \\
    git config --global --add safe.directory /www; \\
    if [ -n "$SOURCE_SHA" ]; then \\
      git init . && git remote add origin "$REPO_URL" && \\
      git fetch --depth 1 origin "$SOURCE_SHA" && git checkout --detach FETCH_HEAD; \\
    else \\
      git clone --depth 1 --branch master "$REPO_URL" .; \\
    fi && \\
    git submodule update --init --recursive --force'''
text = text[:start] + clone_section + text[end:]

if 'git fetch --depth 1 origin "$SOURCE_SHA"' not in text:
    raise SystemExit("exact source SHA fetch is missing")

path.write_text(text)

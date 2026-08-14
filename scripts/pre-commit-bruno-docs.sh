#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
builder="${repo_root}/.agents/skills/ideal-bruno/scripts/build_web_docs.py"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to rebuild Bruno web documentation." >&2
  exit 1
fi

(cd "${repo_root}" && uv run python "${builder}")
git -C "${repo_root}" add docs/api/bruno/index.html
echo "Bruno web documentation regenerated and staged."

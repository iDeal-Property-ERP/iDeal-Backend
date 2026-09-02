#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
tool="${repo_root}/.agents/skills/ideal-dbml/scripts/dbml_tool.py"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to validate and rebuild DBML schema documentation." >&2
  exit 1
fi

(cd "${repo_root}" && uv run python "${tool}" generate)
(cd "${repo_root}" && uv run python "${tool}" validate)
git -C "${repo_root}" add docs/db/db-diagram/
echo "DBML schema documentation validated, regenerated, and staged."

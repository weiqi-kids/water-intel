#!/bin/bash
# Validate docs/ directory structure.
# Usage: bash scripts/validate_docs.sh [docs_path]

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
DOCS_PATH="${1:-$REPO_DIR/docs}"

python3 "$SCRIPT_DIR/validate_docs.py" --docs-path "$DOCS_PATH"

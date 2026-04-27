#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/.claude/commands/meta-diagnostics"

# Validate we're in the repo root
if [ ! -f "$REPO_ROOT/.claude/commands/meta-diagnostics/SKILL.md" ]; then
  echo "Error: Run this script from the root of the meta-account-diagnostics repo."
  exit 1
fi

# Warn about old install location
OLD_INSTALL="$HOME/.claude/skills/meta-diagnostics"
if [ -d "$OLD_INSTALL" ]; then
  echo "Note: Found old install at $OLD_INSTALL"
  echo "      This location is no longer used. You can delete it:"
  echo "      rm -rf $OLD_INSTALL"
  echo ""
fi

mkdir -p "$INSTALL_DIR/templates"

cp "$REPO_ROOT/.claude/commands/meta-diagnostics/SKILL.md" "$INSTALL_DIR/SKILL.md"
cp "$REPO_ROOT/data/motion-benchmarks.json" "$INSTALL_DIR/motion-benchmarks.json"
cp "$REPO_ROOT/templates/dashboard_template.py" "$INSTALL_DIR/templates/dashboard_template.py"

if [ -f "$REPO_ROOT/.claude/commands/meta-diagnostics/_run_analyses.py" ]; then
  cp "$REPO_ROOT/.claude/commands/meta-diagnostics/_run_analyses.py" "$INSTALL_DIR/_run_analyses.py"
fi

echo "✓ /meta-diagnostics skill installed to $INSTALL_DIR"
echo ""
echo "Assets installed:"
echo "  SKILL.md"
echo "  motion-benchmarks.json"
echo "  templates/dashboard_template.py"
[ -f "$INSTALL_DIR/_run_analyses.py" ] && echo "  _run_analyses.py"
echo ""
echo "Restart Claude Code (or open a new session) and run:"
echo "  /meta-diagnostics"
echo ""
echo "Prerequisite: ads-mcp-connector must be installed and connected to Meta."
echo "Run /ads-connect first if you haven't already."

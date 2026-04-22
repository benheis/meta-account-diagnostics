#!/bin/bash
set -e

SKILL_DIR="$HOME/.claude/skills/meta-diagnostics"
SKILL_SRC=".claude/commands/meta-diagnostics/SKILL.md"

if [ ! -f "$SKILL_SRC" ]; then
  echo "Error: Run this script from the root of the meta-account-diagnostics repo."
  exit 1
fi

mkdir -p "$SKILL_DIR"
cp "$SKILL_SRC" "$SKILL_DIR/SKILL.md"

echo "✓ /meta-diagnostics skill installed to $SKILL_DIR"
echo ""
echo "Restart Claude Code (or open a new session) and run:"
echo "  /meta-diagnostics"
echo ""
echo "Prerequisite: ads-mcp-connector must be installed and connected to Meta."
echo "Run /ads-connect first if you haven't already."

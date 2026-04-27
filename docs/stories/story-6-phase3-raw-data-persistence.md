# Story 6: Phase 3 Raw Data Persistence + Install Bundling — Brownfield Fix

**Size:** Small | **Source:** Architecture Review (Hybrid Compute Architecture) | **Commit baseline:** `f5b69a3`

> **Dependency:** Story 7 (`_run_analyses.py`) depends on this story's raw file contract. Implement Story 6 before Story 7.

---

## User Story

As a system that needs to compute analyses deterministically,
I want the raw API pull data written to disk immediately after each pull,
So that the Python compute engine (Story 7) can read stable, complete input files rather than reconstructing data from the LLM's in-context state.

---

## Story Context

**Existing System Integration:**
- Integrates with: `SKILL.md` Phase 3 (data pull instructions); `install.sh` (skill file deployment)
- Technology: Claude LLM writing JSON via bash tool; bash install script
- Follows pattern: Phase 5 already writes results.json and dashboard.py to `~/meta-diagnostics/` — this extends the same file output pattern to Phase 3
- Touch points: SKILL.md Phase 3 (5 new write steps); `install.sh` (3 new copy lines)

**Background:**
Currently, Phase 3 pulls data into the LLM's context and holds it there until Phase 4 uses it. For the hybrid compute architecture, Phase 4 must hand off to a Python script (`_run_analyses.py`). That script needs raw data as files on disk — it cannot read from the LLM's context window. This story establishes the raw data contract: 5 JSON files in `~/meta-diagnostics/raw/`, written immediately after each pull.

Additionally, `install.sh` currently only copies `SKILL.md`. The full skill requires `motion-benchmarks.json` (for A5/A7 benchmarks) and the dashboard template. This story expands the install to bundle all static assets.

---

## Acceptance Criteria

### Phase 3 — Write Raw Data to Disk

After each pull completes successfully, write the raw response to disk before proceeding to the next pull:

1. **After Pull A** (ads_90d):
   Write `~/meta-diagnostics/raw/ads_90d.json` — the full array of ad rows from `meta_get_ads` with `date_range: "last_90d"`.

2. **After Pull B** (ads_6m):
   Write `~/meta-diagnostics/raw/ads_6m.json` — the full array of ad rows from `meta_get_ads` with `date_range: "last_6_months"`.

3. **After Pull C** (monthly_reach):
   Write `~/meta-diagnostics/raw/monthly_reach.json` — the full response from `meta_get_monthly_reach`.

4. **After Pull D** (account_overview):
   Write `~/meta-diagnostics/raw/account_overview.json` — the full response from `meta_get_account_overview`.

5. **After Pull E** (ad_monthly_spend):
   Write `~/meta-diagnostics/raw/ad_monthly_spend.json` — the full response from `meta_get_ad_monthly_spend`.

6. **Create directory** `~/meta-diagnostics/raw/` before the first write if it doesn't exist. (Parent `~/meta-diagnostics/` already created in Phase 5 — create `raw/` subdirectory here in Phase 3.)

7. **Empty pulls:** If a pull returns an empty array or null, still write the file with content `[]` or `{}`. Never skip the write. The compute script depends on all 5 files being present.

8. **Failed pulls:** If the MCP tool returns an error, write `{"error": "<error message>", "data": []}` to the file. Continue with remaining pulls. The compute script will handle empty/error data gracefully.

9. **Confirm to user** after all 5 files are written (before the existing "Data pulled. Running 7 analyses..." message): `"Raw data saved to ~/meta-diagnostics/raw/ (5 files)."`

### Install Bundling — `install.sh`

10. **Update `install.sh`** to copy all required skill assets to the installed skill directory. The install target directory changes from `$HOME/.claude/skills/meta-diagnostics` to `$HOME/.claude/commands/meta-diagnostics` (the standard Claude Code command directory that Claude Code actually reads for slash commands):
    ```bash
    INSTALL_DIR="$HOME/.claude/commands/meta-diagnostics"
    mkdir -p "$INSTALL_DIR"
    cp ".claude/commands/meta-diagnostics/SKILL.md" "$INSTALL_DIR/SKILL.md"
    cp "data/motion-benchmarks.json" "$INSTALL_DIR/motion-benchmarks.json"
    mkdir -p "$INSTALL_DIR/templates"
    cp "templates/dashboard_template.py" "$INSTALL_DIR/templates/dashboard_template.py"
    ```
    Note: `_run_analyses.py` is added to this copy list in Story 7 when the file exists.

11. **SKILL.md Phase 5 Step 3** currently says "Copy the template from the skill's `templates/dashboard_template.py`". Clarify the expected path: "Copy `{skill_dir}/templates/dashboard_template.py` to `~/meta-diagnostics/dashboard.py`, where `{skill_dir}` is the directory containing this SKILL.md file."

12. **SKILL.md A7** currently references `motion-benchmarks.json` without a path. Update all references to specify: "Read `{skill_dir}/motion-benchmarks.json` where `{skill_dir}` is the directory containing this SKILL.md file."

**Integration Requirements:**
13. The 5 raw files are the sole inputs to `_run_analyses.py` (Story 7). Their schema is the raw MCP tool response — no transformation before writing.
14. Existing Phase 4 logic is NOT changed by this story — the LLM still runs analyses in-context as before. Story 8 replaces Phase 4 logic. This story only adds the file writes and install fixes.
15. Raw files from a prior run are overwritten on each new run — no versioning needed for raw data.

**Quality Requirements:**
16. After a successful run, `ls ~/meta-diagnostics/raw/` shows all 5 files.
17. All 5 files are valid JSON (can be parsed with `python3 -c "import json; json.load(open('...'))"`)
18. `install.sh` runs without error from the repo root; `ls ~/.claude/commands/meta-diagnostics/` shows SKILL.md, motion-benchmarks.json, and templates/dashboard_template.py.

---

## Technical Notes

**Phase 3 — write instruction pattern (add after each pull):**
```
After receiving the response from meta_get_ads (last_90d):
Run: mkdir -p ~/meta-diagnostics/raw
Write the full response JSON to ~/meta-diagnostics/raw/ads_90d.json.
If the response is an error, write: {"error": "<message>", "data": []}
```
Repeat this pattern for each of the 5 pulls using the filenames above.

**Updated install.sh (full replacement):**
```bash
#!/bin/bash
set -e

INSTALL_DIR="$HOME/.claude/commands/meta-diagnostics"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Validate we're in the repo root
if [ ! -f "$REPO_ROOT/.claude/commands/meta-diagnostics/SKILL.md" ]; then
  echo "Error: Run this script from the root of the meta-account-diagnostics repo."
  exit 1
fi

mkdir -p "$INSTALL_DIR/templates"

cp "$REPO_ROOT/.claude/commands/meta-diagnostics/SKILL.md" "$INSTALL_DIR/SKILL.md"
cp "$REPO_ROOT/data/motion-benchmarks.json" "$INSTALL_DIR/motion-benchmarks.json"
cp "$REPO_ROOT/templates/dashboard_template.py" "$INSTALL_DIR/templates/dashboard_template.py"

# _run_analyses.py added in Story 7
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
```

**Raw file schema contract** (for Story 7 implementation):
- `ads_90d.json`: `[{"ad_id": "...", "name": "...", "spend": ..., "conversions": ..., "cpa": ..., "created_time": "...", ...}, ...]`
- `ads_6m.json`: same schema as ads_90d.json
- `monthly_reach.json`: `[{"month": "YYYY-MM", "reach": ..., "spend": ...}, ...]` — exact schema depends on MCP tool response
- `account_overview.json`: `{"spend": "...", "active_ads": ..., "date_range": "..."}` — raw MCP response
- `ad_monthly_spend.json`: `[{"ad_id": "...", "name": "...", "month": "YYYY-MM", "spend": ...}, ...]` — one row per ad per month

**Note on monthly_reach spend field:** If `meta_get_monthly_reach` does not return per-month spend, the compute script (Story 7) must aggregate spend from `ad_monthly_spend.json` instead. Record which approach applies for Story 7 implementation.

---

## Definition of Done

- [ ] Phase 3 writes all 5 raw files to `~/meta-diagnostics/raw/` after each pull
- [ ] Empty/error pulls write `[]` or `{"error": "...", "data": []}` — never skip
- [ ] User confirmation message after raw data saved
- [ ] `install.sh` copies SKILL.md, motion-benchmarks.json, dashboard_template.py to `~/.claude/commands/meta-diagnostics/`
- [ ] SKILL.md Phase 5 Step 3 specifies `{skill_dir}/templates/dashboard_template.py`
- [ ] SKILL.md A7 references `{skill_dir}/motion-benchmarks.json`
- [ ] Running `bash install.sh` from repo root succeeds and produces correct directory structure

---

## Risk and Compatibility Check

**Primary Risk:** `install.sh` previously installed to `~/.claude/skills/meta-diagnostics/` — users with the old install path have SKILL.md in the wrong place. They must re-run `install.sh` to get the correct path. **This is a breaking change for existing installs** — document in the commit message that users must reinstall.

**Mitigation:** Add a migration check to `install.sh`: if `~/.claude/skills/meta-diagnostics/SKILL.md` exists, print: "Note: Found old install at ~/.claude/skills/meta-diagnostics/ — this has been superseded by ~/.claude/commands/meta-diagnostics/. You can delete the old directory."

**Rollback:** Remove the 5 write steps from Phase 3 — the LLM continues running analyses from context as before. Revert install.sh. Raw files on disk are harmless and can be deleted manually.

- [x] Raw file writes are additive — they don't change Phase 3 behavior (data still held in context for current Phase 4)
- [x] Phase 4 in current form is unaffected (Story 8 changes Phase 4)
- [x] Dashboard unchanged
- [x] `install.sh` change is safe for new installs; existing installs need manual reinstall

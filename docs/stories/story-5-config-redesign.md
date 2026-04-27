# Story 5: Config Redesign — Winner Criteria + Silent Defaults — Brownfield Fix

**Size:** Small | **Source:** Architecture Review (CRITICAL-1, CRITICAL-2) | **Commit baseline:** `f5b69a3`

---

## User Story

As a media manager setting up the diagnostic,
I want the configuration to capture a meaningful performance target — my acceptable CPA — rather than an arbitrary spend threshold,
So that "winner" is defined by whether the ad is profitable, not by how much money I happened to put behind it.

---

## Story Context

**Existing System Integration:**
- Integrates with: `SKILL.md` Phase 1 (config collection) and Phase 4 (analyses reference config keys)
- Technology: Claude LLM reading/writing `~/.meta-diagnostics-config.json`
- Follows pattern: existing 4-question Phase 1 sequence + JSON merge write
- Touch points: SKILL.md Phase 1 only — no dashboard changes

**Background:**
Phase 1 currently asks for `winner_threshold` (a spend floor, default $3,000). This key is explicitly deprecated in Analysis 5 — the LLM collects it and immediately ignores it. Meanwhile, two config keys that ARE actively used by analyses (`allocation_min_spend` in A1/A2 and `winner_top_percentile` in A5) are never asked for or written to config — they appear as implicit defaults the LLM must guess.

Additionally, there is no instruction for parsing config overrides from user invocation (the A2 caption tells users to say "rerun with allocation_min_spend = 1000" but SKILL.md has no instruction for handling that message).

This story: replaces `winner_threshold` with `target_cpa` (optional, null if user doesn't have one), adds the two missing keys as silent defaults, and adds a config-override parsing rule.

---

## Acceptance Criteria

### Phase 1 Config Questions

1. **Remove Question 4** (`winner_threshold`). It is no longer asked, no longer saved, and no longer referenced anywhere.
2. **Replace with Question 4: target_cpa (optional)**:
   ```
   What CPA would you consider a winning result for your business?

   This is the maximum [conversion_label] cost you'd accept for a scaled creative.
   If you have a clear target (e.g. "anything under $200 is profitable"), enter it.
   If not, leave blank — the system will identify winners relative to your account's
   performance distribution (top 20% by CPA among converted concepts).

   Type a number (e.g. 200) or press Enter to skip.
   ```
   - Parse as a float if provided; store as `null` if blank/skipped.
   - Validate: if provided, must be a positive number. Re-prompt once on invalid input.

### Config File Schema

3. **Save config** block updated to include all keys:
   ```json
   {
     "deps_checked": true,
     "account_id": "act_...",
     "conversion_event": "...",
     "conversion_label": "...",
     "industry_vertical": "...",
     "target_cpa": null,
     "allocation_min_spend": 500,
     "winner_top_percentile": 0.20
   }
   ```
   - `target_cpa`: null (if skipped) or the user's numeric input
   - `allocation_min_spend`: always written as `500` on first setup (silent default, not prompted)
   - `winner_top_percentile`: always written as `0.20` on first setup (silent default, not prompted)

4. **Backward compatibility:** If the existing config file contains `winner_threshold`, silently ignore it — do not error, do not migrate it to `target_cpa`.

### Config Skip Logic

5. The existing "skip to Phase 2 if all required fields present" logic changes: the required fields are now `account_id`, `conversion_event`, `conversion_label`, `industry_vertical`. `target_cpa` is optional (null is a valid value). `allocation_min_spend` and `winner_top_percentile` are auto-set.
6. If an existing config is missing `allocation_min_spend` or `winner_top_percentile`, add them with defaults during Phase 1 (without re-asking all questions).

### Config Override Parsing

7. **At the top of Phase 1**, before reading or asking for config, check whether the user passed any override parameters when invoking the skill. Pattern to detect:
   - User message contains phrases like: `"with allocation_min_spend = 1000"`, `"allocation_min_spend=500"`, `"target_cpa = 150"`, `"winner_top_percentile = 0.15"`
   - If detected: update those keys in `~/.meta-diagnostics-config.json` and confirm: `"Config updated: allocation_min_spend set to $1,000. Proceeding with diagnostic..."`
   - Overridable keys: `allocation_min_spend`, `target_cpa`, `winner_top_percentile`
   - Non-overridable (require full re-setup): `account_id`, `conversion_event`, `industry_vertical`

**Integration Requirements:**
8. All analyses that reference `allocation_min_spend`, `target_cpa`, or `winner_top_percentile` continue to read from config — no changes needed to analysis logic (analysis changes handled in Stories 7 and 8).
9. `winner_threshold` key removed from all SKILL.md references (search for any remaining mentions).

**Quality Requirements:**
10. Running Phase 1 on a fresh config produces a config file with all 7 keys populated.
11. Running Phase 1 on an existing config that has all required fields — skips to Phase 2 without asking questions, but adds missing silent defaults.
12. "rerun /meta-diagnostics with allocation_min_spend = 2000" → config updated, diagnostic runs with new floor, caption in A2 dashboard shows $2,000.

---

## Technical Notes

**Phase 1 entry override detection (add before existing config-read logic):**
```
Before reading or collecting config, scan the user's invocation message for override patterns.
Supported overrides: allocation_min_spend (positive integer), target_cpa (positive number or "null"),
winner_top_percentile (decimal between 0.01 and 0.50).
If found: load existing config, update the specified keys, write back, confirm update, proceed to Phase 2.
If not found: proceed with normal Phase 1 flow.
```

**Updated "skip" condition for existing config:**
```
If config exists AND has account_id, conversion_event, conversion_label, industry_vertical:
  - Add allocation_min_spend: 500 if missing (silent, no prompt)
  - Add winner_top_percentile: 0.20 if missing (silent, no prompt)
  - Add target_cpa: null if missing (silent, no prompt)
  - Write updated config back to disk
  - Skip to Phase 2
```

**target_cpa usage across analyses (for SKILL.md Phase 4 reference):**
- A1 Purple zone: uses `account_median_cpa` as the CPA ceiling (unchanged — Purple is defined by position, not absolute target)
- A2 tier ranking: unchanged — still ranks by CPA
- A5 winner selection: `target_cpa` is the primary discriminator when set; `winner_top_percentile` is the fallback — see Story 7 for compute implementation

---

## Definition of Done

- [ ] Phase 1 Question 4 asks for `target_cpa` (optional), not `winner_threshold` (spend floor)
- [ ] Config written with 7 keys: account_id, conversion_event, conversion_label, industry_vertical, target_cpa, allocation_min_spend, winner_top_percentile
- [ ] Existing configs with `winner_threshold` silently accepted (not errored)
- [ ] Config-override parsing instruction at Phase 1 entry handles allocation_min_spend, target_cpa, winner_top_percentile overrides
- [ ] Skip logic on existing config adds missing silent defaults without re-asking questions
- [ ] No remaining references to `winner_threshold` in SKILL.md

---

## Risk and Compatibility Check

**Primary Risk:** Users with existing configs still have `winner_threshold` stored. The key is now ignored, which is safe — A5 already ignored it. No behavior change for existing users.

**Rollback:** Revert Phase 1 changes in SKILL.md. Existing config files are unaffected.

- [x] No breaking changes to existing analysis output (analysis changes are in Story 7)
- [x] `target_cpa: null` is a valid JSON value — dashboard and downstream readers must handle null gracefully (they don't read this key directly)
- [x] Silent defaults are additive — no existing behavior removed
- [x] Config-override parsing is additive — if pattern not found, Phase 1 proceeds unchanged

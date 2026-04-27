# Story 9: MCP Response Normalization — Brownfield Fix

**Size:** Medium | **Source:** Post-PR4 QA — Phase 3 ↔ Phase 4 data contract mismatch | **Commit baseline:** `75b501c`

> **Blocker:** Every analysis returns INSUFFICIENT_DATA on a real account run because `_run_analyses.py` expects bare lists but MCP tools return wrapped envelope objects. This story is P0 — nothing else is verifiable until it ships.

---

## User Story

As a developer running `_run_analyses.py` against real MCP output,
I want the script to correctly parse whatever shape the MCP tools return,
So that every analysis computes against actual data instead of silently zeroing out.

---

## Story Context

**Existing System Integration:**
- Modifies: `.claude/commands/meta-diagnostics/_run_analyses.py` — load/normalization layer only (lines 1155–1169 and new functions above `main`)
- No changes to: `SKILL.md`, `dashboard_template.py`, `install.sh`, any analysis function (`run_a1` through `run_a7`)
- Technology: Python 3, standard library only — no new dependencies
- Follows pattern: existing `safe_float()` helper pattern — defensive parsing, never crash, degrade gracefully

**Background:**
PR 4 introduced `_run_analyses.py` with the expectation that Phase 3 would write bare lists to disk. In practice, the MCP tools return wrapped envelope objects — the agent writes whatever the tool returns verbatim. The `isinstance` guards at lines 1162–1169 silently coerce any non-list response to `[]`, producing INSUFFICIENT_DATA across all 7 analyses. Three distinct shapes need normalization:

| File | MCP returns | Script expects |
|---|---|---|
| `ads_90d.json`, `ads_6m.json` | `{"ads": [...], "since": "...", "until": "..."}` — 11 fields per ad, `ad_name` key, `cost_per_action_type` list instead of flat `conversions` | `list[dict]` — each ad has `name`, `spend`, `conversions`, `created_time` |
| `monthly_reach.json` | `{"months": [...], "count": 13}` | `list[dict]` |
| `ad_monthly_spend.json` | `{"ads": [{..., "ad_name": "...", "monthly_spend": [{month, spend}, ...]}]}` | `list[dict]` — one flat row per ad-month: `{name, month, spend}` |

The `conversions` derivation requires `conversion_event` from config (e.g. `"Purchase"`) — this is why the fix belongs in `_run_analyses.py` and not the MCP layer. The MCP tool cannot know which action type is the user's conversion event.

---

## Acceptance Criteria

### Normalization Functions

1. **`normalize_ads_response(raw, conversion_event)`** — handles `ads_90d.json` and `ads_6m.json`:
   - If `raw` is a `list`: return as-is (already flat — forward-compatible if MCP shape changes)
   - If `raw` is a `dict` with key `"ads"`: extract `raw["ads"]`
   - For each ad in the extracted list:
     - Map `ad_name` → `name` if `name` key is absent
     - Derive `conversions`: search `cost_per_action_type` list for an entry whose `action_type` string contains `conversion_event` (case-insensitive). If found and `value > 0`: `conversions = round(safe_float(spend) / safe_float(value), 4)`. If not found or value is 0: `conversions = 0.0`
     - Normalize `created_time`: strip timezone suffix (e.g. `+0000`) to leave `"YYYY-MM-DDTHH:MM:SS"` — `build_concept_maps` only uses the first 7 chars, so this is a safety trim
   - Return the normalized list

2. **`normalize_reach_response(raw)`** — handles `monthly_reach.json`:
   - If `raw` is a `list`: return as-is
   - If `raw` is a `dict` with key `"months"`: return `raw["months"]`
   - Otherwise: return `[]`

3. **`normalize_monthly_spend_response(raw)`** — handles `ad_monthly_spend.json`:
   - If `raw` is a `list`: return as-is (already flat)
   - If `raw` is a `dict` with key `"ads"`: flatten the nested structure:
     ```
     for each ad in raw["ads"]:
         for each entry in ad["monthly_spend"]:
             emit {name: ad.get("ad_name") or ad.get("name"), month: entry["month"], spend: entry["spend"]}
     ```
   - Return the flattened list

### Integration

4. Replace the `isinstance` guards at lines 1162–1169 with normalization calls:
   ```python
   ads_90d      = normalize_ads_response(load_json(..., []), conversion_event)
   ads_6m       = normalize_ads_response(load_json(..., []), conversion_event)
   monthly_reach_raw = normalize_reach_response(load_json(..., []))
   ad_monthly_spend  = normalize_monthly_spend_response(load_json(..., []))
   ```
   `account_overview` is a dict — no change needed.

5. `conversion_event` is available at line 1143 as `config.get('conversion_event', 'Conversion')` — pass this to `normalize_ads_response`.

6. All three normalizer functions are **pure functions** (no side effects, no file I/O) — placed in the Helpers section of the file, below `load_json`.

### Resilience Requirements

7. If `cost_per_action_type` is absent from an ad, `conversions = 0.0` — no KeyError, no crash
8. If no action_type entry matches `conversion_event`, `conversions = 0.0` — degrade gracefully, do not skip the ad
9. If `raw["ads"]` is not a list (e.g. `null`), return `[]`
10. If `monthly_spend` is absent from an ad entry in `ad_monthly_spend`, skip that ad — no crash

### Quality Requirements

11. Running `_run_analyses.py` against real MCP output (the `~/meta-diagnostics/raw/` files from a live account run) produces non-zero concept aggregates for all analyses that have data
12. All 7 analyses return a verdict other than INSUFFICIENT_DATA when the account has ≥90 days of active ads
13. Verified on `act_748122004521787`: A1 Purple zone contains scaled winner concepts with combined spend reflecting merged Copy variants

---

## Technical Notes

**`cost_per_action_type` matching — example:**

```python
def _find_conversions(cost_per_action_type: list, conversion_event: str, spend: float) -> float:
    if not cost_per_action_type or not conversion_event:
        return 0.0
    event_lower = conversion_event.lower()
    for entry in cost_per_action_type:
        action_type = str(entry.get('action_type', '')).lower()
        if event_lower in action_type or action_type in event_lower:
            cpa_val = safe_float(entry.get('value', 0))
            if cpa_val > 0:
                return round(spend / cpa_val, 4)
    return 0.0
```

**Flattening `ad_monthly_spend` — example:**

```python
def normalize_monthly_spend_response(raw) -> list:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return []
    ads = raw.get('ads', [])
    if not isinstance(ads, list):
        return []
    rows = []
    for ad in ads:
        name = ad.get('ad_name') or ad.get('name', '')
        for entry in (ad.get('monthly_spend') or []):
            rows.append({'name': name, 'month': entry.get('month', ''), 'spend': entry.get('spend', '0')})
    return rows
```

**Dead code cleanup (optional, can be separate PR):** `run_a2()` has a duplicate `ads_out` assignment block (lines 288–310 — the first block at 288–297 is immediately overwritten). This is harmless but should be cleaned up. Not a blocker for this story.

---

## Definition of Done

- [ ] `normalize_ads_response(raw, conversion_event)` implemented in Helpers section
- [ ] `normalize_reach_response(raw)` implemented in Helpers section
- [ ] `normalize_monthly_spend_response(raw)` implemented in Helpers section
- [ ] Lines 1155–1169 in `main()` updated to call normalizers
- [ ] Verified on real account: no INSUFFICIENT_DATA verdicts for analyses with data
- [ ] Verified: `conversions` derived correctly for at least one concept (cross-check: `spend ÷ conversions ≈ expected CPA`)
- [ ] No new dependencies introduced
- [ ] `install.sh` re-run after change (copies updated `_run_analyses.py` to install dir)

---

## Risk and Compatibility Check

**Primary Risk:** `conversion_event` string doesn't match any `action_type` in the Meta response — `conversions = 0` for all ads, A1/A2/A5 return INSUFFICIENT_DATA. Mitigation: the matching is substring-based (case-insensitive), which handles the common `"Purchase"` → `"offsite_conversion.fb_pixel_purchase"` pattern. If a user has an unusual conversion event, the error surface is clear (zero conversions in the analysis) and fixable by checking config.

**Secondary Risk:** MCP response shape changes again in a future connector update. Mitigation: the normalizers accept bare lists as valid input — if the MCP ever does return flat lists natively, the normalizers pass them through without transformation.

- [x] No changes to any analysis function — all 7 are isolated from this change
- [x] No changes to `SKILL.md` or `dashboard_template.py`
- [x] Backwards compatible — if raw files are already flat lists, normalizers pass them through
- [x] No new Python dependencies

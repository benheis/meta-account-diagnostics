# Story 10: A2 Relative Spend Floor — Brownfield Fix

**Size:** Small | **Source:** Post-PR4 QA — A2 analysis design issue | **Commit baseline:** `75b501c`

> **Dependency:** Story 9 must ship first. The A2 verdict is meaningless until real MCP data flows correctly through the normalization layer.

---

## User Story

As a media manager reading the Creative Allocation analysis,
I want the Top 10% CPA tier to reflect concepts that have been genuinely tested at scale,
So that a $600 ad with one lucky conversion doesn't outrank a $50K scaled winner in the efficiency ranking.

---

## Story Context

**Existing System Integration:**
- Modifies: `.claude/commands/meta-diagnostics/_run_analyses.py` → `run_a2()` (lines 259–370) and `_empty_a2()` return dict
- Modifies: `templates/dashboard_template.py` → `chart_creative_allocation()` caption (line 245–252)
- No changes to: `SKILL.md`, any other analysis function, `install.sh`
- Technology: Python 3; Streamlit caption string
- Follows pattern: `run_a1()` already uses `total_spend` to compute percentile-based thresholds — same pattern applied to A2's ranking gate

**Background:**
Story 2 (PR 3) introduced `allocation_min_spend` (default $500) as the ranked pool gate for A2. This correctly excludes zero-spend concepts but still admits low-spend outliers into the percentile competition. On a real account run, a concept with $600 spend and one conversion at $45 CPA ranks as Top 1% — pushing the actual scaled winners ($20K–$50K spend) into "Other (ranked)" and collapsing `top_10pct_spend_pct` to ~1–2%. The HEALTHY threshold is `top_10pct_spend_pct > 50%` which reflects the correct target: half the budget should be on your best CPA concepts. The problem is the ranked pool population, not the threshold.

The fix: gate the percentile ranking pool at `max(allocation_min_spend, 0.5% of total account spend)`. This is a relative floor that scales with account size — on a $72K account it's ~$720 (minimal change), on a $500K account it's $5,000 (excludes micro-tests from ranking), on a $1M account it's $10,000.

Concepts above `allocation_min_spend` but below the 1% floor are tagged `"Other (untested)"` — they've been tested but not committed enough to rank. This is the honest label.

---

## Acceptance Criteria

### Compute Changes (`run_a2`)

1. After computing `total_spend`, compute the effective ranking floor:
   ```python
   rank_floor = max(allocation_min, total_spend * 0.005)
   ```

2. Ranked pool gate changes from `spend >= allocation_min` to `spend >= rank_floor`:
   ```python
   if c['cpa'] > 0 and c['conversions'] >= 1 and c['spend'] >= rank_floor:
       ranked.append(entry)
   elif c['cpa'] > 0 and c['conversions'] >= 1:
       sub_threshold.append(entry)   # above allocation_min but below rank_floor, OR below allocation_min with conversions
   else:
       unranked.append(entry)
   ```

3. `rank_floor` emitted in the data dict as `effective_rank_floor` (the computed value, not the config input):
   ```json
   {
     "allocation_min_spend": 500,
     "effective_rank_floor": 720.0
   }
   ```
   Both fields present — `allocation_min_spend` remains for the "Other (untested)" conceptual explanation; `effective_rank_floor` is what the caption should show as the ranking gate.

4. Dead code cleanup: remove the duplicate `ads_out` assignment block (lines 288–297 — the first build of `ads_out` is immediately overwritten by the second at lines 300–310). Keep only the second block.

### Dashboard Changes (`chart_creative_allocation`)

5. Chart caption reads `effective_rank_floor` instead of `allocation_min_spend` for the dollar figure in the ranking gate explanation:
   ```python
   rank_floor = data.get("effective_rank_floor", data.get("allocation_min_spend", 500))
   floor_display = data.get("allocation_min_spend", 500)
   st.caption(
       f"Ranking pool includes only concepts with ≥ ${rank_floor:,.0f} lifetime spend "
       f"(0.5% of total account spend, or ${floor_display:,.0f} minimum — whichever is higher). "
       f"Ads below this threshold are tagged \"Other (untested)\". "
       f"To change the minimum floor — tell the AI: \"rerun /meta-diagnostics with allocation_min_spend = 1000\"."
   )
   ```

6. Backwards compatibility: if `effective_rank_floor` is absent (older `results.json`), fall back to `allocation_min_spend`. Caption renders correctly in both cases.

### Quality Requirements

7. On a real account run: `top_10pct_spend_pct` reflects the spend concentration on the lowest-CPA concepts that have each committed ≥ 0.5% of total account spend
8. Verified: a concept with `spend < 1% of total_spend` never appears as "Top 1%" or "Top 10%"
9. Verified: `effective_rank_floor` in the data dict equals `max(allocation_min_spend, total_spend * 0.01)` — spot-check against account total spend
10. Caption dollar value matches `effective_rank_floor`, not the raw config floor

---

## Technical Notes

**Exact change to `run_a2` pool assignment block:**

```python
total_spend = sum(c['spend'] for c in concept_aggregates_90d.values())
rank_floor = max(allocation_min, total_spend * 0.01)

ranked, sub_threshold, unranked = [], [], []
for name, c in concept_aggregates_90d.items():
    entry = {'name': name, 'spend': c['spend'], 'cpa': c['cpa'],
             'conversions': c['conversions'], 'ad_id_count': c['ad_id_count']}
    if c['cpa'] > 0 and c['conversions'] >= 1 and c['spend'] >= rank_floor:
        ranked.append(entry)
    elif c['cpa'] > 0 and c['conversions'] >= 1:
        sub_threshold.append(entry)
    else:
        unranked.append(entry)
```

**Data dict addition:**

In the `return` dict at the end of `run_a2()`, add `effective_rank_floor` alongside `allocation_min_spend`:
```python
'allocation_min_spend': round(allocation_min, 2),
'effective_rank_floor': round(rank_floor, 2),
```

Also update the `INSUFFICIENT_DATA` early-return dict to include `effective_rank_floor: allocation_min` (since total_spend is unknown at that point, floor = config value).

**Scale examples:**

| Account 90d spend | 0.5% floor | effective_rank_floor (if allocation_min=$500) |
|---|---|---|
| $30,000 | $150 | $500 (allocation_min wins) |
| $72,000 | $360 | $500 (allocation_min wins) |
| $100,000 | $500 | $500 (tied) |
| $150,000 | $750 | $750 |
| $500,000 | $2,500 | $2,500 |
| $1,000,000 | $5,000 | $5,000 |

---

## Definition of Done

- [ ] `rank_floor = max(allocation_min, total_spend * 0.01)` computed in `run_a2()`
- [ ] Ranked pool gate uses `rank_floor` (not `allocation_min`)
- [ ] `effective_rank_floor` emitted in data dict
- [ ] Duplicate `ads_out` block (lines 288–297) removed
- [ ] Dashboard caption reads `effective_rank_floor` with backwards-compatible fallback
- [ ] Verified: no micro-spend concept appears in Top 1% / Top 10% tier
- [ ] `install.sh` re-run after change

---

## Risk and Compatibility Check

**Primary Risk:** On a very small account where total_spend is low, `total_spend * 0.01` may be less than `allocation_min_spend` — in which case `rank_floor = allocation_min_spend` and behavior is identical to pre-fix. No regression risk.

**Secondary Risk:** Old `results.json` files (pre-S10) lack `effective_rank_floor`. Dashboard caption falls back to `allocation_min_spend` — renders correctly, just shows the config floor rather than the computed floor.

- [x] Verdict thresholds unchanged — only the ranked pool population changes
- [x] Tier labels unchanged — "Top 1%", "Top 10%", "Other (untested)", "Other (no conversions)" all preserved
- [x] `dashboard_template.py` change is a caption string update — no chart structure changes
- [x] No SKILL.md changes required
- [x] No new Python dependencies

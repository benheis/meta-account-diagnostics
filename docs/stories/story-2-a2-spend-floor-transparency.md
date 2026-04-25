# Story 2: A2 Ranked Pool Spend Floor + Transparency — Brownfield Fix

**Size:** Medium | **Source:** Round 3 Bug Report, Issue 2 | **Commit baseline:** `a2b391e`

---

## User Story

As a media manager reading the Creative Allocation chart,
I want the Top 10% / Top 1% tiers to reflect concepts where we've actually committed budget,
So that the verdict tells me whether I'm concentrating money on proven winners — not whether a $200 test ad got lucky with one conversion.

---

## Story Context

**Existing System Integration:**
- Integrates with: `SKILL.md` § Analysis 2 (lines 275–306) for spec; `templates/dashboard_template.py` → `chart_creative_allocation()` and `analysis_card()` for rendering
- Technology: Claude LLM (SKILL.md is the analysis runner — no Python runner file exists); Streamlit + Plotly Express bar chart
- Follows pattern: `allocation_min_spend` already exists in SKILL.md config for A1 — same config key reused by A2
- Touch points: SKILL.md spec + dashboard chart function + `analysis_card` helper

**Background:**
Analysis 2 ranks all concepts by CPA ascending with no minimum spend floor. A concept with spend=$200 and CPA=$13 (one lucky conversion) ranks Top 1% and saturates the percentile calculation. The 6 actual scaled winners ($55K–$10K spend, $156–$476 CPA) all fall in "Other" because they can't beat the CPA of statistical outliers. On this account `top_10pct_spend_pct ≈ 2%` even though allocation health is objectively moderate-to-good. The fix gates the ranked pool by `allocation_min_spend` (default $500, already used by A1's Red zone logic), adds two new tier labels for excluded concepts, and surfaces the active threshold visibly in the chart.

**Critical architecture note:** There is no `_run_analyses.py`. The analysis runner is the Claude LLM following SKILL.md. The spec changes in this story update what the LLM computes on the next `/meta-diagnostics` run — no Python analysis code to edit.

---

## Acceptance Criteria

**Functional Requirements:**
1. Ranked pool gate: `CPA > 0 AND conversions ≥ 1 AND spend ≥ allocation_min_spend` (default `$500`; reads from existing config key)
2. Three concept pools with distinct tier labels:
   - **Ranked:** eligible for Top 1%/Top 10% percentile math
   - **`"Other (untested)"`:** CPA > 0 AND conversions ≥ 1 AND spend < allocation_min_spend (converted but under-tested)
   - **`"Other (no conversions)"`:** CPA = 0 or conversions = 0 (no signal)
3. Data dict gains: `sub_threshold_spend_pct` (spend share of untested pool) and `allocation_min_spend` (the active threshold, for chart caption)
4. Per-concept entries in `ads` array gain `conversions` and `ad_id_count` fields (already emitted by A1 and the shared concept map)
5. Verdict thresholds updated:
   - HEALTHY: `top_10pct_spend_pct > 50 AND sub_threshold_spend_pct between 5–25`
   - WARNING: `top_10pct_spend_pct 30–50 OR sub_threshold_spend_pct > 25`
   - CRITICAL: `top_10pct_spend_pct < 30 OR budget_waste_signal > 20% of median CPA`
6. Dashboard chart uses 4-color tier map:
   - Top 1%: `#a855f7` (purple, unchanged)
   - Top 10%: `#6366f1` (indigo, unchanged)
   - Other (untested): `#fbbf24` (amber — new)
   - Other (no conversions): `#d1d5db` (grey, unchanged color, new label)
7. `st.caption()` rendered below chart title, reading floor from `data["allocation_min_spend"]`:
   ```
   Ranking pool includes only concepts with ≥ $500 lifetime spend
   (statistical-significance gate). Ads below this threshold are tagged
   "Other (untested)". To change this floor for your business — e.g. $100
   for low-CAC accounts or $2,000 for high-CAC accounts — tell the AI:
   "rerun /meta-diagnostics with allocation_min_spend = 1000".
   ```
8. Hover on bars exposes `cpa`, `conversions`, `ad_id_count` in addition to existing `tier` and `spend`
9. Dollar signs in all analysis card `meaning` and `action` text render as plain text (not MathJax/LaTeX)

**Integration Requirements:**
10. `analysis_card()` change is global — all 7 analyses benefit from dollar-sign escaping without further changes
11. Existing `"Top 1%"` and `"Top 10%"` bar colors unchanged (visual regression check)
12. `budget_waste_signal` calculation unchanged (spend-weighted avg CPA − unweighted median CPA)

**Quality Requirements:**
13. A2 verdict on `act_748122004521787` flips from CRITICAL to WARNING or HEALTHY after fix
14. Caption dollar value matches `data["allocation_min_spend"]` — verified by changing config to 1000 and confirming caption updates

---

## Technical Notes

**SKILL.md changes (§ Analysis 2):**

Ranked pool definition (replace existing lines 280–282):
```
1. Separate concepts from concept_aggregates_90d into three pools:
   - Ranked pool: CPA > 0 AND conversions ≥ 1 AND spend ≥ allocation_min_spend
   - Sub-threshold: CPA > 0 AND conversions ≥ 1 AND spend < allocation_min_spend.
     Tagged "Other (untested)". Excluded from percentile math.
   - Unranked: CPA = 0 or conversions = 0.
     Tagged "Other (no conversions)". Excluded from percentile math.
```

Data dict additions (extend existing dict at lines 298–305):
```json
{
  "ads": [{"name": "...", "spend": 0.0, "cpa": 0.0, "conversions": 0,
           "ad_id_count": 1, "tier": "Top 1%|Top 10%|Other (untested)|Other (no conversions)"}],
  "top_1pct_spend_pct": 0.0,
  "top_10pct_spend_pct": 0.0,
  "sub_threshold_spend_pct": 0.0,
  "allocation_min_spend": 500,
  "budget_waste_signal": 0.0
}
```

**`dashboard_template.py` — `chart_creative_allocation` changes:**

```python
# Expand tier_color_map
tier_color_map = {
    "Top 1%":                "#a855f7",
    "Top 10%":               "#6366f1",
    "Other (untested)":      "#fbbf24",
    "Other (no conversions)":"#d1d5db",
}
tier_order = ["Top 1%", "Top 10%", "Other (untested)", "Other (no conversions)"]

# Add to px.bar():
category_orders={"tier": tier_order},
hover_data={
    "cpa":         ":$,.0f",
    "conversions": ":.0f",
    "ad_id_count": True,
    "tier":        True,
    "spend":       ":$,.0f",
    "name":        False,
},
labels={..., "cpa": "CPA ($)", "conversions": "Conversions", "ad_id_count": "Ad copies"},

# After st.plotly_chart():
floor = data.get("allocation_min_spend", 500)
st.caption(
    f"Ranking pool includes only concepts with ≥ ${floor:,.0f} lifetime spend "
    f"(statistical-significance gate). Ads below this threshold are tagged "
    f"\"Other (untested)\". To change this floor for your business — e.g. $100 "
    f"for low-CAC accounts or $2,000 for high-CAC accounts — tell the AI: "
    f"\"rerun /meta-diagnostics with allocation_min_spend = 1000\"."
)
```

Note: `df` must include `cpa`, `conversions`, `ad_id_count` columns — guard with `.get()` and fill 0 for backwards compatibility with older `results.json`.

**`dashboard_template.py` — `analysis_card` change (global dollar-sign fix):**

Add `_safe_md()` helper near top of file (alongside `_to_float`, `_fmt_usd`):
```python
def _safe_md(text: str) -> str:
    return text.replace("$", "\\$")
```

In `analysis_card()`, change:
```python
st.markdown(f"**What it means:** {meaning}")
st.markdown(f"**Action:** {action}")
# TO:
st.markdown(f"**What it means:** {_safe_md(meaning)}")
st.markdown(f"**Action:** {_safe_md(action)}")
```

---

## Definition of Done

- [ ] SKILL.md A2 spec updated: ranked pool gate, three tier labels, new data dict fields, updated verdict thresholds
- [ ] `chart_creative_allocation`: 4-color `tier_color_map`, `category_orders`, `hover_data` with cpa+conversions+ad_id_count, `st.caption()` with active floor
- [ ] `_safe_md()` helper added; applied to `meaning` and `action` in `analysis_card()`
- [ ] A2 verdict on `act_748122004521787` reflects scaled-winner allocation, not outlier noise
- [ ] Caption shows `$500` (or current `allocation_min_spend` config value)
- [ ] No MathJax rendering on dollar amounts in any analysis card's meaning/action text
- [ ] All other A2 chart styling (bar sort order, 50% annotation, xaxis hidden ticks) unchanged

---

## Risk and Compatibility Check

**Primary Risk:** SKILL.md spec change affects the LLM's output on the next run — results won't change until user reruns `/meta-diagnostics`. Old `results.json` files (pre-fix) will show `tier: "Other"` for what is now split into `"Other (untested)"` and `"Other (no conversions)"`. The dashboard chart falls back to grey for unknown tiers, so old files degrade gracefully.

**Mitigation:** Guard `cpa`, `conversions`, `ad_id_count` columns in `chart_creative_allocation` with `.get()`/`fillna(0)` so older results render without crash.

**Rollback:** Revert SKILL.md A2 spec lines + 3 localized dashboard changes.

- [x] No breaking changes to existing dashboard rendering (old `"Other"` tier falls through to grey default)
- [x] SKILL.md change is additive (new fields, not removed fields)
- [x] `_safe_md()` is a pure string transformation — safe for all 7 analysis cards
- [x] Performance impact: negligible

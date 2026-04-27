# Story 12: A2 Creative Allocation Chart Visual Overhaul — Brownfield Fix

**Size:** Small | **Source:** Post-PR5 QA — A2 chart rendering confusion | **Commit baseline:** `904ba73`

---

## User Story

As a media manager reading the Creative Allocation chart,
I want bars sorted by spend from largest to smallest with winner tiers highlighted in color and everything else in neutral gray,
So that I can immediately see where my budget is concentrated and which concepts have earned winner status — without decoding a confusing multi-color legend.

---

## Story Context

**Existing System Integration:**
- Modifies: `templates/dashboard_template.py` → `chart_creative_allocation()` (lines 189–252)
- No changes to: `_run_analyses.py`, `SKILL.md`, `install.sh`, any analysis logic or data dict
- Technology: Python, Streamlit, Plotly Express bar chart
- Follows pattern: `_safe_md()` for currency strings (already applied in caption)

**Background:**
Four issues identified from live account screenshot:

1. **Wrong sort order.** `category_orders={"tier": tier_order}` causes Plotly to group bars by tier before rendering — so all tiny-spend Top 1%/Top 10% bars (best CPA, low budget) cluster on the far left, then a jarring cliff up to the huge "Other (ranked)" bars on the right. The df is already sorted by spend descending — removing `category_orders` from `px.bar()` fixes the order.

2. **"Other (ranked)" has no color mapping — defaults to Plotly green.** The `tier_color_map` includes four entries but omits `"Other (ranked)"`, so Plotly assigns its default green (`#2ca02c`). This makes the biggest bars (the bulk of account spend) look like HEALTHY signal, and creates a confusing 5th legend entry that appears unlabeled or mismatched.

3. **Three "Other" categories with alarm colors.** `"Other (untested)"` is amber (warning signal) and `"Other (no conversions)"` is light gray — but neither is meaningfully actionable from the chart. The user's mental model is simple: Top 1%, Top 10%, everything else. All "Other *" tiers should render in neutral gray shades that recede visually, leaving purple and indigo to carry the analytical signal.

4. **Title says "ads" not "concepts."** The chart aggregates multiple ad IDs into one bar per concept name. The title "Top 40 ads by spend" is wrong — it should say "Top 40 ad concepts" and note the aggregation so users understand why the bar count doesn't match their Meta Ads Manager ad count.

---

## Acceptance Criteria

### Sort order

1. Remove `category_orders={"tier": tier_order}` from `px.bar()`. The dataframe is already sorted by spend descending (line 204) — bars will render in spend order across all tiers once grouping is removed.
2. Bars flow left (highest spend) to right (lowest spend) regardless of tier. Top 1%/Top 10% colored bars appear wherever their spend falls in the distribution — often interspersed with gray "Other (ranked)" bars.

### Color map

3. Updated `tier_color_map`:
   ```python
   tier_color_map = {
       "Top 1%":                 "#a855f7",  # purple — unchanged
       "Top 10%":                "#6366f1",  # indigo — unchanged
       "Other (ranked)":         "#9ca3af",  # neutral gray (was missing → Plotly default green)
       "Other (untested)":       "#d1d5db",  # light gray (was amber #fbbf24)
       "Other (no conversions)": "#e5e7eb",  # lightest gray (unchanged tone, lighter shade)
       "Other":                  "#d1d5db",  # backwards compat — pre-S2 results.json
   }
   ```
4. Legend order (for readability — controls legend only, not bar order):
   ```python
   tier_legend_order = ["Top 1%", "Top 10%", "Other (ranked)", "Other (untested)", "Other (no conversions)"]
   ```
   Apply via `fig.update_layout(legend=dict(traceorder="normal"))` after setting trace order with `fig.data` reordering if needed — or simply accept default legend order (tiers appear in the order first encountered in df).

### Title and subtitle

5. Chart title: `f"Top {len(df_top)} ad concepts by spend (of {len(df)} concepts in 90-day window)"`
6. Add `st.caption()` immediately above the chart (before `st.plotly_chart`):
   ```
   Each bar is one ad concept — all ads sharing the same name are aggregated into a single bar.
   ```
   This explains the concept-level aggregation so users aren't confused by the count mismatch with Meta Ads Manager.

### Hover unchanged

7. Hover data unchanged — `cpa`, `conversions`, `ad_id_count`, `tier`, `spend` all still visible on hover. The `tier` field in hover lets users see the exact tier label (e.g. "Other (ranked)") for any gray bar, preserving analytical transparency even though the visual simplifies.

### Quality Requirements

8. No purple or indigo bars hidden behind gray bars — verify z-order is correct (Plotly renders traces in definition order; winner tiers should render on top if overlap occurs at low spend values)
9. Verified: no "Other (ranked)" bars appear in Plotly's default green
10. Verified: the "← you" annotation in the A7 tier table is unaffected (different chart function)

---

## Technical Notes

**The `category_orders` root cause in detail:**

When `px.bar` receives `category_orders={"tier": tier_order}`, Plotly creates one trace per tier value in the specified order. Each trace contains all bars of that tier, positioned along the x-axis in their dataframe order. The visual result: all bars of the first tier (Top 1%) appear leftmost, then Top 10%, then Other (untested), then Other (no conversions), then Other (ranked) (which isn't in `tier_order`) appended at the end — producing the spend-cliff in the screenshot.

Removing `category_orders` collapses all tiers into the dataframe's natural row order (spend descending), with each bar colored by its tier. This is the standard spend-waterfall pattern used in media reporting.

**Exact diff for `chart_creative_allocation`:**

```python
# REMOVE from px.bar():
category_orders={"tier": tier_order},

# UPDATE tier_color_map (replace existing):
tier_color_map = {
    "Top 1%":                 "#a855f7",
    "Top 10%":                "#6366f1",
    "Other (ranked)":         "#9ca3af",
    "Other (untested)":       "#d1d5db",
    "Other (no conversions)": "#e5e7eb",
    "Other":                  "#d1d5db",
}

# UPDATE title string in px.bar():
title=f"Top {len(df_top)} ad concepts by spend (of {len(df)} concepts in 90-day window)",

# ADD before st.plotly_chart():
st.caption("Each bar is one ad concept — all ads sharing the same name are aggregated into a single bar.")
```

**`tier_order` variable:** Can be removed entirely (was only used for `category_orders`). If kept for reference, rename to `tier_legend_order` to be honest about its scope.

---

## Definition of Done

- [ ] `category_orders` removed from `px.bar()`
- [ ] `tier_color_map` updated — `"Other (ranked)"` mapped to `#9ca3af`, `"Other (untested)"` mapped to `#d1d5db`
- [ ] Title updated to "ad concepts"
- [ ] Aggregation caption added above chart
- [ ] Verified: bars sort by spend descending across all tiers
- [ ] Verified: no green bars (Plotly default) visible — all "Other (ranked)" bars are gray
- [ ] Verified: Top 1%/Top 10% purple/indigo bars visible at their correct spend position
- [ ] No changes outside `chart_creative_allocation()`

---

## Risk and Compatibility Check

**Primary Risk:** Removing `category_orders` changes bar order — users who ran `/meta-diagnostics` before this fix will see a different bar sequence on refresh. This is the intended behavior (correctness fix).

**Mitigation:** The 50%-of-spend annotation adjusts automatically since it reads from the sorted df, not position.

**Backwards compatibility:** `"Other"` key retained in `tier_color_map` for pre-S2 `results.json` files that used the old tier label.

- [x] No changes to `_run_analyses.py` — data dict unchanged
- [x] No changes to `SKILL.md`
- [x] Hover data unchanged — full tier label still visible on hover
- [x] `_safe_md()` already applied to caption — no new escaping needed

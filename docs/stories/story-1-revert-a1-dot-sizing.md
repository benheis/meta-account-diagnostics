# Story 1: Revert A1 Scatter Variable Dot Sizing — Brownfield Fix

**Size:** Small | **Source:** Round 3 Bug Report, Issue 1 | **Commit baseline:** `a2b391e`

---

## User Story

As a media manager reading the Test & Learn scatter chart,
I want all concept dots to render at a uniform size,
So that I can compare zone colors (Red/Green/Purple) without large bubbles obscuring small-spend winners.

---

## Story Context

**Existing System Integration:**
- Integrates with: `templates/dashboard_template.py` → `chart_test_and_learn()` (lines 79–109)
- Technology: Python, Streamlit, Plotly Express (`px.scatter`)
- Follows pattern: existing `hover_data` pattern already in the function
- Touch points: single function, no data dict changes required

**Background:**
PR 2 added `size="conversions", size_max=24` to encode conversion volume as bubble radius. The intent was to expose conversion data visually, but conversions are derived from `spend ÷ CPA` — collinear with the two axes already on the chart. The result: large-spend concepts render as giant blobs that crowd the Purple winner cluster (which tends to be lower-spend, earlier-stage concepts the analyst most needs to see). The fix keeps conversions in the tooltip, removes them from visual encoding.

---

## Acceptance Criteria

**Functional Requirements:**
1. All concept dots render at uniform diameter (`size=10`, `opacity=0.75`)
2. Conversions remain visible in the hover tooltip (no data removed, only visual encoding changed)
3. No other changes to the chart (axes, color zones, log scale, hover fields all unchanged)

**Integration Requirements:**
4. `hover_data` dict unchanged — `conversions`, `ad_id_count`, `spend`, `cpa`, `name` all still present
5. Guard logic for missing `conversions` field (older `results.json`) remains in place
6. `zone_color_map` and all other rendering parameters unchanged

**Quality Requirements:**
7. No regression in A1 scatter rendering for any zone (Red/Green/Purple)
8. Visually verified: Purple winner cluster is legible alongside high-spend Green/Red dots

---

## Technical Notes

**Exact change — `chart_test_and_learn` in `dashboard_template.py`:**

```python
# REMOVE these two params from px.scatter():
size="conversions",
size_max=24,

# CHANGE update_traces call from:
fig.update_traces(marker=dict(opacity=0.8))
# TO:
fig.update_traces(marker=dict(size=10, opacity=0.75))
```

**Key Constraint:** The conversions guard block above `px.scatter()` must remain intact — it fills missing `conversions` with 1 for backwards compatibility with older `results.json` files. Even though conversions are no longer used for sizing, the field is still referenced in `hover_data`.

**Existing Pattern Reference:** `chart_creative_allocation` uses a fixed bar chart with no dynamic sizing — same philosophy that position/color carry the analytical load.

---

## Definition of Done

- [ ] `size="conversions"` and `size_max=24` removed from `px.scatter()` call
- [ ] `fig.update_traces(marker=dict(size=10, opacity=0.75))` in place
- [ ] Conversions still appear in tooltip on hover
- [ ] Verified on `act_748122004521787` — Purple cluster legible, no visual crowding
- [ ] No other chart functions modified

---

## Risk and Compatibility Check

**Primary Risk:** None — pure visual regression to prior state. No data dict changes, no downstream effects.
**Mitigation:** N/A
**Rollback:** Revert 2-line change in `chart_test_and_learn`.

- [x] No breaking changes to existing APIs
- [x] No data dict changes
- [x] UI change is a strict simplification
- [x] Performance impact: negligible (removes computation, not adds)

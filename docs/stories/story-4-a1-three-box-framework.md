# Story 4: A1 Three-Box Framework Visual Overhaul — Brownfield Fix

**Size:** Large | **Source:** Round 3 Bug Report, Issue 4 | **Commit baseline:** `a2b391e`

> **Escalation note:** This story has three coordinated parts (zone redefinition in SKILL.md, data dict additions, chart rendering overhaul in dashboard_template.py). If the chart rendering scope grows beyond the described changes, split into `story-4a` (SKILL.md zone + data dict) and `story-4b` (dashboard rendering).

---

## User Story

As a media manager reading the Test & Learn chart,
I want to see the Three-Box Framework drawn as actual regions on the scatter — with per-zone spend and conversion concentrations shown as headline numbers,
So that I (and any first-time viewer) can immediately read whether budget is concentrating in Purple winners, and understand how to interpret and act on what I see.

---

## Story Context

**Existing System Integration:**
- Integrates with: `SKILL.md` § Analysis 1 (lines 229–271) for zone definitions + data dict; `templates/dashboard_template.py` → `chart_test_and_learn()` (lines 79–109) for rendering
- Technology: Claude LLM (SKILL.md is the analysis runner); Streamlit + Plotly (graph_objects `add_shape`, `add_hline`, `add_annotation`)
- Follows pattern: `_safe_md()` from Story 2 for dollar-sign escaping; `_to_float()` / `_fmt_usd()` pattern for currency formatting; `box_thresholds` dict pattern mirrors `allocation_min_spend` from Story 2
- Touch points: SKILL.md A1 zone logic + data dict; `chart_test_and_learn` in dashboard_template.py

**Background:**
Analysis 1 ostensibly evaluates the Three-Box Test & Learn Framework, but:
1. Purple zone is defined as "lowest-CPA 10% by count" — same statistical-noise bias fixed in A2 (single-conversion outliers dominate). On this account, Purple holds 4 tiny-budget concepts ($4K total) while the actual scaled winners ($55K, $34K, $20K…) are tagged Green.
2. The framework boxes aren't drawn — just colored dots with a legend.
3. Per-zone concentration (count · spend% · conversions%) isn't shown.

The fix redefines zones using coordinate-based thresholds derived from the account's own spend distribution (percentile-based, not hardcoded), then overlays the boxes on the scatter and adds concentration cards above the chart.

**Critical architecture note:** There is no `_run_analyses.py`. Zone redefinition is a SKILL.md instruction change — no Python analysis code to write.

---

## Acceptance Criteria

### Zone Redefinition (SKILL.md)

1. Before zone assignment, compute two spend thresholds from `concept_aggregates_90d` so they adapt to account size:
   ```
   concept_spends = sorted list of all concept spend values from concept_aggregates_90d

   testing_max_spend = max(allocation_min_spend,  P25 of concept_spends)
   scaled_min_spend  = P75 of concept_spends
   red_cpa_multiple  = 2.0  (unchanged)
   median_cpa        = P50 of concept CPA in concept_aggregates_90d  (already computed)
   ```
2. Zone assignment (first match wins):
   ```
   Red:    concept_spend ≥ testing_max_spend  AND  cpa ≥ red_cpa_multiple × median_cpa
   Purple: concept_spend ≥ scaled_min_spend   AND  0 < cpa ≤ median_cpa
   Green:  concept_spend < testing_max_spend  AND  (cpa = 0 OR cpa ≤ median_cpa)
   Unzoned: everything else — visible on chart in neutral grey, excluded from concentration math
   ```
3. On `act_748122004521787`: Purple should contain the 6 scaled-winner concepts ($55K, $34K, $20K, $16K, $15K, $11K spend), not the 4 tiny-spend outliers
4. Thresholds scale correctly: a $1M/day account's P75 is ~$50K+ (not $5K); a $10K/month account's P75 is ~$500

### Data Dict Additions (SKILL.md)

5. `zone_concentration` block added to A1 data dict:
   ```json
   "zone_concentration": {
     "purple":  {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
     "red":     {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
     "green":   {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
     "unzoned": {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0}
   }
   ```
6. `box_thresholds` block added (emits the *computed* values, not config inputs):
   ```json
   "box_thresholds": {
     "testing_max_spend": 0.0,
     "scaled_min_spend":  0.0,
     "red_cpa_multiple":  2.0,
     "median_cpa":        0.0
   }
   ```

### Chart Rendering (dashboard_template.py)

7. **Concentration cards above scatter:** three `st.columns(3)` cards (Purple / Green / Red). Each card:
   - Zone-colored header dot + zone name + sub-label (Purple: "high spend · low CPA", Green: "testing zone", Red: "scaled loser")
   - Headline triplet: `<N> concepts · <X>% of spend · <Y>% of conv`
   - Data reads from `zone_concentration`; gracefully omits if absent (older results.json)
8. **Zone rectangles on scatter:** semi-transparent `add_shape` rectangles at `box_thresholds` boundaries:
   - Purple region: `x0=scaled_min_spend, x1=x_max_data, y0=0, y1=median_cpa` (fill: `#a855f7`, opacity=0.09)
   - Red region: `x0=testing_max_spend, x1=x_max_data, y0=median_cpa × red_cpa_multiple, y1=y_max_data` (fill: `#ef4444`, opacity=0.09)
   - Green region: `x0=1 (log-safe floor), x1=testing_max_spend, y0=0, y1=median_cpa` (fill: `#22c55e`, opacity=0.06)
   - Note: chart uses `log_x=True` — x-coordinates are in linear data space; `x0` must be > 0 for leftmost box (use `1` as safe floor)
9. **Horizontal reference line at median_cpa:** dashed line across the full scatter at `y=median_cpa`, annotated "Median CPA"
10. **Zone annotations inside rectangles:** lightweight text inside each colored region ("PURPLE — feed / scale" / "RED — kill" / "GREEN — test / graduate")
11. **Caption below scatter:** explains the Three-Box Framework + shows computed thresholds + AI-config CTA:
    ```
    Three-Box Framework: Purple = high-spend, low-CPA scaled winners (feed them).
    Green = testing zone (graduate winners, kill losers). Red = scaled losers (kill them).
    Thresholds auto-calibrated to this account: testing floor = $X, scaled floor = $Y, CPA cutoff = $Z.
    To override: tell the AI "rerun /meta-diagnostics with scaled_min_spend = 10000".
    ```
    Dollar values escaped with `_safe_md()` to prevent Streamlit MathJax.
12. **Unzoned concepts:** neutral grey `#9ca3af` — add to `zone_color_map`

**Integration Requirements:**
13. Existing `hover_data` (name, conversions, ad_id_count, spend, cpa) unchanged
14. Log X axis and all existing axis labels unchanged
15. If `box_thresholds` or `zone_concentration` absent from data dict (older results.json), scatter renders in legacy mode (no rectangles, no concentration cards) without crash

**Quality Requirements:**
16. Purple zone on `act_748122004521787` shows 6 concepts with >60% of account spend
17. Zone rectangles visible and correctly bounded — Purple box does not extend into Red territory
18. Log-axis rectangle rendering verified: leftmost Green box x0=1 does not cause Plotly error

---

## Technical Notes

**Plotly `add_shape` on log-x scatter:**
```python
thresholds = data.get("box_thresholds", {})
testing_max = thresholds.get("testing_max_spend", 500)
scaled_min  = thresholds.get("scaled_min_spend", 5000)
median_cpa  = thresholds.get("median_cpa", 0)
red_cpa     = median_cpa * thresholds.get("red_cpa_multiple", 2.0)
x_max       = df["spend"].max() * 2   # headroom beyond largest dot

# Green box (log-safe: x0 must be > 0)
fig.add_shape(type="rect", x0=1, x1=testing_max, y0=0, y1=median_cpa,
              fillcolor="#22c55e", opacity=0.06, line_width=0, layer="below")

# Purple box
fig.add_shape(type="rect", x0=scaled_min, x1=x_max, y0=0, y1=median_cpa,
              fillcolor="#a855f7", opacity=0.09, line_width=0, layer="below")

# Red box
fig.add_shape(type="rect", x0=testing_max, x1=x_max, y0=red_cpa, y1=df["cpa"].max() * 1.3,
              fillcolor="#ef4444", opacity=0.09, line_width=0, layer="below")

# Median CPA line
fig.add_hline(y=median_cpa, line_dash="dot", line_color="#6b7280",
              annotation_text=f"Median CPA (${median_cpa:,.0f})", annotation_position="bottom right")
```

**Concentration cards:**
```python
zone_conc = data.get("zone_concentration", {})
if zone_conc:
    cols = st.columns(3)
    zone_display = [
        ("purple", "#a855f7", "Purple — Scale", "high spend · low CPA"),
        ("green",  "#22c55e", "Green — Test",   "testing zone"),
        ("red",    "#ef4444", "Red — Kill",     "scaled loser"),
    ]
    for col, (zone_key, color, label, sublabel) in zip(cols, zone_display):
        z = zone_conc.get(zone_key, {})
        with col:
            st.markdown(f"<span style='color:{color}'>●</span> **{label}**", unsafe_allow_html=True)
            st.caption(sublabel)
            st.markdown(
                f"**{z.get('count', 0)} concepts** · "
                f"**{z.get('spend_pct', 0):.0f}% of spend** · "
                f"**{z.get('conversions_pct', 0):.0f}% of conv**"
            )
```

**`zone_color_map` update:**
```python
zone_color_map = {
    "Red":     "#ef4444",
    "Green":   "#22c55e",
    "Purple":  "#a855f7",
    "Unzoned": "#9ca3af",
}
```

---

## Definition of Done

- [ ] SKILL.md A1: percentile-based threshold computation documented (`testing_max_spend = max(allocation_min_spend, P25)`, `scaled_min_spend = P75`); coordinate-based zone definitions with `Unzoned` category; `zone_concentration` and `box_thresholds` in data dict
- [ ] `chart_test_and_learn`: concentration cards above scatter (reads `zone_concentration`); zone rectangles + median line on scatter (reads `box_thresholds`); caption below scatter; `Unzoned` in `zone_color_map`
- [ ] Legacy mode verified: chart renders without crash when `box_thresholds`/`zone_concentration` absent
- [ ] Purple zone on `act_748122004521787` = 6 scaled-winner concepts (>60% of spend), not 4 tiny-budget outliers
- [ ] Zone rectangles correctly bounded; Purple box does not overlap Red region
- [ ] No MathJax on dollar amounts in caption (uses `_safe_md()` from Story 2)

---

## Risk and Compatibility Check

**Primary Risk:** Percentile-based thresholds change zone assignments relative to current run — this is the intended behavior (correctness fix), but users reviewing old vs new results will see different zone labels for the same concepts.

**Mitigation:** The `box_thresholds` in the data dict makes the new boundaries transparent — chart caption shows exactly where the lines are. Users can see why assignments changed.

**Rollback:** Revert SKILL.md A1 zone definition section + revert `chart_test_and_learn` additions. Old `results.json` files with the legacy Purple definition render without issue in legacy mode.

- [x] `box_thresholds` / `zone_concentration` absent → chart degrades gracefully (no rectangles, no cards), no crash
- [x] `"Unzoned"` key addition to `zone_color_map` is additive — safe if no dots are tagged Unzoned
- [x] Log-axis x0=1 is a safe floor (never a real concept spend value)
- [x] `_safe_md()` reuse from Story 2 — no duplication if Stories 2 and 4 ship together
- [x] No changes to verdict thresholds (existing HEALTHY/WARNING/CRITICAL math unchanged)

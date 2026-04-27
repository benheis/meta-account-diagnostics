# Story 11: A7 MathJax Escape + Global Audit — Brownfield Fix

**Size:** Small | **Source:** Post-PR5 QA — Issue 2, A7 tier table LaTeX rendering | **Commit baseline:** `9ed1372`

---

## User Story

As a media manager reading the Creative Volume analysis,
I want the spend tier reference table to display currency ranges as plain text,
So that `$10K–$50K` reads as a dollar range — not as broken italic math output.

---

## Story Context

**Existing System Integration:**
- Primary fix: `templates/dashboard_template.py` → `chart_volume_vs_spend()` (lines 593–599) — tier table row assembly
- Durable fix: audit all `st.markdown` / `st.caption` / `st.table` call sites in `dashboard_template.py` that render user-data strings, routing currency values through existing `_safe_md()` helper
- Technology: Python, Streamlit — `st.table` renders cell content through markdown, which interprets `$...$` as LaTeX inline math
- Follows pattern: `_safe_md()` already defined at line 37 and already applied in `analysis_card()` (lines 79–80), `chart_test_and_learn` caption (line 179), and the A2 chart caption (line 247)

**Background:**
Spend tier range strings (`<$10K`, `$10K–$50K`, `$10K–$200K`, etc.) contain paired `$` characters. Streamlit's `st.table` passes cell content through its markdown renderer, which matches `$...$` as LaTeX inline math — producing italic-math output with the leading `$` dropped. This is the 4th instance of the same MathJax-escape issue (previously fixed in A1 meaning/action copy, A2 analysis card copy, and the A1 Three-Box Framework caption). The point fix is one line in `chart_volume_vs_spend`; the durable fix is a call-site audit to prevent a 5th recurrence.

**`_safe_md()` already exists** at line 37:
```python
def _safe_md(text: str) -> str:
    """Escape dollar signs so Streamlit doesn't render them as MathJax/LaTeX."""
    return text.replace("$", "\\$")
```
No new helper needed — the audit applies the existing function consistently.

---

## Acceptance Criteria

### Point Fix — `chart_volume_vs_spend` tier table

1. `spend_range` value is passed through `_safe_md()` before being composed into the "Spend tier" cell string:
   ```python
   for row in tier_table:
       marker = " ← you" if row.get("is_current") else ""
       spend_range = _safe_md(str(row.get("spend_range", "")))
       rows.append({
           "Spend tier": f"{row['tier']} ({spend_range}){marker}",
           f"{vertical} median (monthly)": f"{row['median_monthly']:.0f}" if row.get('median_monthly') else "—",
       })
   st.table(rows)
   ```
2. Tier table renders `Small ($10K–$50K/month)`, `Medium ($50K–$200K/month)`, etc. — dollar signs visible, no italic-math styling

### Durable Fix — Call-site audit

3. Audit every `st.markdown`, `st.caption`, and `st.table` call in `dashboard_template.py` that renders a **user-data string** (not a hardcoded label). Apply `_safe_md()` at any site that could receive a `$` character:
   - `chart_volume_vs_spend` title string at line 566: `tier_range` may contain `$` — wrap: `_safe_md(tier_range)`
   - `chart_volume_vs_spend` bar label at line 552: `tier_range` embedded in `f"..."` — wrap: `_safe_md(tier_range)`
   - `render_data_quality_card`: `st.markdown(f"**Combined spend: ${combined:,.0f}**...")` at line 619 — `${combined:,.0f}` is a formatted float, not a user string, but the `$` is literal — escape it: `f"**Combined spend: \\${combined:,.0f}**"`
   - Any other `st.caption` that embeds `run_rate_str` or currency-formatted values — verify or wrap

4. Call sites that render **hardcoded labels only** (e.g. `"🔴 CRITICAL — do this week"`, `"Source: Motion 2026"`) do not need `_safe_md()` — no change.

5. Call sites already protected (confirmed safe — no action):
   - `analysis_card()` lines 79–80: already uses `_safe_md(meaning)` and `_safe_md(action)`
   - `chart_test_and_learn` caption line 179: already wrapped in `_safe_md(...)`
   - `chart_creative_allocation` caption lines 247–252: already uses `_safe_md` indirectly (no `$` in f-string template; dollar amounts are `${floor:,.0f}` literals)

**Note on `st.caption` with f-strings:** Streamlit captions also run through markdown. Any `${value:,.0f}` in an f-string produces a literal `$` before the number — this is safe as long as there's only one `$` (no closing `$` to form a pair). Paired `$` in a single string is the trigger. Audit for pairs specifically.

### Quality Requirements

6. Verified: A7 tier table renders with visible dollar signs in all tier range cells
7. Verified: "← you" marker row renders correctly alongside escaped range
8. Verified: no regression in A1, A2, A4 captions (already-fixed sites)

---

## Technical Notes

**Exact change to tier table loop (lines 593–599):**

```python
# Before
for row in tier_table:
    marker = " ← you" if row.get("is_current") else ""
    rows.append({
        "Spend tier": f"{row['tier']} ({row['spend_range']}){marker}",
        ...
    })

# After
for row in tier_table:
    marker = " ← you" if row.get("is_current") else ""
    spend_range = _safe_md(str(row.get("spend_range", "")))
    rows.append({
        "Spend tier": f"{row['tier']} ({spend_range}){marker}",
        ...
    })
```

**Chart title and bar label (lines 552, 566):**
```python
# Before
f"{window_label} vs Motion 2026 benchmarks · {tier} tier ({tier_range})"
f"{vertical} Median<br>{tier_range} cohort"

# After
f"{window_label} vs Motion 2026 benchmarks · {tier} tier ({_safe_md(tier_range)})"
f"{vertical} Median<br>{_safe_md(tier_range)} cohort"
```

**`render_data_quality_card` combined spend line (line 619):**
```python
# Before
st.markdown(f"**Combined spend: ${combined:,.0f}** · _{evidence}_")

# After
st.markdown(f"**Combined spend: \\${combined:,.0f}** · _{evidence}_")
```

---

## Definition of Done

- [ ] `spend_range` escaped through `_safe_md()` in `chart_volume_vs_spend` tier table loop
- [ ] `tier_range` escaped in chart title string and bar label
- [ ] `render_data_quality_card` combined spend `$` escaped
- [ ] Audit of remaining `st.markdown` / `st.caption` / `st.table` call sites complete — no unprotected paired `$` remaining
- [ ] Verified: A7 tier table shows dollar signs, no LaTeX italic rendering
- [ ] No regression in A1/A2/A4 rendering

---

## Risk and Compatibility Check

**Primary Risk:** None — `_safe_md()` is a pure string transformation already in use across the file. Applying it to additional call sites has no side effects.

**Rollback:** Revert the 3–5 line changes in `dashboard_template.py`. Old `results.json` files unaffected.

- [x] No changes to `_run_analyses.py`, `SKILL.md`, or `install.sh`
- [x] No data dict changes
- [x] `_safe_md()` already tested implicitly by existing A1/A2 card rendering
- [x] `st.table` with escaped strings renders identically to unescaped — backslash is consumed by markdown, not displayed

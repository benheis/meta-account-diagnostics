# Story 15: X-Axis Label Audit — Brownfield Fix

**Size:** Small | **Commit baseline:** `4f696fe`

## User Story
As a media manager reading any chart,
I want every axis to be labeled so I know what I'm looking at without guessing.

## Acceptance Criteria
1. A4 Creative Churn stacked area chart: x-axis labeled "Month" (currently has `type="category"` but no `title`)
2. A6 Rolling Reach bar chart: x-axis labeled "Month"
3. All other charts: verify labels present — no changes if already labeled

## Technical Notes
Additions to `fig.update_layout()` in the relevant chart functions:
- `chart_creative_churn`: add `xaxis=dict(type="category", title="Month")`
- `chart_rolling_reach`: add `xaxis_title="Month"` to layout

## Definition of Done
- [ ] A4 x-axis labeled
- [ ] A6 x-axis labeled
- [ ] Audit of remaining 5 charts complete — no unlabeled axes

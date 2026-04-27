# Story 14: Chart Interpretation Captions A4–A7 — Brownfield Fix

**Size:** Small | **Commit baseline:** `4f696fe`

## User Story
As a media manager reading any analysis chart,
I want a brief gray caption explaining how to interpret what I'm looking at,
So that I don't need prior knowledge of the framework to understand the signal.

## Acceptance Criteria
1. **A4 Creative Churn** — caption above chart:
   "Newer cohorts should progressively take spend share from older ones as they prove out. If older cohorts continue dominating month after month, creative is aging without replacement — a leading indicator of audience fatigue."

2. **A5 Hit Rate** — caption already has a hit-rate definition line; add a second interpretive caption below the chart:
   "A healthy account consistently produces new winners each month. Declining hit rate or zero winners for 2+ months signals the current creative direction isn't working — brief new angles, don't iterate on what's failing."

3. **A6 Rolling Reach** — caption above chart:
   "Two signals detect audience saturation: (1) rising cost to reach a net-new person, and (2) declining share of reach going to people who haven't seen your ads before. Either signal alone is a warning; both together is critical."

4. **A7 Creative Volume** — caption above the bar chart (before `st.plotly_chart`):
   "Your launch volume compared against Motion's 2026 benchmarks for your vertical × spend tier. The median bar is your baseline — being below it means competitors at your spend level are testing faster."

## Technical Notes
- All four are `st.caption()` additions inside existing chart functions
- No data dict changes, no _run_analyses.py changes

## Definition of Done
- [ ] Caption added to chart_creative_churn()
- [ ] Interpretive caption added below chart in chart_slugging_rate()
- [ ] Caption added to chart_rolling_reach()
- [ ] Caption added to chart_volume_vs_spend()

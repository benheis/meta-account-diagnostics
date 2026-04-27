# Story 13: Priority Action Stack to Top — Brownfield Fix

**Size:** Small | **Commit baseline:** `4f696fe`

## User Story
As a media manager opening the dashboard,
I want to see the most important actions immediately — before scrolling through 7 analysis cards,
So that I can act on findings without reading every detail first.

## Acceptance Criteria
1. `priority_action_stack(analyses)` renders immediately after the account header/subheader, before any analysis card
2. Removed from the bottom of the page — top-only, no duplication
3. Data quality card (`render_data_quality_card`) remains below all analysis cards (it is supplementary, not immediately actionable)

## Technical Notes
In `main()`, move the `priority_action_stack(analyses)` call from after `render_data_quality_card` to immediately after `st.subheader(...)`. Remove from the bottom.

## Definition of Done
- [ ] Priority Action Stack renders at top before analysis cards
- [ ] No duplicate stack at bottom
- [ ] Data quality card position unchanged (below analysis cards)

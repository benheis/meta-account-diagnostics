# Story 16: Dark Mode Legibility — Brownfield Fix

**Size:** Small | **Commit baseline:** `4f696fe`

## User Story
As a media manager using Streamlit's dark mode,
I want all analysis cards and text to be legible,
So that I can read the dashboard comfortably without switching to light mode.

## Root Cause
`analysis_card()` wraps each card in a raw HTML `<div>` with hardcoded light pastel backgrounds
(`#f0fdf4`, `#fffbeb`, `#fef2f2`, `#f3f4f6`). In dark mode these render as jarring bright patches.
The `h3` title inside the div also loses dark mode text color since Streamlit's theme doesn't
cascade into raw HTML. The border `#e5e7eb` is near-invisible against a dark background.

## Acceptance Criteria
1. Inject a `<style>` block in `main()` (via `st.markdown(..., unsafe_allow_html=True)`) with
   `@media (prefers-color-scheme: dark)` overrides:
   - `.verdict-card` background: dark semi-transparent tints instead of light pastels
     - CRITICAL: `rgba(239,68,68,0.15)`
     - WARNING: `rgba(245,158,11,0.15)`
     - HEALTHY: `rgba(34,197,94,0.15)`
     - INSUFFICIENT_DATA: `rgba(107,114,128,0.15)`
   - `.verdict-card` border: `rgba(255,255,255,0.12)`
   - `.verdict-card h3`: `color: #f1f5f9` (near-white)

2. Add `class="verdict-card verdict-{verdict.lower()}"` to the outer div in `analysis_card()`
   so the CSS rules can target by verdict type

3. Data quality card (`render_data_quality_card`) border/background: add matching dark mode
   override so it doesn't appear as a bright white block

## Technical Notes
```python
DARK_MODE_CSS = """
<style>
@media (prefers-color-scheme: dark) {
    .verdict-card { border-color: rgba(255,255,255,0.12) !important; }
    .verdict-card h3 { color: #f1f5f9 !important; }
    .verdict-critical { background: rgba(239,68,68,0.15) !important; }
    .verdict-warning  { background: rgba(245,158,11,0.15) !important; }
    .verdict-healthy  { background: rgba(34,197,94,0.15)  !important; }
    .verdict-insufficient_data { background: rgba(107,114,128,0.15) !important; }
}
</style>
"""
```
Inject at top of `main()`. Update `analysis_card()` div to include the class attributes.

## Definition of Done
- [ ] CSS block injected in main()
- [ ] analysis_card() div has verdict-specific class
- [ ] In dark mode: card backgrounds are dark tints, not light pastels
- [ ] In dark mode: h3 titles legible (near-white)
- [ ] Light mode: no visual regression (media query only fires in dark mode)

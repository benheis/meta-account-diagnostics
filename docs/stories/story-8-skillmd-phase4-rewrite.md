# Story 8: SKILL.md Phase 4 + Phase 5 Rewrite — LLM as Interpreter — Brownfield Refactor

**Size:** Medium | **Source:** Architecture Review (Hybrid Compute Architecture) | **Commit baseline:** `f5b69a3`

> **Dependencies:** Stories 5, 6, and 7 must all be complete before implementing this story. Story 7's `computed.json` is the input to the Phase 4 instructions written here.

---

## User Story

As the LLM executing `/meta-diagnostics`,
I want Phase 4 to tell me to run the compute script and then write copy around the results — not to compute percentiles and medians myself —
So that the diagnostic produces correct numbers on any account size, and my job is interpretation, not arithmetic.

---

## Story Context

**Existing System Integration:**
- Modifies: `SKILL.md` Phase 4 (Analyses) and Phase 5 (Write Outputs)
- Preserves: All data dict schemas (shapes unchanged — computed.json matches them exactly)
- Preserves: Tone, verdict copy templates, action guidance language
- Removes: All per-analysis arithmetic instructions (percentile computation, zone assignment steps, signal formulas, cohort math)
- Touch points: SKILL.md Phase 4 header + Shared Step + all 7 analysis sections + Data Quality Pass + Phase 5 Step 1

**Background:**
Phase 4 currently instructs the LLM to build concept maps, compute percentiles, assign zones, calculate signals, and run the LCP data quality pass — all in-context. This is unreliable at scale and produces inconsistent results between runs. Story 7 moves all of this to `_run_analyses.py`. This story rewrites Phase 4 to: (1) locate and run the compute script, (2) read `computed.json`, (3) write meaning/action copy for each analysis based on the computed verdict and data, (4) write the markdown report. Phase 5 Step 1 is updated to merge computed.json with the LLM's copy into the final results.json.

The verdict copy templates and tone guidelines are the LLM's primary value-add — these are retained and improved with more explicit guidance for each verdict state.

---

## Acceptance Criteria

### Phase 4 Header (replaces Shared Step + all 7 analysis sections)

1. **Phase 4 begins with a locate-and-run instruction:**
   ```
   PHASE 4 — COMPUTE + INTERPRET

   Step 1 — Locate the compute script:
   The file `_run_analyses.py` is in the same directory as this SKILL.md.
   To find it, run: find ~/.claude -name "_run_analyses.py" -path "*/meta-diagnostics/*" | head -1

   Step 2 — Run the compute script:
   python3 <script_path> \
     --skill-dir <directory containing this SKILL.md> \
     --raw-dir ~/meta-diagnostics/raw \
     --config ~/.meta-diagnostics-config.json \
     --output ~/meta-diagnostics/computed.json

   If the script exits with an error, surface it to the user and stop.
   If the script succeeds, confirm: "Analysis computed. Writing interpretation..."

   Step 3 — Read computed.json:
   Load ~/meta-diagnostics/computed.json. This file contains all 7 analyses with:
   - verdict (HEALTHY / WARNING / CRITICAL / INSUFFICIENT_DATA) — already determined by Python
   - data dict — all numeric fields already computed
   - meaning and action — empty strings that YOU fill in now
   ```

2. **The Shared Step section is removed** from Phase 4. Concept map building, canonical normalization, and data pull references are handled by `_run_analyses.py`. Replace with: "All data preparation and computation is handled by `_run_analyses.py`. Phase 4 begins after computed.json is written."

3. **A single verdict precedence rule** appears once, at the top of the interpretation instructions: "The verdict for each analysis is already set in computed.json — do not recompute it. Your job is to write meaning and action copy that accurately reflects the verdict and the specific numbers in the data dict."

### Per-Analysis Interpretation Instructions

For each of the 7 analyses, retain the following (remove everything else):
- The verdict copy templates (meaning / action per HEALTHY / WARNING / CRITICAL state)
- The `metrics` table spec (what key numbers to include in the markdown report)
- Any analysis-specific tone notes

The computation steps (numbered arithmetic instructions) are fully removed.

4. **Analysis 1 — Test & Learn** interpretation section:
   - Read `winner_spend_pct`, `red_spend_pct`, `testing_budget_pct`, `zone_concentration` from data dict.
   - Meaning copy: reference the specific percentages. For CRITICAL: name the `red_spend_pct` explicitly. For HEALTHY: confirm winner concentration and testing balance.
   - Action copy: for WARNING/CRITICAL, name the specific action (pause Red zone, reallocate to Purple) and reference the `box_thresholds.testing_max_spend` and `box_thresholds.scaled_min_spend` values so the user knows the dollar thresholds.
   - Metrics table: red_spend_pct, winner_spend_pct, testing_budget_pct, purple concept count, red concept count.

5. **Analysis 2 — Creative Allocation** interpretation section:
   - Read `top_10pct_spend_pct`, `sub_threshold_spend_pct`, `budget_waste_signal`, `allocation_min_spend` from data dict.
   - Meaning copy: reference top_10pct_spend_pct and whether budget is concentrated on winners.
   - Action copy: for WARNING, identify whether the problem is too little winner concentration or too much in the untested pool. For CRITICAL, name specific actions.
   - Metrics table: top_1pct_spend_pct, top_10pct_spend_pct, sub_threshold_spend_pct, budget_waste_signal, allocation_min_spend.

6. **Analysis 3 — Old Creative** interpretation section:
   - Read `old_creative_spend_pct` from data dict.
   - Meaning copy: state the percentage of budget on aging/old creative. For CRITICAL, note that refreshing creative is urgent.
   - Metrics table: old_creative_spend_pct.

7. **Analysis 4 — Creative Churn** interpretation section:
   - Read `avg_cohort_half_life_weeks`, `monthly_launches` (last 3 months), launch trend direction from data dict.
   - Meaning copy: name the avg_cohort_half_life_weeks and trend direction.
   - Metrics table: avg_cohort_half_life_weeks, last 3 months' launch counts, trend direction.
   - Note any `data_warnings` from computed.json in the meaning if present.

8. **Analysis 5 — Slugging Rate** interpretation section:
   - Read `recent_avg_hit_rate`, `prior_avg_hit_rate`, `motion_benchmark`, `spend_tier`, `winner_top_percentile` from data dict.
   - Meaning copy: compare recent_avg to motion_benchmark explicitly. For INSUFFICIENT_DATA, explain what's needed.
   - Action copy: for CRITICAL with zero winners, the action must be specific — "brief 5 net-new angles."
   - Metrics table: recent_avg_hit_rate, motion_benchmark, spend_tier, prior_avg_hit_rate.

9. **Analysis 6 — Rolling Reach** interpretation section:
   - Read `signal_a_fired`, `signal_b_fired`, `prior_avg_cost_pnn`, `recent_avg_cost_pnn`, `using_fallback` from data dict.
   - Meaning copy: for INSUFFICIENT_DATA (all fallback), explain the limitation clearly without alarming the user.
   - Note `calculation_note` from data dict in the report.
   - Metrics table: signal_a_fired, signal_b_fired, prior_avg_cost_pnn, recent_avg_cost_pnn.

10. **Analysis 7 — Creative Volume** interpretation section:
    - Read `avg_monthly_launches`, `motion_median_monthly`, `motion_top_quartile_monthly`, `tier`, `vertical` from data dict.
    - Meaning copy: state avg vs. median benchmark explicitly. For CRITICAL, name how far below median.
    - Metrics table: avg_monthly_launches, motion_median_monthly, tier, vertical.

### Data Quality Pass Section

11. **Remove** the LCP algorithm instructions from Phase 4. Replace with: "The data_quality block in computed.json was produced by `_run_analyses.py`. Read `data_quality.likely_related_concept_clusters`. If non-empty, mention in the markdown report under a 'Data Quality' section above the Priority Action Stack. The dashboard card is rendered automatically from the data_quality block."

### Phase 5 Step 1 — results.json Assembly

12. **Update Step 1** to describe a merge operation rather than "write from scratch":
    ```
    Step 1 — Assemble results.json

    Load ~/meta-diagnostics/computed.json. For each analysis in the analyses array:
    - Fill in the `meaning` field with the meaning copy you wrote in Phase 4.
    - Fill in the `action` field with the action copy you wrote in Phase 4.
    - Fill in the `metrics` field with the key numbers table for the markdown report.

    All other fields (id, title, verdict, data) come from computed.json unchanged —
    do NOT recompute or modify them.

    Write the assembled object to ~/meta-diagnostics/results.json.

    Contract: overview.spend is already a raw numeric string in computed.json — do not reformat it.
    ```

13. **Add an analysis `id` validation note** to Phase 5: "The `id` field for each analysis comes from computed.json and is already set correctly. Never modify it. If you see an unrecognized `id` in the dashboard, it means computed.json was written with a wrong id — re-run `_run_analyses.py`."

### Retained Tone + Output Rules

14. **Tone rules are retained verbatim** (current TONE & OUTPUT RULES section at bottom of SKILL.md is unchanged):
    - Be direct. Name the problem specifically.
    - Use the user's `conversion_label` (not generic "CPA") throughout.
    - When verdict is CRITICAL, be urgent without being alarmist.

15. **Priority Action Stack** in the markdown report: unchanged — still synthesizes CRITICAL items first, WARNING second, HEALTHY third.

**Integration Requirements:**
16. After Story 8, running `/meta-diagnostics` produces identical results.json structure as before — the only difference is that numeric fields are computed by Python and are correct.
17. The dashboard template requires no changes — it reads results.json at runtime and the schema is unchanged.
18. If `_run_analyses.py` fails or is not found, surface a clear error and tell the user to run `bash install.sh` from the repo root to reinstall. Do not fall back to LLM-in-context computation.

**Quality Requirements:**
19. Running `/meta-diagnostics` on `act_748122004521787` after Stories 5–8 produces:
    - A1 Purple zone: 6 scaled-winner concepts (not 4 tiny-spend outliers)
    - A2 verdict: WARNING or HEALTHY (not CRITICAL from noise ads)
    - A5 tier correctly identified from account_overview.spend / 3
    - All 7 charts render in the dashboard with populated data
20. Running the diagnostic twice on the same data produces identical numeric fields in results.json (deterministic).

---

## Technical Notes

**New Phase 4 structure outline (full section replacement):**

```
## PHASE 4 — COMPUTE + INTERPRET

### Step 1 — Run the compute script
[locate _run_analyses.py instruction]
[run command]
[success/failure handling]

### Step 2 — Read computed.json
[load instruction]

### Step 3 — Write interpretation copy
For each analysis in computed.json, write meaning and action as described below.
The verdict is already set — do not change it. Reference specific numbers from the data dict.
Always use {conversion_label} instead of "CPA" in copy.

**Evaluation precedence (for awareness only — Python already set the verdict):**
If you ever need to understand why a verdict was assigned, the rules are:
CRITICAL conditions are checked first, then WARNING, then HEALTHY.
A concept that meets HEALTHY conditions but also meets CRITICAL conditions is CRITICAL.

---

### Analysis 1: Test & Learn — Interpretation
Verdict is in computed.json. Write meaning and action using these templates:

CRITICAL: "X% of your budget is on scaled ads with CPA above 2× the account median — 
these are scaled losers. [N] concepts in the Red zone account for X% of total spend."
Action: "Pull a report of your Red zone ads (spend ≥ $[testing_max_spend], CPA ≥ $[red_cpa]).
Pause the top 3 by spend before the next billing period."

WARNING: "Budget is spreading into underperforming ads..."
[etc.]

Metrics table (for markdown report):
| Metric | Value |
| Red zone spend | {red_spend_pct:.0f}% |
| Purple (winners) | {winner_spend_pct:.0f}% |
| Green (testing) | {testing_budget_pct:.0f}% |
| Purple concepts | {zone_concentration.purple.count} |
| Red concepts | {zone_concentration.red.count} |

---

[repeat for all 7 analyses]
```

**Phase 5 Step 1 replacement block:**

```
### Step 1: Assemble results.json

Read ~/meta-diagnostics/computed.json.

For each analysis entry, add your Phase 4 copy:
  - "meaning": the one-sentence plain-English meaning you wrote
  - "action": the one specific next step you wrote
  - "metrics": a dict of key metric name → formatted value strings (for markdown report)

Write the complete assembled object to ~/meta-diagnostics/results.json.

Do not modify: run_date, config, overview, data_quality, or any analysis's id/title/verdict/data.
```

**Script failure handling (add to ERROR HANDLING section):**
```
**_run_analyses.py not found or exits with error:**
"The compute script could not be found or failed to run. To fix this:
1. Run `bash install.sh` from the root of the meta-account-diagnostics repo.
2. Then re-run /meta-diagnostics.
Error details: [paste the error message here]"
Do not attempt to run analyses without the compute script.
```

---

## Definition of Done

- [ ] SKILL.md Phase 4 replaces Shared Step + all 7 per-analysis computation sections with: run script → read computed.json → write copy
- [ ] Per-analysis interpretation copy templates retained for all 7 analyses (meaning/action per verdict state)
- [ ] Phase 5 Step 1 updated: merge computed.json + LLM copy → results.json
- [ ] Data Quality Pass section replaced with: "read data_quality from computed.json, mention in report if non-empty"
- [ ] ERROR HANDLING updated with script-not-found handling
- [ ] Running `/meta-diagnostics` on test account produces correct A1 Purple zone (6 concepts), correct A2 verdict
- [ ] Two consecutive runs on same account produce identical numeric fields
- [ ] All 7 dashboard charts render with populated data
- [ ] TONE & OUTPUT RULES section unchanged

---

## Risk and Compatibility Check

**Primary Risk:** After Story 8, the LLM will refuse to compute analyses without `_run_analyses.py`. If a user has not run `install.sh` after Story 7, they'll hit the "script not found" error. Mitigation: Story 7's install.sh update handles this automatically; the error message tells users exactly how to fix it.

**Secondary Risk:** The LLM might still add interpretation bias to the numeric fields when assembling results.json ("I'll round this slightly"). Mitigation: the Phase 5 instruction explicitly says "do not modify" non-copy fields; the dashboard validates that data fields are numeric types (Plotly will visually error if they're wrong).

**Rollback:** Revert SKILL.md to the pre-Story-8 state. `_run_analyses.py` and `computed.json` remain on disk but are unused. The LLM returns to in-context computation. All prior raw data files remain harmless.

- [x] Dashboard template unchanged — reads same results.json contract
- [x] Story 8 is the last dependency — once this ships, the full hybrid architecture is live
- [x] Old results.json files (pre-Story 8) still render correctly in the dashboard
- [x] If `_run_analyses.py` output schema drifts from dashboard expectations, charts degrade gracefully (text-only card, no crash)

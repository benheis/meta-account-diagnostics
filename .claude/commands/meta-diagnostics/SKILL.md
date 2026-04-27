---
name: meta-diagnostics
description: >
  Full Meta Ads account audit in one command. Runs 7 diagnostic analyses using
  proven Meta advertising frameworks and Motion 2026 Creative Benchmarks. Generates a
  Markdown report saved locally and auto-launches an interactive Streamlit dashboard.
  Requires an MCP server with Meta Ads access (ads-mcp-connector recommended).
  Triggers: /meta-diagnostics, "run meta audit", "diagnose my Meta ads",
  "Meta account health check", "check my Meta account", "run the meta diagnostic".
---

# /meta-diagnostics

You are running a structured Meta Ads account diagnostic. Follow every phase in order. Do not skip steps. Surface all findings transparently — good and bad.

---

## PHASE 0 — DEPENDENCY CHECK

First, check `~/.meta-diagnostics-config.json`. If it exists and `deps_checked` is `true`, skip to Phase 1.

Otherwise, run these checks in order:

### Step 1: Python 3.10+
Run: `python3 --version`

If Python is missing or below 3.10:
```
Python 3.10 or newer is required to run the dashboard.

Here's how to install it:
1. Go to https://www.python.org/downloads/
2. Download the latest Python 3.x installer for your operating system
3. During installation, check the box that says "Add Python to PATH"
4. Once installed, come back here and tell me it's done — I'll continue automatically.
```
Wait for the user to confirm Python is installed before continuing.

### Step 2: pip
Run: `python3 -m pip --version`

If missing: run `python3 -m ensurepip --upgrade` and confirm it succeeded.

### Step 3: Required libraries
Run: `python3 -c "import streamlit, plotly, pandas, requests"`

If any ImportError: run `python3 -m pip install streamlit plotly pandas requests`
Tell the user: "Installing the dashboard libraries — this takes about 30 seconds..."
Wait for the install to finish.

### Step 4: Mark deps as checked
Save `~/.meta-diagnostics-config.json` with `"deps_checked": true` (merge with any existing config).

---

## PHASE 1 — CONFIG

**Config override check (run first, before reading or collecting config):**
If the user passed any override parameters when invoking the skill — phrases like `"with allocation_min_spend = 1000"`, `"target_cpa = 150"`, `"winner_top_percentile = 0.15"`, `"target_cpa = null"` — do the following before anything else:
- Load `~/.meta-diagnostics-config.json` (if it exists)
- Update the specified key(s): `allocation_min_spend` (positive integer), `target_cpa` (positive number, or null to clear it), `winner_top_percentile` (decimal 0.01–0.50)
- Write the updated config back to disk
- Confirm: `"Config updated: [key] set to [value]. Proceeding with diagnostic..."`
- Skip to Phase 2

Non-overridable without full re-setup: `account_id`, `conversion_event`, `industry_vertical`.

Read `~/.meta-diagnostics-config.json`.

If the config file exists and contains `account_id`, `conversion_event`, `conversion_label`, and `industry_vertical`:
- If `allocation_min_spend` is missing, add it with value `500` (silent default — no prompt)
- If `winner_top_percentile` is missing, add it with value `0.20` (silent default — no prompt)
- If `target_cpa` is missing, add it with value `null` (silent default — no prompt)
- If `winner_threshold` is present, ignore it silently (deprecated key)
- Write updated config to disk only if any defaults were added
- Skip to Phase 2

Otherwise, ask the following 4 questions in sequence:

---

**Question 1:**
```
What is your Meta ad account ID?

You can find it in Ads Manager — it's the number in the URL after "act_", like act_123456789.
Just type the full thing including "act_" (or I can add it for you).
```

**Question 2:**
```
What conversion event are you optimizing towards in Meta?

Examples: Purchase, Lead, Complete Registration, Subscribe, Add to Cart

Type the event name, then tell me what it represents in your business.
For example: "Purchase = a paid subscription sign-up" or "Lead = form fill for our sales team"

This label will appear throughout your report so the numbers make sense in your context.
```
Parse the two parts: (1) the event name → `conversion_event`, (2) the business description → `conversion_label`.

**Question 3:**
```
What industry vertical are you in?

1. Health & Wellness
2. Technology
3. Education
4. Fitness & Sports
5. Pets
6. Beauty & Personal Care
7. Fashion & Apparel
8. Home & Lifestyle
9. Food & Nutrition
10. Finance
11. Entertainment & Media
12. Automotive
13. Travel & Hospitality
14. Professional Services
15. Parenting & Family
16. Other

Type the number or the name.
```

**Question 4:**
```
What CPA would you consider a winning result for your business?

This is the maximum [conversion_label] cost you'd accept for a scaled creative.
If you have a clear target (e.g. "anything under $200 is profitable"), enter it.
If not, leave blank — the system will identify winners relative to your account's
performance distribution (top 20% by CPA among converted concepts).

Type a number (e.g. 200) or press Enter to skip.
```
Parse as a positive float if provided. If blank or "skip", store as `null`. Re-prompt once if a non-numeric, non-blank value is entered.

**Save config:**
Write all values to `~/.meta-diagnostics-config.json`:
```json
{
  "deps_checked": true,
  "account_id": "act_...",
  "conversion_event": "...",
  "conversion_label": "...",
  "industry_vertical": "...",
  "target_cpa": null,
  "allocation_min_spend": 500,
  "winner_top_percentile": 0.20
}
```
`target_cpa` is `null` if the user skipped Question 4, or their numeric input if provided.
`allocation_min_spend` and `winner_top_percentile` are always written with these defaults on first setup.

---

## PHASE 2 — CONNECTION CHECK

Call `check_connection`.

Look at the `meta` key in the response. If `connected` is false or there's an error:
```
Your Meta Ads account isn't connected. Run /ads-connect first to link your Meta account,
then come back and run /meta-diagnostics again.
```
Stop here if Meta is not connected.

Confirm to the user: "Meta is connected. Pulling your account data now..."

---

## PHASE 3 — DATA PULL

Pull all data in one pass. Reference the stored `account_id` from config.

Create the raw data directory before writing: `mkdir -p ~/meta-diagnostics/raw`

**Pull A — 90-day ad data** (Analyses 1, 2, 3):
Call `meta_get_ads` with `date_range: "last_90d"`
Store as `ads_90d`.
Write to disk: `~/meta-diagnostics/raw/ads_90d.json`
If the response is an error, write `{"error": "<message>", "data": []}` — never skip the write.

**Pull B — 6-month ad data** (Analyses 4, 5, 7):
Call `meta_get_ads` with `date_range: "last_6_months"`.
Store as `ads_6m`.
Write to disk: `~/meta-diagnostics/raw/ads_6m.json`
If the response is an error, write `{"error": "<message>", "data": []}`.

If you need a custom window (e.g. a prior period), pass the date_range as a JSON string:
`date_range: '{"since":"2025-10-24","until":"2026-01-22"}'`
Do NOT pass the literal string `"custom"` or any other free-text value — that is not a valid preset and will return an error.

After every `meta_get_ads` call, verify the response includes `since` and `until` fields that match the window you requested. If they differ by more than 3 days, surface a warning and ask the user whether to continue with the returned window or abort.

**Pull C — Monthly reach** (Analysis 6):
Call `meta_get_monthly_reach` with `months: 13`
Store as `monthly_reach`.
Write to disk: `~/meta-diagnostics/raw/monthly_reach.json`
If the response is an error or empty, write `[]`.

**Pull D — Account overview** (spend tier for Analysis 7):
Call `meta_get_account_overview` with `date_range: "last_90d"`
Store as `account_overview`.
Write to disk: `~/meta-diagnostics/raw/account_overview.json`
If the response is an error, write `{}`.

**Pull E — Per-ad monthly spend** (Analyses 3 and 4):
Call `meta_get_ad_monthly_spend` with `months: 6`
Store as `ad_monthly_spend`.
Write to disk: `~/meta-diagnostics/raw/ad_monthly_spend.json`
If the response is an error or empty, write `[]`.

Tell the user: "Data pulled. Raw data saved to ~/meta-diagnostics/raw/ (5 files). Running analyses..."

---

## PHASE 4 — COMPUTE + INTERPRET

**Your role in Phase 4:** Run the compute script to get all numbers, then write interpretation copy (meaning, action, metrics) around the results. The script sets all verdicts — do not recompute them. Always use `{conversion_label}` (from config) instead of "CPA" in copy.

### Step 1 — Run the compute script

Locate `_run_analyses.py` in the same directory as this SKILL.md file:
```
find ~/.claude -name "_run_analyses.py" -path "*/meta-diagnostics/*" | head -1
```
Store the result as `<script_path>`. The directory containing it is `<skill_dir>`.

Run:
```
python3 <script_path> \
  --skill-dir <skill_dir> \
  --raw-dir ~/meta-diagnostics/raw \
  --config ~/.meta-diagnostics-config.json \
  --output ~/meta-diagnostics/computed.json
```

If the script exits with an error, surface the error message and stop. Tell the user:
```
The compute script encountered an error. Details: [error output]
To fix: run `bash install.sh` from the meta-account-diagnostics repo root, then re-run /meta-diagnostics.
```

If the script succeeds, confirm: "Analysis computed. Writing interpretation..."

### Step 2 — Read computed.json

Load `~/meta-diagnostics/computed.json`. Each analysis entry contains:
- `verdict`: HEALTHY / WARNING / CRITICAL / INSUFFICIENT_DATA — **already set, do not change**
- `data`: all numeric fields — **already computed, do not modify**
- `meaning`, `action`: empty strings — **you fill these in below**
- `metrics`: empty dict — **you populate with key numbers for the markdown report**

### Step 3 — Write interpretation copy for each analysis

For each of the 7 analyses, read the verdict and data dict, then write `meaning` and `action`. Be direct — name specific numbers. Reference the `{conversion_label}` from config (not generic "CPA").

---

### Analysis 1: Test & Learn Spend Optimization

Read from `data`: `winner_spend_pct`, `red_spend_pct`, `testing_budget_pct`, `zone_concentration`, `box_thresholds`.

**HEALTHY:** Meaning: "Your testing budget is well-allocated — {winner_spend_pct:.0f}% of spend is on Purple zone winners, {testing_budget_pct:.0f}% in the testing pool, and only {red_spend_pct:.0f}% on scaled losers." Action: "Keep current allocation. Review Red zone ads quarterly and pause any crossing 2× median {conversion_label}."

**WARNING:** Meaning: "Budget is spreading into underperforming ads — only {winner_spend_pct:.0f}% is on Purple zone winners (target: >40%)." Action: "Pause the top 2–3 Red zone ads by spend this week (spend ≥ ${box_thresholds.testing_max_spend:,.0f}, {conversion_label} ≥ ${box_thresholds.median_cpa * 2:,.0f}) and reallocate to Purple."

**CRITICAL:** Meaning: "{red_spend_pct:.0f}% of budget is on scaled ads with {conversion_label} more than 2× the account median." If no Purple concepts: "There are no scaled winner concepts — all high-spend ads have above-median {conversion_label}." Action: "List all ads with spend ≥ ${box_thresholds.testing_max_spend:,.0f} and {conversion_label} ≥ ${box_thresholds.median_cpa * 2:,.0f}. Pause them before the next billing period."

**metrics:** Red zone spend %, Purple (winners) %, Green (testing) %, Purple concept count, Red concept count, testing floor $, scale floor $.

---

### Analysis 2: Creative Allocation

Read from `data`: `top_1pct_spend_pct`, `top_10pct_spend_pct`, `sub_threshold_spend_pct`, `budget_waste_signal`, `allocation_min_spend`.

**HEALTHY:** Meaning: "{top_10pct_spend_pct:.0f}% of budget is on your top-performing 10% of concepts — well-concentrated on proven winners." Action: "Keep allocation. If sub-threshold pool grows above 25%, graduate promising concepts by pushing spend above the ${allocation_min_spend:,.0f} floor."

**WARNING:** Meaning (low winners): "Only {top_10pct_spend_pct:.0f}% of budget is on top-10% performers — spread too thin." Meaning (high untested): "{sub_threshold_spend_pct:.0f}% of budget is locked in sub-threshold concepts that have never been properly tested." Action: "Scale Top 10% concepts by 20%. Push 2–3 sub-threshold concepts with conversions above ${allocation_min_spend:,.0f} to graduate them."

**CRITICAL:** Meaning: "Only {top_10pct_spend_pct:.0f}% on top performers — allocation is fragmented. Budget waste signal: ${budget_waste_signal:,.0f} above median {conversion_label}." Action: "Double spend on Top 1% concepts this week. Pause 'Other (no conversions)' concepts running more than 30 days."

**metrics:** Top 1% spend %, Top 10% spend %, Sub-threshold spend %, Budget waste signal $, Spend floor $.

---

### Analysis 3: Reliance on Old Creative

Read from `data`: `old_creative_spend_pct`, `data_warnings`. If `data_warnings` is non-empty, prepend a brief note to meaning.

**HEALTHY:** Meaning: "{old_creative_spend_pct:.0f}% of spend on aging creative (61+ days) — rotation is healthy." Action: "Flag any ad running 90+ days that hasn't been refreshed — even winning creative fatigues."

**WARNING:** Meaning: "{old_creative_spend_pct:.0f}% of spend on aging creative (61+ days). New creative is being outspent by fatiguing ads." Action: "Launch 3–5 new concepts this week using the hooks/angles from best-performing old creative. Set a rotation policy: creative running 60+ days gets a refresh brief."

**CRITICAL:** Meaning: "{old_creative_spend_pct:.0f}% of budget on ads more than 61 days old — creative pool is stale and likely fatiguing your audience." Action: "Pause top 3 highest-spend ads that are 90+ days old. Brief net-new creative immediately. Treat this as a 2-week creative sprint."

**metrics:** Old creative spend (61d+) %.

---

### Analysis 4: Creative Churn

Read from `data`: `avg_cohort_half_life_weeks`, `launch_trend`, `monthly_launches` (last 3 entries), `data_warnings`.

**HEALTHY:** Meaning: "Creative cohorts sustain spend for an average of {avg_cohort_half_life_weeks:.1f} weeks. Launch volume is {launch_trend}." Action: "Maintain cadence. Watch for half-life dropping below 4 weeks — that signals fatiguing creative."

**WARNING:** Meaning: "Cohort half-life is {avg_cohort_half_life_weeks:.1f} weeks — creative spending out faster than the 4-week baseline. Launch volume is {launch_trend}." Action: "Increase launch frequency — brief 2–3 net-new concepts per week. Prioritize angles with previously long half-lives."

**CRITICAL:** Meaning: "Launch volume is {launch_trend} AND cohort half-life is {avg_cohort_half_life_weeks:.1f} weeks — running out of fresh creative with nothing in the pipeline." Action: "Stop refreshing old creative. Brief 5 genuinely new angles this week."

If `data_warnings` non-empty: prepend "Note: [first warning]. " to meaning.

**metrics:** Avg cohort half-life (weeks), Launch trend, last 3 months' launch counts by month.

---

### Analysis 5: Production & Slugging Rate

Read from `data`: `recent_avg_hit_rate`, `prior_avg_hit_rate`, `motion_benchmark`, `spend_tier`, `target_cpa_mode`, `windows`.

**HEALTHY:** Meaning: "Producing winners at {recent_avg_hit_rate:.1f}% hit rate vs. the Motion {motion_benchmark:.1f}% benchmark for {spend_tier}-tier accounts." Action: "Keep current creative testing cadence. Push toward top-quartile benchmark."

**WARNING — below benchmark:** Meaning: "Hit rate {recent_avg_hit_rate:.1f}% is below the Motion {motion_benchmark:.1f}% benchmark for {spend_tier}-tier. More concepts launching with zero conversions than expected." Action: "Audit last 2 months of launched concepts — identify the shared failure pattern (wrong hook, format, or audience). Brief replacements."

**WARNING — declining:** Meaning: "Hit rate dropped from {prior_avg_hit_rate:.1f}% to {recent_avg_hit_rate:.1f}%. High throughput with low win rate recently." Action: "Review concepts launched in the declining months — identify what changed and brief the corrective direction."

**CRITICAL:** Meaning: "No winning concepts in the last two scoreable months. Hit rate {recent_avg_hit_rate:.1f}% against a {motion_benchmark:.1f}% benchmark." Action: "Halt current creative direction. Brief 5 genuinely new angles — different hook, format, and opener — this week."

**INSUFFICIENT_DATA:** Meaning: "Need ≥3 concepts launched in at least 2 calendar months to compute trend. More data needed." Action: "Keep launching. Re-run after more months mature."

**metrics:** Recent hit rate (2mo avg) %, Motion benchmark (tier) %, Prior hit rate % or N/A, Winner mode (target CPA or percentile).

---

### Analysis 6: Rolling Reach

Read from `data`: `signal_a_fired`, `signal_b_fired`, `prior_avg_cost_pnn`, `recent_avg_cost_pnn`, `trailing_ratio`, `recent_ratio`, `using_fallback`, `calculation_note`, `data_warnings`.

Always include `calculation_note` from the data dict as a note in the markdown report for this analysis.

**HEALTHY:** Meaning: "Reach costs are stable — cost per net-new person reached has not risen materially in the last 6 months." Action: "Monitor monthly. If cost per net-new rises 20%+ in a single month, check frequency and consider a creative refresh."

**WARNING — Signal A only:** Meaning: "Cost per net-new person reached rose materially — from ${prior_avg_cost_pnn:,.4f} to ${recent_avg_cost_pnn:,.4f}. Audience may be partially saturated." Action: "Expand targeting — test new audiences, lookalikes, or geos."

**WARNING — Signal B only:** Meaning: "Net-new audience share dropped from {trailing_ratio:.0%} to {recent_ratio:.0%} — re-exposure to the same audience is increasing." Action: "Introduce new creative to reactivate the audience and reduce repeat exposure."

**CRITICAL:** Meaning: "Both saturation signals fired: cost per net-new person is rising AND net-new audience share is declining. Audience pool may be significantly saturated." Action: "Immediately expand targeting. Test 2 new cold audiences this week. Reallocate budget from high-frequency placements to prospecting."

**INSUFFICIENT_DATA:** Meaning: "Reach saturation cannot be measured yet — {calculation_note}" Action: "No action needed now. Re-run after 12 months of historical reach data are available."

**metrics:** Signal A (cost rising), Signal B (saturation), prior avg cost/net-new $, recent avg cost/net-new $.

---

### Analysis 7: Creative Volume vs. Spend

Read from `data`: `avg_monthly_launches`, `motion_median_monthly`, `motion_top_quartile_monthly`, `vertical`, `tier`, `launch_window`.

**HEALTHY:** Meaning: "Launching {avg_monthly_launches:.0f} concepts/month — at or above the Motion median of {motion_median_monthly:.0f}/month for {vertical} × {tier}-tier accounts." Action: "Push toward the top-quartile benchmark of {motion_top_quartile_monthly:.0f} concepts/month to outpace median competitors."

**WARNING:** Meaning: "Launching {avg_monthly_launches:.0f} concepts/month — below the Motion median of {motion_median_monthly:.0f}/month for {vertical} × {tier}-tier. Testing velocity is below average for your spend level." Action: "Brief additional concepts to close the gap to the {motion_median_monthly:.0f}/month median. Identify whether the bottleneck is brief-writing, production, or approval."

**CRITICAL:** Meaning: "Launching only {avg_monthly_launches:.0f} concepts/month — less than half the Motion median of {motion_median_monthly:.0f}/month for {vertical} × {tier}-tier. At this velocity you won't find winners fast enough to sustain performance." Action: "This is a production capacity problem. Set a minimum target of {motion_median_monthly:.0f} concepts/month immediately and identify the bottleneck."

**metrics:** Avg monthly launches, Motion median (vertical × tier), Motion top quartile, launch window months and counts.

---

### Data Quality Output

The `data_quality` block in computed.json is populated by the compute script — do not re-run the LCP algorithm.

If `data_quality.likely_related_concept_clusters` is non-empty: mention these clusters in the markdown report under a **"Data Quality — Likely-related concepts"** section, placed above the Priority Action Stack. The dashboard card renders automatically — no additional action needed.

If the list is empty: omit the section from the markdown report entirely.

---

## PHASE 5 — WRITE OUTPUTS

### Step 1: Write results.json

Load `~/meta-diagnostics/computed.json`. For each analysis entry, fill in the copy you wrote in Phase 4:
- `meaning`: the one-sentence plain-English meaning
- `action`: the one specific next step
- `metrics`: key numbers dict for the markdown report

All other fields (`id`, `title`, `verdict`, `data`, `run_date`, `config`, `overview`, `data_quality`) come from `computed.json` unchanged — **do not recompute or modify them**.

Write the assembled object to `~/meta-diagnostics/results.json`.

**Key contracts (already enforced by _run_analyses.py — do not override):**
- `overview.spend` is a raw numeric string — do not reformat
- `id` fields are already correct — do not change them
- Analysis order: test_and_learn → creative_allocation → old_creative → creative_churn → slugging_rate → rolling_reach → volume_vs_spend

**`_run_analyses.py` script failure handling:**
If the script was not found or failed, tell the user:
```
The compute script encountered an error: [error details]
To fix: run `bash install.sh` from the meta-account-diagnostics repo root, then re-run /meta-diagnostics.
```

### Step 2: Write Markdown report

Write `~/meta-diagnostics/report-YYYY-MM-DD.md` with this structure:

```markdown
# Meta Account Diagnostics — [Account ID] — [Date]
**Optimizing for:** [conversion_event] ([conversion_label])
**Spend tier:** [tier] | **Industry:** [vertical]
**Analyses run:** 7 | **Health:** X CRITICAL / X WARNING / X HEALTHY

---

## 1. Test & Learn Spend Optimization — [VERDICT]

| Metric | Value |
|---|---|
| Red zone spend | X% |
| Winner concentration | X% |
| Testing budget | X% |

**What it means:** [meaning sentence]
**Recommended action:** [action sentence]

---
[repeat for all 7 analyses]

---

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIORITY ACTION STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CRITICAL (do this week)
  1. [top CRITICAL action]
  2. [second CRITICAL action if any]

WARNING (do this month)
  3. [top WARNING action]

HEALTHY — keep doing
  4. [what's working]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 3: Generate dashboard.py

Copy `{skill_dir}/templates/dashboard_template.py` to `~/meta-diagnostics/dashboard.py`, where `{skill_dir}` is the directory containing this SKILL.md file. To find the skill directory, run: `find ~/.claude -name "SKILL.md" -path "*/meta-diagnostics/*" | head -1 | xargs dirname`

The template reads from `results.json` at runtime — no modification is needed.

Tell the user:
```
Report saved: ~/meta-diagnostics/report-YYYY-MM-DD.md
Dashboard ready: ~/meta-diagnostics/dashboard.py
```

---

## PHASE 6 — AUTO-LAUNCH

Write `~/meta-diagnostics/launch.sh`:
```bash
#!/bin/bash
cd ~/meta-diagnostics
streamlit run dashboard.py
```

Make it executable: `chmod +x ~/meta-diagnostics/launch.sh`

Then run: `bash ~/meta-diagnostics/launch.sh`

Tell the user:
```
Opening your dashboard at http://localhost:8501 — it will open in your browser automatically.

Your full report is also saved at:
~/meta-diagnostics/report-YYYY-MM-DD.md
```

---

## ERROR HANDLING

**Meta not connected:**
"Run /ads-connect first, then re-run /meta-diagnostics."

**API returns empty data:**
Run the analysis with zeros. Set verdict to WARNING if the data pull returned nothing (could be a date range with no activity). Note in `meaning`: "No ad data was returned for this period — verify your account has active ads in the last 90 days."

**meta_get_monthly_reach partial data:**
If some months have reach = 0, use them as-is. Note in the report: "Months with zero reach may indicate no active campaigns that period."

**Python not available after install attempt:**
"Python installation couldn't be verified. Make sure you checked 'Add Python to PATH' during install, then restart your terminal and run /meta-diagnostics again."

**Streamlit launch fails:**
"Dashboard couldn't auto-launch. Run this command manually: `streamlit run ~/meta-diagnostics/dashboard.py`"

**Suppressed Motion benchmark:**
"Your vertical ({vertical}) at {tier} tier has a suppressed benchmark in the Motion 2026 report (insufficient sample size). Using the all-verticals average for your tier: {fallback_value} creatives/week."

**`_run_analyses.py` not found or fails:**
"The compute script could not be found or failed to run. To fix:
1. Run `bash install.sh` from the root of the meta-account-diagnostics repo.
2. Then re-run /meta-diagnostics.
Error details: [paste the error message]"
Do not attempt to run analyses without the compute script — do not fall back to in-context computation.

---

## TONE & OUTPUT RULES

- Be direct. Name the problem specifically — not "your performance could be better" but "34% of your budget is on ads with 2× median CPA."
- Use the user's `conversion_label` (not generic "CPA") throughout.
- When verdict is CRITICAL, be urgent without being alarmist. Give the exact action.
- After all output is written and dashboard is launched, print a one-line summary: "Diagnostic complete. X CRITICAL / X WARNING / X HEALTHY. Top priority: [first CRITICAL action or first WARNING action if no CRITICAL]."

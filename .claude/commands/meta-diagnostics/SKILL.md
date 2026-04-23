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

Read `~/.meta-diagnostics-config.json`.

If the config file exists and contains `account_id`, `conversion_event`, `conversion_label`, `industry_vertical`, and `winner_threshold` — load it and skip to Phase 2.

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
What spend threshold defines a "winning" ad for your account?

This is the minimum lifetime spend an ad must reach before you consider it a scaled winner.

Suggested range: $1,000–$5,000 depending on your account size.
Default: $3,000

Just type a number (e.g. 2500) or press Enter to use $3,000.
```
Default to 3000 if the user presses Enter or types nothing.

**Save config:**
Write all values to `~/.meta-diagnostics-config.json`:
```json
{
  "deps_checked": true,
  "account_id": "act_...",
  "conversion_event": "...",
  "conversion_label": "...",
  "industry_vertical": "...",
  "winner_threshold": 3000
}
```

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

**Pull A — 90-day ad data** (Analyses 1, 2, 3):
Call `meta_get_ads` with `date_range: "last_90d"`
Store as `ads_90d`.

**Pull B — 6-month ad data** (Analyses 4, 5, 7):
Call `meta_get_ads` with `date_range: "last_6_months"`.
Store as `ads_6m`.

If you need a custom window (e.g. a prior period), pass the date_range as a JSON string:
`date_range: '{"since":"2025-10-24","until":"2026-01-22"}'`
Do NOT pass the literal string `"custom"` or any other free-text value — that is not a valid preset and will return an error.

After every `meta_get_ads` call, verify the response includes `since` and `until` fields that match the window you requested. If they don't match, stop and surface the error before proceeding with analysis.

**Pull C — Monthly reach** (Analysis 6):
Call `meta_get_monthly_reach` with `months: 13`
Store as `monthly_reach`.

**Pull D — Account overview** (spend tier for Analysis 7):
Call `meta_get_account_overview` with `date_range: "last_90d"`
Store as `account_overview`.

Tell the user: "Data pulled. Running 7 analyses..."

---

## PHASE 4 — ANALYSES

Run all 7 analyses using the data from Phase 3. For each analysis, produce:
- `title`: analysis name
- `verdict`: HEALTHY / WARNING / CRITICAL
- `meaning`: one plain-English sentence
- `action`: one specific next step
- `data`: structured dict for the dashboard charts (spec below)
- `metrics`: key numbers table (for Markdown report)

Store the CPA label as: `"{conversion_event} Cost ({conversion_label})"` — use this everywhere you'd write "CPA".

---

### Analysis 1: Test & Learn Spend Optimization

**Data used:** `ads_90d`

**Calculations:**
1. For each ad, extract `spend` (float) and CPA = find `conversion_event` in `cost_per_action_type` array. If not found, use 0.
2. Compute `account_median_cpa` = median CPA of all ads with CPA > 0.
3. Compute `account_median_spend` = median spend of all ads.
4. Zone each ad:
   - Red: CPA > 2 × account_median_cpa AND spend > 500
   - Purple: in the lowest-CPA 10% of ads by count
   - Green: everything else
5. Compute:
   - `red_spend_pct` = sum of Red zone spend / total spend × 100
   - `winner_spend_pct` = sum of Purple zone spend / total spend × 100
   - `testing_budget_pct` = sum of spend on ads with spend < 500 / total spend × 100

**Verdict:**
- HEALTHY: winner_spend_pct > 40 AND testing_budget_pct between 10-20 AND red_spend_pct < 15
- WARNING: winner_spend_pct 20-40 OR red_spend_pct 15-25
- CRITICAL: red_spend_pct > 25 OR (all ads have spend < 5% of total — no clear winner)

**Meaning (examples):**
- HEALTHY: "Your testing budget is well-allocated — winners are scaling and losers are being cut."
- WARNING: "Budget is spreading into underperforming ads; consider consolidating spend on your top performers."
- CRITICAL: "Over {red_spend_pct:.0f}% of your budget is on ads with high CPA and high spend — these are scaled losers that need to be cut immediately."

**Action (examples):**
- HEALTHY: "Keep current allocation — review Red zone ads quarterly."
- WARNING: "Pause the top 3 Red zone ads by spend this week and reallocate budget to Purple zone."
- CRITICAL: "List all Red zone ads and pause any with lifetime spend > $500 and CPA > 2× account median. Do this before the next billing period."

**Dashboard data dict:**
```json
{
  "ads": [{"name": "...", "spend": 0.0, "cpa": 0.0, "zone": "Green|Red|Purple"}],
  "cpa_label": "Purchase Cost (paid subscription sign-up)",
  "account_median_cpa": 0.0,
  "red_spend_pct": 0.0,
  "winner_spend_pct": 0.0,
  "testing_budget_pct": 0.0
}
```

---

### Analysis 2: Creative Allocation

**Data used:** `ads_90d` (reuse from Analysis 1 — no new API call)

**Calculations:**
1. Rank all ads by CPA ascending (lowest CPA = best).
2. Identify top 1% by count (ceil), top 10% by count.
3. Compute:
   - `top_1pct_spend_pct` = spend in top 1% / total spend × 100
   - `top_10pct_spend_pct` = spend in top 10% / total spend × 100
4. Tag each ad: "Top 1%", "Top 10%", or "Other"
5. Spend-weighted avg CPA = sum(spend × cpa) / sum(spend)
6. Unweighted median CPA = median(cpa)
7. `budget_waste_signal` = spend_weighted_avg_cpa - unweighted_median_cpa (positive = budget is on worse ads)

**Verdict:**
- HEALTHY: top_10pct_spend_pct > 50
- WARNING: top_10pct_spend_pct 30-50
- CRITICAL: top_10pct_spend_pct < 30 OR highest-spend ads are NOT lowest-CPA (budget_waste_signal > 20% of median CPA)

**Dashboard data dict:**
```json
{
  "ads": [{"name": "...", "spend": 0.0, "cpa": 0.0, "tier": "Top 1%|Top 10%|Other"}],
  "top_1pct_spend_pct": 0.0,
  "top_10pct_spend_pct": 0.0,
  "budget_waste_signal": 0.0
}
```

---

### Analysis 3: Reliance on Old Creative

**Data used:** `ads_90d` — use `created_time` field

**Calculations:**
1. For each ad, compute age in days = today - date(created_time).
2. Bucket:
   - New: 0-30 days
   - Mid: 31-60 days
   - Aging: 61-90 days
   - Old: 90+ days
3. Compute % of total 90d spend per bucket.
4. Compute `old_creative_spend_pct` = (Aging + Old) / total × 100.
5. For monthly breakdown (chart): group `created_time` by month for the 3 visible months.

**Verdict:**
- HEALTHY: old_creative_spend_pct < 40
- WARNING: old_creative_spend_pct 40-65
- CRITICAL: old_creative_spend_pct > 65

**Dashboard data dict:**
```json
{
  "monthly_spend_by_age": [
    {"month": "2025-01", "New (0-30d)": 0.0, "Mid (31-60d)": 0.0, "Aging (61-90d)": 0.0, "Old (90d+)": 0.0}
  ],
  "old_creative_spend_pct": 0.0
}
```

---

### Analysis 4: Creative Churn

**Data used:** `meta_get_ad_monthly_spend(months=6)` — call this tool explicitly. It returns one entry per ad with a `monthly_spend` array of `{month, spend}` objects.

**Calculations:**

Step 1 — Group ads into launch cohorts:
- For each ad, extract launch month from `created_time` → YYYY-MM. This is the cohort key.
- Build a dict: `cohorts = { "2025-11": [ad1, ad2, ...], "2025-12": [...], ... }`

Step 2 — Build `cohort_spend_by_month`:
- Enumerate every calendar month M in the 6-month window.
- For each cohort C launched on or before M, sum `monthly_spend[month == M].spend` across all ads in C.
- Output one row per calendar month:
  `{"month": "2025-11", "Nov 2025 launches": 5234.10, "Oct 2025 launches": 3201.55}`
- Cohort column name format: `"{Mon YYYY} launches"` (e.g. "Nov 2025 launches").
- Only include cohorts that have non-zero spend in at least one month.

Step 3 — Cohort half-life:
- For each cohort C: find its peak spend month. Find the first subsequent month where spend drops below 50% of peak. Half-life = distance in months between peak and that month (minimum 1).
- `avg_cohort_half_life_weeks` = mean half-life across all cohorts × 4.33.

Step 4 — Monthly launch counts:
- `monthly_launches` = for each month M, count of ads whose `created_time` falls in M.

Step 5 — Launch trend:
- Compare last 3 months' launch counts. Growing = each month higher than prior. Declining = each month lower. Flat = otherwise.

**Fallback (if `meta_get_ad_monthly_spend` returns an error or empty):**
Distribute each ad's lifetime spend from `ads_6m` evenly across its active months (launch month → today). Use this to approximate `cohort_spend_by_month`. Add to the output:
```json
"data_warnings": ["Cohort spend approximated using even distribution — actual spend is typically front-loaded. Run meta_get_ad_monthly_spend for accurate curves."]
```

**Contract: never emit empty data fields.** If `cohort_spend_by_month` cannot be populated even with the fallback, set it to `[]` and populate `data_warnings` explaining why. Do NOT leave the field missing or silently empty — the dashboard surfaces `data_warnings` to the user.

**Verdict:**
- HEALTHY: Launch volume stable or growing MoM. Cohort half-life > 6 weeks (1.5 months).
- WARNING: Launch volume declining 2+ months in a row OR cohort half-life < 4 weeks.
- CRITICAL: Launch volume declining AND projected to fall below Motion median for spend tier within 30 days.

**Dashboard data dict:**
```json
{
  "cohort_spend_by_month": [
    {"month": "2025-11", "Nov 2025 launches": 5234.10, "Oct 2025 launches": 3201.55},
    {"month": "2025-12", "Nov 2025 launches": 4180.99, "Dec 2025 launches": 8120.30}
  ],
  "monthly_launches": [{"month": "2025-11", "count": 4}, {"month": "2025-12", "count": 6}],
  "avg_cohort_half_life_weeks": 5.2,
  "data_warnings": []
}
```

---

### Analysis 5: Production & Slugging Rate

**Data used:** `ads_6m`

**Calculations:**
1. Compute `account_median_ad_spend` = median of all ad spend values.
2. Motion winner threshold = max(10 × account_median_ad_spend, 500).
3. User winner threshold = config `winner_threshold`.
4. For each month: count launches, count winners (user def), count winners (Motion def).
5. Monthly hit rate (user def) = winners_user / launches × 100.
6. Determine spend tier from `account_overview` monthly spend:
   - Micro: < 10000, Small: 10000-50000, Medium: 50000-200000, Large: 200000-1000000, Enterprise: 1000000+
7. Load Motion benchmark hit rate for spend tier from `motion-benchmarks.json`.
8. Classify: Volume problem if launches < Motion median for tier. Quality problem if launches ≥ median but hit rate < benchmark.

**Verdict:**
- HEALTHY: Hit rate ≥ Motion avg for tier, stable or improving.
- WARNING: Hit rate 50-80% of Motion avg OR declining 2+ months.
- CRITICAL: Hit rate < 50% of Motion avg OR zero winners in last 60 days.

**Dashboard data dict:**
```json
{
  "monthly_slugging": [
    {"month": "2025-01", "launches": 0, "winners_user": 0, "winners_motion": 0, "hit_rate_pct": 0.0}
  ],
  "motion_avg_hit_rate": 0.0,
  "motion_top_quartile_hit_rate": 0.0,
  "spend_tier": "Small",
  "problem_type": "volume|quality|both|none",
  "account_median_ad_spend": 0.0
}
```

---

### Analysis 6: Rolling Reach

**Data used:** `monthly_reach` (from `meta_get_monthly_reach`)

**Calculations:**
1. For each month M, estimate net new reach using the approximation:
   - Full overlap calculation requires knowing unique reach across months, which isn't directly available.
   - Use this proxy: net_new_reach[M] = reach[M] - (reach[M-12] * 0.5)
   - Rationale: after 12 months, approximately 50% of the audience could be considered re-engagement (conservative). If no M-12 data, use reach[M] × 0.7 as estimate.
   - Cap net_new at reach[M] (can't exceed total reach).
2. cost_per_net_new_reach[M] = spend[M] / net_new_reach[M] (skip if net_new is 0).
3. Trend: is net new reach direction over last 3 months up, flat, or down?
4. Cost trend: is cost per net new reach up, flat, or down?

**Verdict:**
- HEALTHY: Net new reach stable or growing AND cost per net new reach flat or declining.
- WARNING: Net new reach declining 2+ months in a row.
- CRITICAL: Net new reach declining AND cost per net new reach rising.

**Dashboard data dict:**
```json
{
  "monthly_reach": [
    {"month": "2025-01", "reach": 0, "net_new_reach": 0, "spend": 0.0, "cost_per_net_new": 0.0}
  ],
  "net_new_trend": "up|flat|down",
  "cost_trend": "up|flat|down"
}
```

---

### Analysis 7: Creative Volume vs. Spend (Motion 2026 Benchmarks)

**Data used:** Launch counts from `ads_6m`. Spend tier from Analysis 5.

**Calculations:**
1. avg_monthly_launches = mean of last 3 months' launch counts.
2. Look up Motion median weekly volume for user's vertical + tier from `motion-benchmarks.json`.
   - If value is null (suppressed), fall back to `all_verticals_fallback` for that tier.
3. Convert weekly to monthly: benchmark_weekly × 4.33.
4. Top quartile monthly = top_quartile_weekly × 4.33.
5. Compare: user launches vs median vs top quartile.
6. Note: Motion median = 50th percentile (average account). Top quartile is the real competitive benchmark.

**Verdict:**
- HEALTHY: avg_monthly_launches ≥ Motion median monthly.
- WARNING: avg_monthly_launches 50-80% of Motion median monthly.
- CRITICAL: avg_monthly_launches < 50% of Motion median monthly.

**Dashboard data dict:**
```json
{
  "avg_monthly_launches": 0.0,
  "motion_median_monthly": 0.0,
  "motion_top_quartile_monthly": 0.0,
  "vertical": "Technology",
  "tier": "Small",
  "fallback_used": false
}
```

---

## PHASE 5 — WRITE OUTPUTS

### Step 1: Write results.json

Create directory `~/meta-diagnostics/` if it doesn't exist.

Write `~/meta-diagnostics/results.json` with this structure:
```json
{
  "run_date": "YYYY-MM-DD",
  "config": { ...config values... },
  "overview": {
    "spend": "...",
    "active_ads": 0,
    "date_range": "last_90_days"
  },
  "analyses": [
    {
      "title": "Test & Learn Spend Optimization",
      "verdict": "CRITICAL",
      "meaning": "...",
      "action": "...",
      "metrics": { ...key numbers... },
      "data": { ...chart data dict... }
    }
  ]
}
```
Include all 7 analyses in order.

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

Copy the template from the skill's `templates/dashboard_template.py` to `~/meta-diagnostics/dashboard.py`.

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

---

## TONE & OUTPUT RULES

- Be direct. Name the problem specifically — not "your performance could be better" but "34% of your budget is on ads with 2× median CPA."
- Use the user's `conversion_label` (not generic "CPA") throughout.
- When verdict is CRITICAL, be urgent without being alarmist. Give the exact action.
- After all output is written and dashboard is launched, print a one-line summary: "Diagnostic complete. X CRITICAL / X WARNING / X HEALTHY. Top priority: [first CRITICAL action or first WARNING action if no CRITICAL]."

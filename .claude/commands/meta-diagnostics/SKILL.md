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

**Pull E — Per-ad monthly spend** (Analyses 3 and 4):
Call `meta_get_ad_monthly_spend` with `months: 6`
Store as `ad_monthly_spend`.

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
4. Zone each ad (evaluated in order; first match wins):
   - Red: CPA > 2 × account_median_cpa AND spend > 500
   - Purple: in the lowest-CPA 10% of ads **among ads with CPA > 0 AND conversions ≥ 1** by count. Ads with zero conversions are ineligible for Purple regardless of their recorded CPA.
   - Green: everything else (including zero-conversion ads that don't meet Red criteria)
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
1. Separate ads into two pools:
   - **Ranked pool**: CPA > 0 AND conversions ≥ 1. These are the only ads eligible for percentile tiers.
   - **Unranked**: CPA = 0 or conversions = 0. Zero conversions means no performance signal — CPA = 0 is not "great CPA," it is no data. These ads are tagged "Other" and excluded from all percentile math.
2. Rank the ranked pool by CPA ascending (lowest CPA = best).
3. Identify top 1% by count (ceil) and top 10% by count — from the ranked pool only.
4. Compute:
   - `top_1pct_spend_pct` = spend in top 1% / total spend × 100
   - `top_10pct_spend_pct` = spend in top 10% / total spend × 100
5. Tag each ad: "Top 1%", "Top 10%", or "Other" (unranked ads are always "Other")
6. Spend-weighted avg CPA = sum(spend × cpa) / sum(spend) — use all ads with spend > 0
7. Unweighted median CPA = median(cpa) of the ranked pool only
8. `budget_waste_signal` = spend_weighted_avg_cpa - unweighted_median_cpa (positive = budget is on worse ads)

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

**Data used:** `ad_monthly_spend` (Pull E)

**Calculations:**
1. From `ad_monthly_spend`, iterate over all (ad, month) pairs where the ad's spend in that month is > 0.
2. For each pair, compute `age_at_month` = (first day of that calendar month − date(ad.`created_time`)).days.
3. Assign age bucket based on `age_at_month`:
   - New (0-30d): age_at_month ≤ 30
   - Mid (31-60d): age_at_month 31–60
   - Aging (61-90d): age_at_month 61–90
   - Old (90d+): age_at_month > 90
4. Accumulate spend per (calendar_month, bucket). Initialize each cell with a fresh `{k: 0.0 for k in BUCKET_KEYS}` — never use a shared mutable accumulator as the dict factory (doing so causes phantom spend to leak into newly-seen cells).
5. Compute `old_creative_spend_pct` = sum of (Aging + Old) spend across all calendar months / total spend × 100.
6. For each (month, bucket) cell, collect the constituent (ad, spend-in-that-month) pairs, sort by spend-in-that-month descending, keep top 5 (`TOP_N_PER_BUCKET = 5`). Truncate ad names to 60 characters, appending `…` if truncated. Empty cells → `[]`.

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
  "monthly_top_ads_by_age": [
    {
      "month": "2025-01",
      "buckets": {
        "New (0-30d)":    [{"name": "Ad name (max 60 chars)", "spend": 0.0, "rank": 1}],
        "Mid (31-60d)":   [],
        "Aging (61-90d)": [],
        "Old (90d+)":     []
      }
    }
  ],
  "top_ads_per_bucket": 5,
  "old_creative_spend_pct": 0.0
}
```

Note: `monthly_top_ads_by_age` is additive — the dashboard gracefully degrades to bucket totals only when this field is absent (for results.json files generated before this change).

---

### Analysis 4: Creative Churn

**Data used:** `ad_monthly_spend` (Pull E — already fetched in Phase 3). Each entry has a `monthly_spend` array of `{month, spend}` objects.

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
- For each cohort C: find its peak spend month. Find the first subsequent month where spend drops below 50% of peak.
  - If such a month is found: half-life = distance in months between peak and that month (minimum 1).
  - If spend never drops below 50% of peak within the data window: half-life = data_window_months (the cohort is still active). Flag it as `still_active: true` in the per-cohort data. Include it in the average — treating still-active cohorts as having a very long half-life is the correct interpretation.
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

**Config parameters used:**
- `window_days` (default 60) — size of each rolling cohort window in days
- `winner_top_percentile` (default 0.20) — an ad is a winner if its CPA falls in the top X% of its own window's eligible pool
- `winner_min_spend` (default 300) — lifetime spend floor to enter the eligible pool
- `winner_threshold` — DEPRECATED. If present in config, emit a warning: "winner_threshold has no effect — Analysis 5 now uses per-window CPA-percentile scoring. Remove it from your config." Do not crash.

**Calculations:**

Step 1 — Build rolling cohort windows:
- Start: 6 months before today. End: today. Step: 30 days.
- Produces ~5 windows over 180 days. Label each by its start and end months (e.g. "Oct–Dec '25").
- Use `ads_6m` as the source for all ad data.

Step 2 — Score each window independently:
For each window W = [window_start, window_end]:
- `window_ads` = ads from `ads_6m` with `created_time` in [window_start, window_end]
- `underspent` = window_ads with spend < winner_min_spend
- `wasted` = window_ads with spend ≥ winner_min_spend AND conversions = 0
- `qualified` = window_ads with spend ≥ winner_min_spend AND conversions > 0
- If len(qualified) < 3: mark window `scoreable = false`, skip threshold; set hit_rate_pct = null.
- Otherwise: sort qualified by CPA ascending. `cpa_threshold` = CPA at index `floor(winner_top_percentile × len(qualified))`.
- `winners` = qualified ads with CPA ≤ cpa_threshold
- `winner_spend` = sum of spend of winners
- `losing_qualified_spend` = sum of spend of (qualified − winners)
- `wasted_spend` = sum of spend of wasted
- `hit_rate_pct` = len(winners) / len(qualified) × 100

Step 3 — Verdict (trend across windows, never cross-window threshold):
- Collect `hit_rate_pct` values for all scoreable windows (where `scoreable = true`).
- `recent_windows` = last 2 scoreable windows. `prior_windows` = 2 before those.
- `recent_avg` = mean(recent_windows hit_rate_pct). `prior_avg` = mean(prior_windows) if ≥ 2 prior exist, else null.
- `target_rate` = winner_top_percentile × 100.

| Verdict | Conditions (any one triggers) |
|---|---|
| CRITICAL | Zero winners across the 2 most recent scoreable windows OR recent_avg < 0.5 × target_rate |
| WARNING | recent_avg < 0.8 × target_rate OR (prior_avg is not null AND recent_avg < prior_avg × 0.8) |
| HEALTHY | recent_avg ≥ 0.8 × target_rate AND (prior_avg is null OR recent_avg ≥ prior_avg × 0.8) |
| INSUFFICIENT_DATA | Fewer than 2 scoreable windows |

Motion benchmark hit rate for the account's spend tier is kept in the data dict as `motion_avg_hit_rate_for_context` — include it in the report table as context only, not as a verdict driver.

**Meaning / action copy:**
- HEALTHY: "Producing winners at {recent_avg:.0f}% hit rate (target ~{target_rate:.0f}%). Each cohort window evaluated against its own CPA bar — no cross-cohort dilution."
- WARNING — low hit rate: "Only {recent_avg:.0f}% of qualified launches in recent windows cleared their cohort CPA bar (target ~{target_rate:.0f}%). Concept quality slipping or losers being scaled prematurely. Audit kill criteria."
- WARNING — declining: "Hit rate dropped from {prior_avg:.0f}% to {recent_avg:.0f}% across recent windows. Review which concepts launched in {most recent window label} are underperforming."
- CRITICAL — zero winners: "No winners in the last two cohort windows. Halt current concepts; brief 5 net-new angles this week."
- INSUFFICIENT_DATA: "Need at least 2 scoreable windows (≥3 ads each with ≥ ${min_spend} spend and ≥1 conversion) to compute a trend. Run again after more data matures."

**Dashboard data dict:**
```json
{
  "windows": [
    {
      "label": "Oct–Dec '25",
      "window_start": "2025-10-23",
      "window_end": "2025-12-22",
      "launches": 12,
      "qualified": 8,
      "winners": 2,
      "wasted": 1,
      "winner_spend": 45000.0,
      "losing_qualified_spend": 22000.0,
      "wasted_spend": 3500.0,
      "hit_rate_pct": 25.0,
      "cpa_threshold": 58.40,
      "scoreable": true
    }
  ],
  "winner_top_percentile": 0.20,
  "winner_min_spend": 300,
  "window_days": 60,
  "recent_avg_hit_rate": 22.5,
  "prior_avg_hit_rate": 28.0,
  "motion_avg_hit_rate_for_context": 8.13,
  "spend_tier": "Medium"
}
```

---

### Analysis 6: Rolling Reach

**Data used:** `monthly_reach` (from `meta_get_monthly_reach`)

**Calculations:**

**Step 0 — Partial month handling:**
Check whether the most recent month has fewer days elapsed than `days_in_month(M)`. If so, compute `reach_per_day[M] = reach[M] / elapsed_days` and use per-day values for all trend comparisons. Include `is_partial: true` on that month's row and a note in the report. Never compare a partial month's raw total against a full month's raw total.

**Step 1 — Estimate net-new reach per month:**
- If M−12 data exists: `net_new_reach[M] = max(reach[M] - reach[M-12] * 0.5, 0)`
- If M−12 data does not exist: `net_new_reach[M] = reach[M] * 0.7` (fallback)
- Track whether the fallback was used: `using_fallback = True` if ANY month used 0.7×
- `net_new_ratio[M] = net_new_reach[M] / reach[M]` (will be exactly 0.70 for every fallback month)
- `cost_per_net_new[M] = spend[M] / net_new_reach[M]` (skip if net_new_reach is 0 or spend is 0)

**Step 2 — Signal A: Is cost per net-new rising materially?**
- Take the last 6 active months (exclude the partial month from this window).
- Split into prior half (oldest 3) and recent half (newest 3).
- `prior_avg = mean(cost_per_net_new for prior 3 months)`
- `recent_avg = mean(cost_per_net_new for recent 3 months)`
- Signal A fires if `recent_avg ≥ prior_avg * 1.20` (≥20% increase).
- Absolute floor: if `recent_avg < 0.50`, Signal A cannot fire regardless of slope (cost is too cheap for the delta to matter). Max verdict = WARNING if this floor applies.
- Store: `signal_a_fired: bool`, `prior_avg_cost_pnn: float`, `recent_avg_cost_pnn: float`

**Step 3 — Signal B: Is the net-new ratio structurally dropping?**
- If `using_fallback` is True for all months: Signal B is suppressed. Every ratio will be exactly 0.70 — the formula cannot detect saturation without M−12 data.
- Otherwise: compute trailing 6-month mean of `net_new_ratio` and most recent 3-month mean.
- Signal B fires if `recent_3m_ratio ≤ trailing_6m_ratio - 0.05` (≥5 percentage point drop).
- Store: `signal_b_fired: bool | null` (null = suppressed), `trailing_ratio: float`, `recent_ratio: float`

**Step 4 — Verdict:**
| Signal A | Signal B | Verdict |
|---|---|---|
| True | True | CRITICAL |
| True | False | WARNING |
| False | True | WARNING |
| False | False | HEALTHY |
| Either suppressed (all-fallback) | — | INSUFFICIENT_DATA |

If `INSUFFICIENT_DATA`: set verdict to `"INSUFFICIENT_DATA"` and add to `data_warnings`:
`"Reach saturation cannot be measured — fewer than 12 months of historical reach data available. Re-run after [date 12 months from earliest data point] when M−12 baseline exists."`
Surface this as a neutral note card in the report, not a CRITICAL or WARNING.

**Step 5 — Report note:**
Always include a one-liner in the report explaining the calculation method:
- If all fallback: `"Net-new reach estimated using 0.7× fallback for all N months (no M−12 baseline available)."`
- If mixed: `"Net-new reach estimated using M−12 overlap formula for N months; 0.7× fallback used for M months where baseline was unavailable."`

**Dashboard data dict:**
```json
{
  "monthly_reach": [
    {
      "month": "2025-01",
      "reach": 0,
      "net_new_reach": 0,
      "net_new_ratio": 0.70,
      "spend": 0.0,
      "cost_per_net_new": 0.0,
      "reach_per_day": 0.0,
      "is_partial": false,
      "used_fallback": true
    }
  ],
  "signal_a_fired": false,
  "signal_b_fired": null,
  "prior_avg_cost_pnn": 0.0,
  "recent_avg_cost_pnn": 0.0,
  "trailing_ratio": 0.70,
  "recent_ratio": 0.70,
  "using_fallback": true,
  "calculation_note": "Net-new reach estimated using 0.7× fallback for all 13 months (no M−12 baseline available).",
  "data_warnings": []
}
```

---

### Analysis 7: Creative Volume vs. Spend (Motion 2026 Benchmarks)

**Data used:** Launch counts from `ads_6m`. Spend tier from Analysis 5.

**Calculations:**
1. Count launches per calendar month from `ads_6m` using `created_time`. **Important:** Meta creates a new `ad_id` with a new `created_time` each time an existing ad is duplicated into a new ad set. These duplicates are counted as launches here. Launch counts may therefore overstate net-new creative output for accounts that scale via ad-set duplication.
2. avg_monthly_launches = mean of last 3 months' launch counts.
3. Look up Motion median weekly volume for user's vertical + tier from `motion-benchmarks.json`.
   - If value is null (suppressed), fall back to `all_verticals_fallback` for that tier.
4. Convert weekly to monthly: benchmark_weekly × 4.33.
5. Top quartile monthly = top_quartile_weekly × 4.33.
6. Compare: user launches vs median vs top quartile.
7. Note: Motion median = 50th percentile (average account). Top quartile is the real competitive benchmark. Motion's count methodology likely reflects intentional creative tests, not ad-object duplications — add `"launch_count_includes_duplicates": true` to `data_warnings` so the dashboard can surface this caveat.

**Verdict:**
- HEALTHY: avg_monthly_launches ≥ Motion median monthly.
- WARNING: avg_monthly_launches 50-80% of Motion median monthly.
- CRITICAL: avg_monthly_launches < 50% of Motion median monthly.

**Additional calculation — tier benchmark table:**
For all 5 spend tiers, look up `median_weekly_testing_volume[vertical][tier]` from `motion-benchmarks.json` (fall back to `all_verticals_fallback` if null) and convert to monthly. Include this as `tier_benchmark_table` so the chart can show where the user sits across tiers.

Also compute:
- `tier_spend_range`: the human-readable range from `spend_tiers[tier]` in `motion-benchmarks.json`
- `account_monthly_run_rate`: the account's average monthly spend over the 90d window (from `account_overview`)
- `launch_window.months`: names of the 3 calendar months used for avg_monthly_launches (e.g. "Feb 2026", "Mar 2026", "Apr 2026 (MTD)")
- `launch_window.monthly_counts`: the raw launch count for each of those 3 months

**Dashboard data dict:**
```json
{
  "avg_monthly_launches": 0.0,
  "motion_median_monthly": 0.0,
  "motion_top_quartile_monthly": 0.0,
  "vertical": "Finance",
  "tier": "Medium",
  "tier_spend_range": "$50K–$200K/month",
  "account_monthly_run_rate": 72003,
  "fallback_used": false,
  "median_cohort_label": "Finance × Medium-tier accounts",
  "top_quartile_cohort_label": "All verticals × Medium-tier accounts",
  "top_quartile_is_cross_vertical": true,
  "launch_window": {
    "label": "Last 3 calendar months",
    "months": ["Feb 2026", "Mar 2026", "Apr 2026 (MTD)"],
    "monthly_counts": [0, 0, 0]
  },
  "tier_benchmark_table": [
    {"tier": "Micro",      "spend_range": "< $10K/month",      "median_monthly": 0.0, "is_current": false},
    {"tier": "Small",      "spend_range": "$10K–$50K/month",   "median_monthly": 0.0, "is_current": false},
    {"tier": "Medium",     "spend_range": "$50K–$200K/month",  "median_monthly": 0.0, "is_current": true},
    {"tier": "Large",      "spend_range": "$200K–$1M/month",   "median_monthly": 0.0, "is_current": false},
    {"tier": "Enterprise", "spend_range": "$1M+/month",        "median_monthly": 0.0, "is_current": false}
  ],
  "benchmark_source": "Motion 2026 Creative Benchmarks (550K+ ads, 6,000+ advertisers, Sep 2025–Jan 2026)",
  "data_warnings": ["Launch counts include ad-set duplicates — Meta creates a new ad_id each time an existing ad is duplicated into a new ad set. Your launch count may overstate net-new creative output if your account scales via duplication."]
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
    "spend": "216029.38",
    "active_ads": 151,
    "date_range": "last_90_days"
  },
  "analyses": [
    {
      "id": "test_and_learn",
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

**Contract: `overview.spend` must be a raw numeric string with no currency symbol or commas** — e.g. `"216029.38"`, NOT `"$216,029"` or `"216,029.38 USD"`. The dashboard calls `float()` on this value directly and will crash on formatted strings.

Include all 7 analyses in order. Each analysis MUST include an `id` field — the dashboard keys its chart renderer off this value, not the title. Use exactly these ids:

| # | id | title (can be any human-readable string) |
|---|---|---|
| 1 | `test_and_learn` | Test & Learn Spend Optimization |
| 2 | `creative_allocation` | Creative Allocation |
| 3 | `old_creative` | Reliance on Old Creative |
| 4 | `creative_churn` | Creative Churn |
| 5 | `slugging_rate` | Production & Slugging Rate |
| 6 | `rolling_reach` | Rolling Reach |
| 7 | `volume_vs_spend` | Creative Volume vs. Spend (Motion 2026 Benchmarks) |

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

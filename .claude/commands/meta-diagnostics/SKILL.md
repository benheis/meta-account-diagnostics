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

### Shared Step — Build concept-level maps (run ONCE before any analysis)

Meta creates a new `ad_id` with a new `created_time` every time an existing creative is duplicated into a new ad set. All analyses must operate on **creative concepts** (unique names), not raw `ad_id` rows. Before running any analysis, build the following two maps from `ads_6m`. Also build `concept_aggregates_90d` from `ads_90d` using the same logic (for A1 and A2).

**Concept key normalization (apply before keying either map):**
Before using an ad name as a map key, normalize it by stripping Meta's auto-duplicate suffixes. Meta appends these suffixes when a media manager duplicates an ad in the UI:
- Strip trailing `" - Copy"`, `" - Copy 2"`, `" - Copy N"` (any non-negative integer N; case-insensitive) from the end of the name
- Apply iteratively until the name is stable (handles `"X - Copy - Copy"`)
- Trim whitespace after stripping
- The **canonical key** is the normalized name (used only for grouping — never displayed)
- The **display name** for charts is the **longest raw name string** within each canonical-key cluster (preserves the full naming-convention version)
- Each concept entry must carry `name_variants: list[str]` of every raw name string that collapsed into it

Example: `"BrandonPodcast-V4-Video - Copy"` and `"BrandonPodcast-V4-Video"` share canonical key `"BrandonPodcast-V4-Video"`. Display name = `"BrandonPodcast-V4-Video"` (the longer, fully-tagged version if available). `name_variants = ["BrandonPodcast-V4-Video", "BrandonPodcast-V4-Video - Copy"]`.

**Map 1 — `concept_aggregates`** (used by A1, A2, A5):
For each canonical key in `ads_6m`, sum `spend` and `conversions` across ALL `ad_id` rows sharing that canonical key. Compute `cpa` from the sums (not mean of per-row CPAs). Record `first_seen` (earliest `created_time`) and `ad_id_count`.
```
concept_aggregates[display_name] = {
  spend:         sum of spend across all ad_ids with this canonical key,
  conversions:   sum of conversions across all ad_ids with this canonical key,
  cpa:           spend / conversions  (0 if conversions = 0),
  ad_id_count:   count of ad_id rows collapsed,
  first_seen:    earliest created_time across all ad_ids with this canonical key,
  name_variants: list of all raw name strings in this cluster
}
```
`concept_aggregates_90d` is built identically from `ads_90d`.

**Map 2 — `concept_first_launch_months`** (used by A3, A4, A5, A7):
For each canonical key in `ads_6m`, record the earliest `created_time` calendar month (YYYY-MM). This is the concept's true launch month regardless of later duplications.
```
concept_first_launch_months[display_name] = earliest YYYY-MM of created_time across all ad_ids with that canonical key
```

**Truncation caveat:** If a creative was first launched BEFORE the start of `ads_6m`, its earliest visible month will be incorrectly attributed as its launch month. Flag the earliest calendar month present in the data as `truncation_warning: true` in analyses that use `concept_first_launch_months`.

---

### Analysis 1: Test & Learn Spend Optimization

**Data used:** `concept_aggregates_90d` (built from `ads_90d` in the Shared Step above)

**Calculations:**
1. For each concept in `concept_aggregates_90d`, use the aggregated `spend` and `cpa` fields. CPA is already computed from lifetime sums — do not re-derive it from individual ad rows.
2. Compute `account_median_cpa` = median CPA of all concepts with CPA > 0.
3. Compute `account_median_spend` = median spend of all concepts.
4. Derive spend thresholds from the account's own spend distribution (so they scale with account size):
   - `concept_spends` = sorted list of all concept spend values in `concept_aggregates_90d`
   - `testing_max_spend` = max(`allocation_min_spend`, P25 of `concept_spends`)
   - `scaled_min_spend`  = P75 of `concept_spends`
   - `red_cpa_multiple`  = 2.0 (unchanged)
   - On a $72K/month account: P75 ≈ $5K, P25 ≈ $500. On a $1M/day account: P75 ≈ $50K, P25 ≈ $5K. No hardcoded assumption.
5. Zone each concept (evaluated in order; first match wins):
   - **Red**:    `spend ≥ testing_max_spend` AND `cpa ≥ red_cpa_multiple × account_median_cpa`
   - **Purple**: `spend ≥ scaled_min_spend`  AND `0 < cpa ≤ account_median_cpa`
   - **Green**:  `spend < testing_max_spend` AND `(cpa = 0 OR cpa ≤ account_median_cpa)`
   - **Unzoned**: everything else — visible on chart in neutral grey, excluded from concentration math
6. Compute:
   - `red_spend_pct`      = sum of Red zone spend / total spend × 100
   - `winner_spend_pct`   = sum of Purple zone spend / total spend × 100
   - `testing_budget_pct` = sum of Green zone spend / total spend × 100
   - `zone_concentration` — per-zone count, spend, spend_pct, conversions, conversions_pct

**Verdict:**
- HEALTHY: `winner_spend_pct > 40` AND `testing_budget_pct` between 10–20 AND `red_spend_pct < 15`
- WARNING: `winner_spend_pct` 20–40 OR `red_spend_pct` 15–25
- CRITICAL: `red_spend_pct > 25` OR (no Purple concepts — no scaled winners at all)

**Meaning (examples):**
- HEALTHY: "Your testing budget is well-allocated — winners are scaling and losers are being cut."
- WARNING: "Budget is spreading into underperforming ads; consider consolidating spend on your top performers."
- CRITICAL: "Over {red_spend_pct:.0f}% of your budget is on ads with high CPA and high spend — these are scaled losers that need to be cut immediately."

**Action (examples):**
- HEALTHY: "Keep current allocation — review Red zone ads quarterly."
- WARNING: "Pause the top 3 Red zone ads by spend this week and reallocate budget to Purple zone."
- CRITICAL: "List all Red zone ads and pause any with lifetime spend above the testing floor and CPA above 2× account median. Do this before the next billing period."

**Dashboard data dict:**
```json
{
  "ads": [{"name": "...", "spend": 0.0, "cpa": 0.0, "conversions": 0, "ad_id_count": 1,
           "zone": "Green|Red|Purple|Unzoned"}],
  "cpa_label": "Purchase Cost (paid subscription sign-up)",
  "account_median_cpa": 0.0,
  "red_spend_pct": 0.0,
  "winner_spend_pct": 0.0,
  "testing_budget_pct": 0.0,
  "zone_concentration": {
    "purple":  {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
    "red":     {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
    "green":   {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0},
    "unzoned": {"count": 0, "spend": 0.0, "spend_pct": 0.0, "conversions": 0.0, "conversions_pct": 0.0}
  },
  "box_thresholds": {
    "testing_max_spend": 0.0,
    "scaled_min_spend":  0.0,
    "red_cpa_multiple":  2.0,
    "median_cpa":        0.0
  }
}
```

---

### Analysis 2: Creative Allocation

**Data used:** `concept_aggregates_90d` (reuse from Analysis 1 — no new API call)

**Calculations:**
1. Separate concepts from `concept_aggregates_90d` into three pools:
   - **Ranked pool**: CPA > 0 AND conversions ≥ 1 AND spend ≥ `allocation_min_spend` (default `$500`; read from config). The only concepts eligible for percentile tiers.
   - **Sub-threshold**: CPA > 0 AND conversions ≥ 1 AND spend < `allocation_min_spend`. Tagged `"Other (untested)"` — the account hasn't put enough money behind these to call them winners or losers. Excluded from percentile math but counted in `sub_threshold_spend_pct`.
   - **Unranked**: CPA = 0 or conversions = 0. Tagged `"Other (no conversions)"`. Excluded from all percentile math.
2. Rank the ranked pool by CPA ascending (lowest CPA = best).
3. Identify top 1% by count (ceil) and top 10% by count — from the ranked pool only.
4. Compute:
   - `top_1pct_spend_pct` = spend in top 1% / total spend × 100
   - `top_10pct_spend_pct` = spend in top 10% / total spend × 100
   - `sub_threshold_spend_pct` = spend in sub-threshold pool / total spend × 100
5. Tag each concept: `"Top 1%"`, `"Top 10%"`, `"Other (untested)"`, or `"Other (no conversions)"`
6. Spend-weighted avg CPA = sum(spend × cpa) / sum(spend) — all concepts with spend > 0
7. Unweighted median CPA = median(cpa) of the ranked pool only
8. `budget_waste_signal` = spend_weighted_avg_cpa - unweighted_median_cpa (positive = budget is concentrated on worse-than-median ads)

**Verdict:**
- HEALTHY: `top_10pct_spend_pct > 50` AND `sub_threshold_spend_pct` between 5–25 (budget concentrated on winners, healthy testing pool)
- WARNING: `top_10pct_spend_pct` 30–50 OR `sub_threshold_spend_pct > 25` (too much budget stuck in the untested pool, never graduating)
- CRITICAL: `top_10pct_spend_pct < 30` OR `budget_waste_signal > 20% of median CPA`

**Dashboard data dict:**
```json
{
  "ads": [{"name": "...", "spend": 0.0, "cpa": 0.0, "conversions": 0,
           "ad_id_count": 1, "tier": "Top 1%|Top 10%|Other (untested)|Other (no conversions)"}],
  "top_1pct_spend_pct": 0.0,
  "top_10pct_spend_pct": 0.0,
  "sub_threshold_spend_pct": 0.0,
  "allocation_min_spend": 500,
  "budget_waste_signal": 0.0
}
```

---

### Analysis 3: Reliance on Old Creative

**Data used:** `ad_monthly_spend` (Pull E) + `concept_first_launch_months` (Shared Step)

**Calculations:**
1. From `ad_monthly_spend`, iterate over all (ad, month) pairs where the ad's spend in that month is > 0.
2. For each pair, compute `age_at_month` using the **concept's** true first launch date, not the individual ad_id's `created_time`:
   `age_at_month = (first day of that calendar month − date(concept_first_launch_months[ad.name])).days`
   This ensures a creative duplicated into a new ad set in January from a September original is correctly aged 120+ days in January, not 0 days.
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

**Data used:** `ad_monthly_spend` (Pull E) + `concept_first_launch_months` (Shared Step)

**Calculations:**

Step 1 — Group concepts into launch cohorts:
- For each ad in `ad_monthly_spend`, use `concept_first_launch_months[ad.name]` as the cohort key (not `ad.created_time`). This correctly attributes all duplicates of a concept to the month it was first introduced.
- Build a dict: `cohorts = { "2025-11": [name1, name2, ...], "2025-12": [...], ... }`

Step 2 — Build `cohort_spend_by_month`:
- Enumerate every calendar month M in the 6-month window.
- For each cohort C launched on or before M, sum `monthly_spend[month == M].spend` across ALL ad_ids whose name belongs to C (aggregating spend across duplicates).
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
- `monthly_launches` = for each month M, count of unique concepts whose `concept_first_launch_months` value equals M. (Used as fallback chart when cohort spend curves are unavailable — counts concepts, not raw `ad_id` rows.)

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

**Data used:** `concept_aggregates` + `concept_first_launch_months` (Shared Step)

**Config parameters used:**
- `winner_top_percentile` (default 0.20) — top X% by CPA among converted concepts = winners
- `winner_threshold`, `winner_min_spend`, `window_days` — DEPRECATED. If present in config, emit a warning and ignore. Do not crash.

**Calculations:**

Step 1 — Assign each concept its true launch month using `concept_first_launch_months`.

Step 2 — Build calendar-month windows (6 months, non-overlapping, one per calendar month):
Each window = one calendar month M. Assign each concept in `concept_aggregates` to its `first_launch_month`.

Step 3 — Score each window:
```
For each calendar month M:
  concepts   = all concepts where first_launch_month == M
  converted  = [c for c in concepts if c.conversions ≥ 1]
  zero_conv  = [c for c in concepts if c.conversions == 0]

  if len(concepts) < 3: scoreable = false; hit_rate = null

  elif not converted: hit_rate = 0.0; winners = []

  else:
    sort converted by CPA ascending
    idx = floor(winner_top_percentile × len(converted))
    cpa_threshold = converted[idx].cpa
    winners = [c for c in converted if c.cpa ≤ cpa_threshold]
    hit_rate = len(winners) / len(concepts) × 100
```
**The denominator is `len(concepts)` — ALL concepts launched that month, including zero-conversion ones.** No spend gate. Every concept the team put in market is a launch decision that counts.

Step 4 — Verdict vs Motion benchmark (not tautological percentile target):
```
target = motion_avg_hit_rate_for_context  (e.g. 8.13% for Medium-tier Finance)
recent_avg = mean(hit_rate of last 2 scoreable months)
prior_avg  = mean(hit_rate of 2 months before that) if ≥ 2 prior exist, else null

CRITICAL:          recent_avg < target × 0.5  OR  zero winners across last 2 scoreable months
WARNING:           recent_avg < target × 0.8  OR  (prior_avg not null AND recent_avg < prior_avg × 0.8)
HEALTHY:           recent_avg ≥ target × 0.8
INSUFFICIENT_DATA: fewer than 2 scoreable months
```

**Meaning / action copy:**
- HEALTHY: "Producing winners at {recent_avg:.1f}% hit rate vs Motion {target:.1f}% benchmark. Hit rate stable or improving month-over-month."
- WARNING — below benchmark: "Hit rate {recent_avg:.1f}% is below the Motion {target:.1f}% benchmark for your tier. More concepts launching with zero conversions than expected."
- WARNING — declining: "Hit rate dropped from {prior_avg:.1f}% to {recent_avg:.1f}%. Review concepts launched in {recent month} — high throughput with low win rate."
- CRITICAL — zero winners: "No winning concepts in the last two months. Halt current creative direction; brief 5 net-new angles this week."
- INSUFFICIENT_DATA: "Need ≥3 concepts launched in at least 2 months to compute trend. Run again after more data matures."

**Dashboard data dict:**
```json
{
  "windows": [
    {
      "month": "2026-01",
      "label": "Jan 2026",
      "is_partial_month": false,
      "truncation_warning": false,
      "concepts_total": 41,
      "converted_count": 9,
      "zero_conv_count": 32,
      "winners": 2,
      "hit_rate": 4.9,
      "winner_cpa_threshold": 250.98,
      "ad_id_count": 82,
      "duplicate_pct": 50.0,
      "scoreable": true
    }
  ],
  "winner_top_percentile": 0.20,
  "recent_avg_hit_rate": 16.25,
  "prior_avg_hit_rate": 8.35,
  "motion_benchmark": 8.13,
  "spend_tier": "Medium",
  "verdict_reference": "motion"
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

**Data used:** `concept_first_launch_months` (Shared Step). Spend tier from Analysis 5.

**Calculations:**
1. Count unique concepts launched per calendar month using `concept_first_launch_months`. Each concept is counted once — in its true first-launch month — regardless of how many `ad_id` duplicates exist in `ads_6m`. Do NOT count raw `ad_id` rows from `ads_6m.created_time`.
2. avg_monthly_launches = mean of last 3 months' concept launch counts.
3. Look up Motion median weekly volume for user's vertical + tier from `motion-benchmarks.json`.
   - If value is null (suppressed), fall back to `all_verticals_fallback` for that tier.
4. Convert weekly to monthly: benchmark_weekly × 4.33.
5. Top quartile monthly = top_quartile_weekly × 4.33.
6. Compare: user launches vs median vs top quartile.
7. Note: Motion median = 50th percentile (average account). Top quartile is the real competitive benchmark. Motion's count methodology reflects intentional creative tests, not ad-object duplications — concept-level counting here aligns with their methodology.

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
- `launch_window.monthly_counts`: the concept-level launch count (unique concepts) for each of those 3 months

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
  "data_warnings": []
}
```

---

---

## DATA QUALITY PASS (run after all 7 analyses, before writing results.json)

### Likely-related concept detection

After `concept_aggregates` is finalized and all 7 analyses have run, perform a prefix-similarity scan to detect concept-name pairs that share a long common prefix but were **not** merged by canonical normalization (i.e., they have different canonical keys — neither is a `" - Copy"` variant of the other).

**Algorithm:**
For each pair of distinct display names in `concept_aggregates`:
1. Normalize each name: lowercase, keep only alphanumeric characters (strip hyphens, spaces, punctuation)
2. Compute their Longest Common Prefix (LCP) on the normalized strings
3. Flag as "likely related" if: `len(LCP) ≥ 30` AND `len(LCP) / min(len(normalized_a), len(normalized_b)) ≥ 0.60`
4. Group flagged pairs into clusters (union-find or simple greedy: if A~B and B~C then {A,B,C} is one cluster)
5. For each cluster, compute `cluster_spend` = sum of member concept spend; include `evidence` = a brief description of why they matched (e.g. "Names share 82 chars of prefix; one is a strict prefix of the other")

Emit the result as a top-level `data_quality` block in `results.json` (sibling to `overview` and `analyses`):

```json
{
  "data_quality": {
    "likely_related_concept_clusters": [
      {
        "cluster_spend": 12852.20,
        "members": [
          {"name": "IfSomeoneJust...-V6-Video-...", "spend": 9858.84, "ad_id_count": 6,
           "conversions": 22, "cpa": 448.13},
          {"name": "IfSomeoneJust...", "spend": 2993.36, "ad_id_count": 1,
           "conversions": 6, "cpa": 498.89}
        ],
        "evidence": "Names share 82 chars of prefix; one is a strict prefix of the other"
      }
    ],
    "total_clusters": 0,
    "total_spend_in_clusters": 0.0,
    "spend_pct_of_total": 0.0
  }
}
```

If no clusters are found, emit `data_quality` with an empty `likely_related_concept_clusters` list and zeroed totals. **Never omit the `data_quality` key** — the dashboard checks for its presence.

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
  "data_quality": { ...as specified in Data Quality Pass above... },
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

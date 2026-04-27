# Meta Diagnostics — Analysis Logic Reference

This document explains how each of the 7 analyses is constructed: what data goes in, what the calculations actually do, what the verdict thresholds mean, and where the design assumptions live. Written for QA and calibration review.

---

## Data Pulls (Phase 3 inputs)

| Variable | Tool | Window | Used by |
|---|---|---|---|
| `ads_90d` | `meta_get_ads` | last 90 days | A1, A2 |
| `ads_6m` | `meta_get_ads` | last 6 months | A4 (fallback), A5, A7 |
| `ad_monthly_spend` | `meta_get_ad_monthly_spend` | 6 months | A3, A4 |
| `monthly_reach` | `meta_get_monthly_reach` | 13 months | A6 |
| `account_overview` | `meta_get_account_overview` | last 90 days | A7 (run rate) |

"CPA" throughout = the user's configured `conversion_event` looked up in the `cost_per_action_type` array. If the event isn't present for a given ad, CPA is recorded as 0.

---

## Analysis 1: Test & Learn Spend Optimization

**Question it answers:** Is the budget concentrated on high-performing ads, or is it spread across scaled losers?

### Inputs
`ads_90d` — lifetime spend and CPA per ad over the last 90 days.

### Calculations

**Step 1 — CPA extraction**
For each ad, find the configured `conversion_event` in `cost_per_action_type`. If absent, CPA = 0.

**Step 2 — Account baselines**
- `account_median_cpa` = median of all ads where CPA > 0 (zero-CPA ads excluded from this calculation)
- `account_median_spend` = median spend across all ads (no exclusion)

**Step 3 — Zone assignment** (evaluated in order; first match wins)
- **Red**: CPA > 2× `account_median_cpa` AND spend > $500 → scaled losers burning money
- **Purple**: lowest-CPA 10% of all ads by count (using `ceil`) → winners
- **Green**: everything else

**Step 4 — Portfolio metrics**
- `red_spend_pct` = Red zone spend / total spend × 100
- `winner_spend_pct` = Purple zone spend / total spend × 100
- `testing_budget_pct` = spend on ads with spend < $500 / total spend × 100

### Verdict thresholds
| Verdict | Conditions |
|---|---|
| HEALTHY | winner_spend_pct > 40% AND testing_budget_pct 10–20% AND red_spend_pct < 15% |
| WARNING | winner_spend_pct 20–40% OR red_spend_pct 15–25% |
| CRITICAL | red_spend_pct > 25% OR all ads have spend < 5% of total (no clear winner) |

### Design notes and open questions
- **CPA = 0 can land an ad in Purple.** An ad with zero conversions has CPA = 0, which ranks it as the "best" CPA in the account. It would be sorted into the lowest-CPA 10% and labeled a winner. This is likely wrong — needs an explicit `conversions > 0` guard on the Purple zone, or the ranking step should exclude CPA = 0 ads. **Flag for fix.**
- **$500 testing threshold is hardcoded.** On a $72K/month account, this is a very low bar. An ad needs to spend < $500 to count as "testing." Most real tests probably spend more than that before a call is made. Worth making this configurable or scaling it to a % of median spend.
- **Red zone requires both criteria (AND, not OR).** An ad with very high CPA but only $50 spend is Green, not Red. This is intentional — you don't want to penalize an ad that's barely launched. But it means a Red ad needs to have already scaled.

---

## Analysis 2: Creative Allocation

**Question it answers:** Is budget flowing toward the best-performing ads, or is it spread evenly regardless of performance?

### Inputs
`ads_90d` (reused from A1, no additional API call).

### Calculations

**Step 1 — CPA ranking**
Sort all ads by CPA ascending (lower CPA = better performance). Ads with CPA = 0 sort to the top of the ranking.

**Step 2 — Percentile tiers**
- Top 1% by count: `ceil(0.01 × total_ads)` lowest-CPA ads
- Top 10% by count: `ceil(0.10 × total_ads)` lowest-CPA ads
- Everything else: "Other"

**Step 3 — Concentration metrics**
- `top_1pct_spend_pct` = spend in top 1% / total spend × 100
- `top_10pct_spend_pct` = spend in top 10% / total spend × 100

**Step 4 — Budget waste signal**
- `spend_weighted_avg_cpa` = Σ(spend × cpa) / Σ(spend) — reflects the CPA the account is actually paying at scale
- `unweighted_median_cpa` = median(cpa across all ads)
- `budget_waste_signal` = spend_weighted_avg_cpa − unweighted_median_cpa
  - Positive: budget is concentrated on above-median-CPA ads (bad)
  - Negative or zero: budget is flowing toward below-median-CPA ads (good)

### Verdict thresholds
| Verdict | Conditions |
|---|---|
| HEALTHY | top_10pct_spend_pct > 50% |
| WARNING | top_10pct_spend_pct 30–50% |
| CRITICAL | top_10pct_spend_pct < 30% OR budget_waste_signal > 20% of `account_median_cpa` |

### Design notes and open questions
- **Same CPA = 0 issue as A1.** Ads with zero conversions rank at the top of the CPA list and land in Top 1% / Top 10%. The "best" ads in the account may include zero-conversion ads. Needs the same guard.
- **Budget waste signal can be misleading with few ads.** With a small number of ads, the spend-weighted average and unweighted median can differ for structural reasons (e.g. one high-spend ad at any CPA level). Worth checking what this number looks like on the live account before treating it as a verdict driver.
- **No minimum spend filter.** An ad with $1 spend and CPA $5 ranks as a better ad than one with $5,000 spend and CPA $20. Statistical noise at low spend levels will always skew the percentile tiers.

---

## Analysis 3: Reliance on Old Creative

**Question it answers:** When money ran during each calendar month, how old were the ads it ran on?

### Inputs
`ad_monthly_spend` (Pull E) — per-ad, per-calendar-month spend for the last 6 months.

### Calculations

**Step 1 — Age bucketing (calendar-month × age-at-spend)**
For every (ad, calendar_month) pair where spend > 0:
1. Compute `age_at_month` = (first day of that calendar month) − date(ad.`created_time`), in days
2. Assign bucket:
   - New (0–30d): age_at_month ≤ 30
   - Mid (31–60d): age_at_month 31–60
   - Aging (61–90d): age_at_month 61–90
   - Old (90d+): age_at_month > 90

**Step 2 — Accumulation**
For each (calendar_month, bucket) cell, accumulate the ad's spend-in-that-month. Each cell is initialized fresh: `{k: 0.0 for k in BUCKET_KEYS}`. The same ad can contribute spend to different bucket cells across different months (e.g. Dec spend → New, Jan spend → Mid, Feb spend → Aging).

**Step 3 — Summary metric**
`old_creative_spend_pct` = Σ(Aging + Old spend across all months) / Σ(all spend) × 100

**Step 4 — Top ads per cell**
For each (month, bucket) cell: collect constituent (ad, spend-in-that-month) pairs, sort by spend-in-that-month descending, keep top 5. Tooltip data.

### Verdict thresholds
| Verdict | Conditions |
|---|---|
| HEALTHY | old_creative_spend_pct < 40% |
| WARNING | old_creative_spend_pct 40–65% |
| CRITICAL | old_creative_spend_pct > 65% |

### Design notes and open questions
- **Thresholds were calibrated against the old metric (today-relative age, 90-day window) — not this one.** The redesign computes a 6-month rolling average of spend-by-age. For a healthy account that constantly refreshes creative, Old % will be lower under this metric than under the old one. For a static account, it'll be higher. The 40/65% bounds are inherited assumptions — **these need calibration from live data after the first clean run.**
- **An ad's contribution moves across buckets over time.** That's the intended behavior. A Dec 26 launch running spend into Jan is correctly classified as New in Jan (age ~6 days), Mid in Feb, Aging in Mar. The chart tells the story of creative freshness at the time money was actually spent.
- **`old_creative_spend_pct` is an account-level weighted average.** A month with $100K spend on old ads carries 10× the weight of a month with $10K spend. This is correct but worth being aware of — a single high-spend month on old creative can move the number significantly.

---

## Analysis 4: Creative Churn

**Question it answers:** How long do launch cohorts hold their spend levels before fading, and is launch volume accelerating or decelerating?

### Inputs
`ad_monthly_spend` (Pull E) — same dataset as A3.

### Calculations

**Step 1 — Build launch cohorts**
Group all ads by launch month (`created_time` → YYYY-MM). Result: `cohorts = {"2025-11": [ad1, ad2, ...], ...}`.

**Step 2 — Cohort spend curves**
For each calendar month M in the 6-month window:
- For each cohort C launched on or before M: sum the `monthly_spend[M]` across all ads in C
- Output one row per calendar month with one column per cohort: `{"month": "2025-11", "Nov 2025 launches": 5234.10, "Oct 2025 launches": 3201.55}`
- Cohorts with zero spend in every month are excluded from the chart

**Step 3 — Cohort half-life**
For each cohort: find its peak spend month. Find the first subsequent month where spend < 50% of that peak. Half-life = months between peak and that month (floor 1 if it drops in the very next month). `avg_cohort_half_life_weeks` = mean half-life across all cohorts × 4.33 (weeks per month).

**Step 4 — Launch trend**
`monthly_launches` = count of ads per launch month. Compare last 3 months: growing/declining/flat.

### Verdict thresholds
| Verdict | Conditions |
|---|---|
| HEALTHY | Launch volume stable or growing MoM AND cohort half-life > 6 weeks |
| WARNING | Launch volume declining 2+ months in a row OR cohort half-life < 4 weeks |
| CRITICAL | Launch volume declining AND projected to fall below Motion median for spend tier within 30 days |

### Design notes and open questions
- **Half-life for never-decaying cohorts.** If a cohort's spend never drops below 50% of its peak (e.g. it's still scaling at the 6-month mark), half-life is undefined. The SKILL doesn't specify a cap or handling for this case. Needs an explicit rule — e.g. cap at 6 months (the data window), or mark as "still active" and exclude from the average.
- **Peak month is not always the launch month.** An ad that launched in November but didn't get budget until December has its peak in December. Half-life is measured from the peak, not from launch. This is correct but means two cohorts can have similar launch dates and very different half-lives depending on when they got ramped.
- **The CRITICAL verdict references "projected to fall below Motion median"** — the projection method isn't defined in the SKILL. This is an ambiguous instruction that the LLM must interpret. It could produce inconsistent CRITICAL flags.
- **Fallback data uses even spend distribution** (lifetime spend divided evenly across active months). Actual spend is typically front-loaded (new creatives get tested hard then trimmed), so fallback cohort curves will look flatter than reality.

---

## Analysis 5: Production & Slugging Rate

**Question it answers:** Of the ads that received enough budget to be judged, what fraction cleared a quality bar — and is that fraction trending up or down?

### Inputs
`ads_6m` — lifetime spend and CPA per ad over the last 6 months.

### Config
- `window_days` (default 60): cohort window size
- `winner_top_percentile` (default 0.20): what fraction of each window's qualified pool counts as "winning"
- `winner_min_spend` (default 300): minimum lifetime spend for an ad to enter the eligible pool

### Calculations

**Step 1 — Build rolling windows**
Starting from 6 months ago, create ~5 overlapping 60-day windows stepped 30 days apart. Each window covers ads with `created_time` in [window_start, window_end]. Label each by its start/end months.

**Step 2 — Score each window independently**
For each window:
1. Partition window ads into three groups:
   - **Underspent**: spend < $300 — not enough data to judge
   - **Wasted**: spend ≥ $300 AND conversions = 0 — budget consumed with no return
   - **Qualified**: spend ≥ $300 AND conversions ≥ 1 — eligible for winner scoring
2. If qualified < 3: mark `scoreable = false`, skip. (Can't compute a meaningful threshold from 2 ads.)
3. Sort qualified by CPA ascending. `cpa_threshold` = CPA at index `floor(0.20 × N)`. For N=10: index 2, the 3rd-lowest CPA. By definition, the bottom 20% of qualified ads (by CPA) are winners.
4. `winners` = qualified with CPA ≤ threshold
5. `hit_rate_pct` = winners / qualified × 100
6. Spend split: `winner_spend`, `losing_qualified_spend`, `wasted_spend`

**Step 3 — Verdict (trend, not absolute)**
- `recent_windows` = last 2 scoreable windows; `prior_windows` = 2 before those
- `recent_avg` = mean hit rate of recent windows; `prior_avg` = mean of prior (null if fewer than 2 prior)
- `target_rate` = 20% (by definition — top 20% of qualified = 20% hit rate if scoring is fair)

| Verdict | Conditions (any one triggers) |
|---|---|
| CRITICAL | Zero winners in the 2 most recent windows OR recent_avg < 10% (0.5 × 20% target) |
| WARNING | recent_avg < 16% (0.8 × target) OR recent_avg < 0.8 × prior_avg |
| HEALTHY | recent_avg ≥ 16% AND (no prior OR recent_avg ≥ 0.8 × prior_avg) |
| INSUFFICIENT_DATA | Fewer than 2 scoreable windows |

### Design notes and open questions
- **The target hit rate is always 20% by construction.** The winner threshold is the top 20% of each window's eligible pool. In a window with 10 qualified ads, 2 will always be "winners" (CPA ≤ the 3rd-lowest CPA), meaning `hit_rate_pct` will always be exactly 20% unless the threshold is affected by ties. The metric is self-referential — it measures whether the best ads in each cohort are actually good, not whether any fixed CPA bar is being cleared. The verdict trend (is the best 20% getting better or worse?) is meaningful; the absolute 20% number is definitional.
- **Overlapping windows mean the same ad can appear in multiple windows.** An ad launched on Nov 15 would appear in both an Oct 23–Dec 22 window and a Nov 22–Jan 21 window. Its performance influences both windows' thresholds and hit rates. This introduces correlation between adjacent window scores.
- **Wasted spend (≥$300, 0 conversions) doesn't affect hit rate but is surfaced on the chart.** This is correct — wasted ads aren't in the denominator. But a window with 10 qualified ads and 15 wasted ads has a very different health picture than one with 10 qualified and 2 wasted, even if both show 20% hit rate. The chart makes this visible; the verdict doesn't capture it.
- **`winner_min_spend` at $300 may be too low or too high depending on account CPA.** At a $50 CPA, $300 = 6 conversions (reasonable). At a $500 CPA, $300 = 0–1 conversions (essentially no data). This should probably scale with `account_median_cpa`.

---

## Analysis 6: Rolling Reach

**Question it answers:** Is the account saturating its addressable audience — are we reaching the same people repeatedly, and is the cost of finding new people rising?

### Inputs
`monthly_reach` from `meta_get_monthly_reach` — 13 months of unique reach and spend per month.

### Calculations

**Step 1 — Partial month handling**
If the current month has fewer days elapsed than `days_in_month(M)`, compute `reach_per_day = reach[M] / elapsed_days` and use per-day normalized values for all trend calculations. Raw totals for partial months are not comparable to full months.

**Step 2 — Net-new reach estimation**
The core model assumption: ~50% of people reached this month were also reached in the same calendar month one year ago (audience overlap).

- **With M−12 baseline**: `net_new_reach[M] = max(reach[M] − reach[M−12] × 0.5, 0)`
- **Without M−12 baseline** (account < 12 months old): `net_new_reach[M] = reach[M] × 0.7` (assumes 70% of reach is net-new — a fixed heuristic, not derived from data)
- `net_new_ratio[M] = net_new_reach[M] / reach[M]`
- `cost_per_net_new[M] = spend[M] / net_new_reach[M]`

**Step 3 — Signal A: Is cost-per-net-new rising?**
- Take last 6 active months (excluding partial). Split: prior 3, recent 3.
- Signal A fires if `mean(recent 3 cost_per_net_new) ≥ mean(prior 3) × 1.20` (≥20% increase)
- Hard floor: if `recent_avg < $0.50`, Signal A cannot fire (cost too cheap for the increase to matter)

**Step 4 — Signal B: Is the net-new ratio structurally dropping?**
- Suppressed entirely if all months used the 0.7× fallback (ratios are all identical — can't detect saturation)
- Otherwise: fires if `mean(recent 3 net_new_ratio) ≤ mean(trailing 6 net_new_ratio) − 0.05` (≥5 percentage-point drop)

**Step 5 — Verdict**
| Signal A | Signal B | Verdict |
|---|---|---|
| True | True | CRITICAL |
| True | False | WARNING |
| False | True | WARNING |
| False | False | HEALTHY |
| All-fallback | — | INSUFFICIENT_DATA |

### Design notes and open questions
- **The 50% overlap assumption is the core model risk.** The formula `reach[M] − reach[M−12] × 0.5` assumes that 50% of this month's audience was also reached in the same calendar month last year. That's a reasonable industry heuristic but will vary by account, creative mix, and targeting structure. If your account's actual overlap is 70%, the model understates saturation. If it's 20%, it overstates it. There's no calibration mechanism.
- **The 70% fallback is a guess.** For accounts under 12 months old, `net_new_reach = reach × 0.70` with no data behind it. Signal B is suppressed in this state, which is the right call — but Signal A will still fire based on cost-per-net-new, and that cost-per-net-new is itself computed from an assumed 70% net-new rate.
- **Signal A's 20% threshold and Signal B's 5pp threshold** are not derived from the account's history — they're fixed parameters. On an account with high month-to-month variance in reach and spend (e.g. seasonal spend swings), these signals may fire spuriously.
- **The $0.50 floor on Signal A** prevents firing on very cheap reach. But the threshold is absolute, not account-relative. A finance account where $0.80 CPM is normal and a DTC account where $0.08 CPM is normal should have different floors.

---

## Analysis 7: Creative Volume vs. Spend (Motion 2026 Benchmarks)

**Question it answers:** Is the account launching enough new creative to compete at its spend level, based on Motion's 2026 benchmark data?

### Inputs
- Launch counts from `ads_6m` (ads by `created_time` month)
- Spend tier from Analysis 5 (derived from `account_overview`)
- `motion-benchmarks.json` — Motion 2026 data: median weekly testing volume by vertical × spend tier; top quartile cross-vertical by tier

### Calculations

**Step 1 — Account launch rate**
`avg_monthly_launches` = mean of last 3 calendar months' launch counts. Convert Motion weekly benchmarks → monthly by multiplying by 4.33.

**Step 2 — Benchmark lookup**
Look up `median_weekly_testing_volume[vertical][tier]` from `motion-benchmarks.json`. If the cell is null (suppressed — insufficient sample in Motion's dataset), fall back to `all_verticals_fallback` for that tier and flag `fallback_used = true`.

**Step 3 — Comparison**
- `motion_median_monthly` = benchmark_weekly × 4.33
- `motion_top_quartile_monthly` = top_quartile_weekly × 4.33
- Note: top quartile is cross-vertical (Motion doesn't publish vertical-level quartiles)

### Verdict thresholds
| Verdict | Conditions |
|---|---|
| HEALTHY | avg_monthly_launches ≥ motion_median_monthly |
| WARNING | avg_monthly_launches 50–80% of motion_median_monthly |
| CRITICAL | avg_monthly_launches < 50% of motion_median_monthly |

### Design notes and open questions
- **Motion's definition of a "launch" likely differs from Meta's `created_time`.** Motion counts intentional creative tests; `created_time` counts every ad object, including duplicates created during ad-set scaling, budget restructuring, etc. An account that duplicates 10 existing ads into a new ad set adds 10 "launches" to the count without producing any new creative. This inflates the account's launch number relative to the benchmark. Needs a caveat or deduplication logic.
- **The 4.33 weekly-to-monthly conversion is an approximation.** Months have 28–31 days. For the Motion median at ~10 creatives/week, this introduces a ±5% rounding error — acceptable. At lower volumes it matters more.
- **Spend tier is inherited from Analysis 5.** If Analysis 5 returns INSUFFICIENT_DATA, the tier may not be set. Needs a fallback — could use `account_overview` spend directly to bucket into a tier without depending on A5.
- **The benchmark is static (Motion Sep 2025–Jan 2026).** It reflects a specific 5-month window. If the account's vertical or the broader market shifts, the benchmarks will drift from reality. Worth noting in the report that these are point-in-time norms, not timeless standards.
- **Top-quartile is always cross-vertical.** The chart shows it as a separate bar with a different pattern fill and a caption note. This means comparing yourself to the top quartile is comparing yourself to the best performers across all verticals at your spend level — a very high bar.

---

## Cross-Analysis Dependencies and Known Gaps

### The CPA = 0 problem (A1 and A2)
Both analyses assign CPA = 0 to ads without a recorded conversion. Zero-CPA ads then rank as the "best" performers in any CPA-ascending sort. This means:
- In A1: zero-conversion ads can appear in the Purple (winner) zone
- In A2: zero-conversion ads can appear in Top 1% / Top 10%

**The fix**: exclude ads with CPA = 0 (or conversions = 0) from all CPA-ranking logic in A1 and A2. They should be treated as unscored, not as perfect performers.

### Ad duplication affects A3, A4, A5, A7
Meta creates a new `ad_id` (with a new `created_time`) every time an existing ad is duplicated into a new ad set. This means:
- A3: a "December creative" duplicated in January shows its large-budget January instance in the New bucket in January — correct behavior, but counterintuitive if you're thinking of the creative concept, not the ad object
- A4: the same concept can appear as multiple launch-month cohorts
- A5: duplicated ads enter the scoring pool for the window in which they were duplicated, regardless of when the original concept launched
- A7: launch counts include duplicates, inflating the number vs. Motion's definition

There's no clean fix for this without concept-level deduplication (collapsing ad objects sharing a name root). The current behavior is consistent — it operates at `ad_id` level throughout — but it diverges from how a marketer thinks about "a creative."

### Spend tier dependency chain
A7's benchmark lookup depends on the spend tier. The spend tier is computed from `account_overview`. If `account_overview` fails or is missing, A7 could fail or use a wrong tier. A5's spend tier field in the data dict has the same dependency. Both analyses should have an explicit fallback that derives tier from `account_overview.spend / 3` (to annualize 90d spend) independently.

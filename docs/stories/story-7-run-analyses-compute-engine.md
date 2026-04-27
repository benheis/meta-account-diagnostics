# Story 7: `_run_analyses.py` — Deterministic Compute Engine — Brownfield Addition

**Size:** Large | **Source:** Architecture Review (Hybrid Compute Architecture) | **Commit baseline:** `f5b69a3`

> **Escalation note:** This story can split into 7a (Shared Step + A1 + A2 + A3) and 7b (A4 + A5 + A6 + A7 + Data Quality) if implementation scope becomes unmanageable. The split point is after A3 — concept maps and the 90d analyses are one cohesive block, the temporal/cohort analyses are another.

> **Dependencies:** Story 5 (config schema with `target_cpa`, `allocation_min_spend`, `winner_top_percentile`) and Story 6 (raw JSON files in `~/meta-diagnostics/raw/`) must be implemented first.

---

## User Story

As a media manager running the diagnostic on any account size,
I want all numerical analysis to be computed by a Python script that reads stable data files,
So that I get correct, reproducible numbers regardless of whether I have 20 concepts or 500.

---

## Story Context

**Existing System Integration:**
- New file: `.claude/commands/meta-diagnostics/_run_analyses.py`
- Reads: `~/meta-diagnostics/raw/*.json` (5 files from Story 6), `~/.meta-diagnostics-config.json`, `{skill_dir}/motion-benchmarks.json`
- Writes: `~/meta-diagnostics/computed.json` (input to Story 8's Phase 4 rewrite)
- Technology: Python 3.10+, stdlib only (`json`, `re`, `os`, `math`, `statistics`, `collections`, `datetime`, `argparse`) — no external dependencies
- Follows pattern: existing `_to_float()`, `_fmt_usd()` helpers in dashboard_template.py; same data dict specs as current SKILL.md Phase 4
- Touch points: new file only — SKILL.md integration handled in Story 8

**Background:**
Currently the LLM computes all analysis numbers in-context. This is unreliable at scale: arithmetic degrades at N>100 concepts, the LCP data quality pass fails above ~150 concepts, and two runs of identical data can produce different numbers. This script moves all computation to deterministic Python. The LLM's role in Phase 4 becomes: run this script, read the output, write meaning/action/verdict copy. All data fields in the output JSON are computed here; all text fields (meaning, action) are left empty for the LLM to fill.

**Critical architecture notes resolved by this story:**
- CRITICAL-3: A3/A4 raw name → display_name lookup (reverse lookup dict built here)
- CRITICAL-4: Spend tier determination (monthly run rate → motion-benchmarks.json lookup)
- CRITICAL-5: `motion-benchmarks.json` path (passed as `--skill-dir` CLI arg)
- CRITICAL-6: Verdict evaluation order (Python if/elif enforces CRITICAL → WARNING → HEALTHY)
- MED-1: LCP O(N²) failure at scale (Python handles 500+ concepts in milliseconds)

---

## Acceptance Criteria

### CLI Interface

1. Script is invokable as:
   ```
   python3 _run_analyses.py \
     --skill-dir <path to directory containing SKILL.md and motion-benchmarks.json> \
     --raw-dir ~/meta-diagnostics/raw \
     --config ~/.meta-diagnostics-config.json \
     --output ~/meta-diagnostics/computed.json
   ```
2. All arguments have sensible defaults:
   - `--skill-dir`: directory of the script itself (`os.path.dirname(os.path.abspath(__file__))`)
   - `--raw-dir`: `~/meta-diagnostics/raw`
   - `--config`: `~/.meta-diagnostics-config.json`
   - `--output`: `~/meta-diagnostics/computed.json`
3. On success: exits with code 0, prints `"computed.json written to <path>"`.
4. On fatal error (missing raw file, corrupt JSON): exits with code 1, prints a human-readable error message.

### Shared Step — Concept Map Building

5. **Canonical normalization** strips trailing Meta copy suffixes iteratively:
   - Pattern: `\s*-\s*copy(\s+\d+)?$` (case-insensitive)
   - Applied in a while loop until the name is stable
   - Whitespace trimmed after each strip
6. **`concept_aggregates`** built from `ads_6m.json`:
   - Keyed by display_name (longest raw name string per canonical cluster)
   - `spend`: sum of all ad_id spend values in cluster
   - `conversions`: sum of all ad_id conversion values
   - `cpa`: spend / conversions (0.0 if conversions = 0)
   - `ad_id_count`: count of ad_id rows
   - `first_seen`: earliest `created_time` in cluster (ISO string)
   - `name_variants`: list of all raw name strings in cluster
7. **`concept_aggregates_90d`** built from `ads_90d.json` using identical logic.
8. **`concept_first_launch_months`**: for each concept in `concept_aggregates`, earliest `created_time` calendar month (YYYY-MM).
9. **`name_to_concept`** reverse lookup: maps every raw name string (including all " - Copy" variants) to its display_name. Used in A3/A4 to safely look up any raw `ad_id` name.
10. If `ads_90d.json` or `ads_6m.json` contain `{"error": ..., "data": []}`, treat as empty arrays — log a warning, do not crash.

### Analysis 1 — Test & Learn (data from concept_aggregates_90d)

11. P25 and P75 of concept spend values computed correctly (linear interpolation between adjacent values).
12. `testing_max_spend = max(allocation_min_spend, P25)`, `scaled_min_spend = P75`.
13. `account_median_cpa` = median of all concept CPA values where CPA > 0.
14. Zone assignment in first-match order: Red → Purple → Green → Unzoned.
15. `zone_concentration` computed per zone: count, spend sum, spend_pct (of total account spend), conversions sum, conversions_pct.
16. `red_spend_pct`, `winner_spend_pct`, `testing_budget_pct` computed from zone sums.
17. Verdict: check CRITICAL conditions first, then WARNING, then HEALTHY. Assign `"INSUFFICIENT_DATA"` if concept_aggregates_90d is empty.
18. Output includes full `ads` array, `zone_concentration`, `box_thresholds` — matching existing data dict spec.

### Analysis 2 — Creative Allocation (data from concept_aggregates_90d)

19. Three pools correctly separated using `allocation_min_spend` from config.
20. Percentile ranking by CPA ascending (lowest CPA = best = top of pool).
21. Top 1% = `ceil(0.01 × len(ranked_pool))` concepts by count; Top 10% = `ceil(0.10 × len(ranked_pool))`.
22. `sub_threshold_spend_pct` = sub-threshold pool spend / total spend × 100.
23. `budget_waste_signal` = spend-weighted avg CPA − unweighted median CPA of ranked pool.
24. Verdict: CRITICAL → WARNING → HEALTHY precedence.
25. Each concept in `ads` array carries `cpa`, `conversions`, `ad_id_count`, `tier`.

### Analysis 3 — Old Creative (data from ad_monthly_spend + concept_first_launch_months)

26. All ad name lookups use `name_to_concept[ad_name]` → display_name → `concept_first_launch_months[display_name]`. If `ad_name` not in `name_to_concept`, skip that ad_id row (emit a count of skipped rows in `data_warnings`).
27. `age_at_month` = (first day of calendar_month − date(concept_first_launch_months[concept])).days. Result in days — never negative (if somehow negative, clamp to 0).
28. Bucket assignment:
    - New (0-30d): age_at_month ≤ 30
    - Mid (31-60d): age_at_month 31–60
    - Aging (61-90d): age_at_month 61–90
    - Old (90d+): age_at_month > 90
29. Each (month, bucket) cell is a fresh dict — no shared mutable accumulator across cells.
30. `old_creative_spend_pct` = sum of (Aging + Old) spend / total spend × 100.
31. Top-5 ads per (month, bucket): sorted by spend-in-that-month descending; names truncated to 60 chars with `…`.
32. Verdict: CRITICAL → WARNING → HEALTHY.

### Analysis 4 — Creative Churn (data from ad_monthly_spend + concept_first_launch_months)

33. Cohort key for each ad = `concept_first_launch_months[name_to_concept[ad.name]]` (not ad.created_time). Skip ads not in name_to_concept.
34. `cohort_spend_by_month`: for each calendar month M in the 6m window, for each cohort launched on or before M, sum spend of all ad_ids belonging to that cohort in month M.
35. Cohort column name format: `"{Mon YYYY} launches"` (e.g., `"Nov 2025 launches"`).
36. Cohort half-life: find peak spend month, find first subsequent month where spend < 50% of peak.
    - If found: half_life = months between peak and that month (minimum 1).
    - If never drops below 50%: half_life = data_window_months (last month index − cohort first month index + 1). Flag as `still_active: true`.
37. `avg_cohort_half_life_weeks` = mean(all half-lives) × 4.33. Include still-active cohorts in mean.
38. `monthly_launches` = for each month M, count of unique concepts where `concept_first_launch_months[concept] == M`.
39. Launch trend: compare last 3 monthly_launches counts. Growing = each > prior. Declining = each < prior. Flat = otherwise.
40. **Fallback** if `ad_monthly_spend.json` is empty or errored: distribute each ad's `ads_6m` lifetime spend evenly across months from launch month to last month in data window. Emit `data_warnings: ["Cohort spend approximated using even distribution..."]`.
41. Verdict: CRITICAL → WARNING → HEALTHY.

### Analysis 5 — Production & Slugging Rate (data from concept_aggregates + concept_first_launch_months)

42. **Spend tier determination** (computed here, used by A5 and A7):
    - `account_monthly_run_rate` = `account_overview.spend` (90d total) / 3
    - Match against tier thresholds: Micro < $10K, Small $10K–$50K, Medium $50K–$200K, Large $200K–$1M, Enterprise $1M+
    - Read `avg_hit_rate_by_tier[tier]["hit_rate_pct"]` from `motion-benchmarks.json` as `motion_target_hit_rate`
43. Per calendar-month window (6 months):
    - `concepts` = all concepts where `concept_first_launch_months[concept] == M`
    - `converted` = [c for c in concepts if c.conversions ≥ 1]
    - `zero_conv` = [c for c in concepts if c.conversions == 0]
    - `scoreable` = len(concepts) ≥ 3
44. **Winner selection** (two modes):
    - If `target_cpa` is set (non-null): `winners = [c for c in converted if c.cpa ≤ target_cpa and c.conversions ≥ 3]`. `winner_cpa_threshold = target_cpa`.
    - If `target_cpa` is null: sort `converted` by CPA ascending, `idx = floor(winner_top_percentile × len(converted))`, `cpa_threshold = converted[idx].cpa`, `winners = [c for c in converted if c.cpa ≤ cpa_threshold]`.
    - **Denominator is always `len(concepts)`** — all launched that month, including zero-conversion ones.
45. `hit_rate = len(winners) / len(concepts) × 100` (null if not scoreable).
46. Verdict computation:
    - Find last 2 scoreable months → `recent_avg`; 2 before those → `prior_avg`
    - If fewer than 2 scoreable months → `"INSUFFICIENT_DATA"`
    - CRITICAL: `recent_avg < motion_target_hit_rate × 0.5` OR zero winners in last 2 scoreable months
    - WARNING: `recent_avg < motion_target_hit_rate × 0.8` OR `(prior_avg not null AND recent_avg < prior_avg × 0.8)`
    - HEALTHY: `recent_avg ≥ motion_target_hit_rate × 0.8`
47. Output includes `windows` array, `recent_avg_hit_rate`, `prior_avg_hit_rate`, `motion_benchmark`, `spend_tier`, `winner_top_percentile`, `verdict_reference: "motion"`.

### Analysis 6 — Rolling Reach (data from monthly_reach + ad_monthly_spend)

48. Monthly spend per calendar month = aggregated from `ad_monthly_spend.json` (sum all ad spend values per month). If `monthly_reach.json` already contains `spend` per month, use that instead.
49. Partial month detection: if the most recent month has fewer days elapsed than days_in_month, compute `reach_per_day` and use per-day normalization for trend comparisons.
50. `net_new_reach[M]`:
    - If M−12 data exists: `max(reach[M] − reach[M−12] × 0.5, 0)`
    - Else: `reach[M] × 0.7` (fallback); track `used_fallback = True` for this month
51. Signal A: last 6 active months (exclude partial). `prior_avg = mean(cost_per_net_new, oldest 3)`, `recent_avg = mean(cost_per_net_new, newest 3)`. Fires if `recent_avg ≥ prior_avg × 1.20` AND `recent_avg ≥ 0.50`.
52. Signal B: suppressed if all months used fallback. Otherwise: fires if `recent_3m_ratio ≤ trailing_6m_ratio − 0.05`.
53. Verdict matrix: (A=True, B=True) → CRITICAL; (A=True, B=False) or (A=False, B=True) → WARNING; (A=False, B=False) → HEALTHY; all-fallback → `"INSUFFICIENT_DATA"`.
54. Output includes all signal fields, `using_fallback`, `calculation_note`, `data_warnings`.

### Analysis 7 — Creative Volume vs. Spend (data from concept_first_launch_months + motion-benchmarks.json)

55. Monthly concept launch counts from `concept_first_launch_months` — count occurrences of each YYYY-MM value. Each concept counted once in its true first-launch month.
56. `avg_monthly_launches` = mean of last 3 months' concept launch counts.
57. Read `median_weekly_testing_volume[vertical][tier]` from `motion-benchmarks.json`. If null: use `all_verticals_fallback[tier]`. Set `fallback_used = True`.
58. `motion_median_monthly = median_weekly × 4.33`, `motion_top_quartile_monthly = top_quartile_weekly × 4.33`.
59. `tier_benchmark_table`: for all 5 tiers, read median_weekly (with fallback), convert to monthly. Mark `is_current: true` for the account's tier.
60. Verdict: HEALTHY if `avg_monthly_launches ≥ motion_median_monthly`; WARNING if 50–80% of median; CRITICAL if < 50%.
61. `launch_window.months` = names of last 3 calendar months (e.g., "Feb 2026", "Mar 2026", "Apr 2026 (MTD)"). Mark the most recent as MTD if it's a partial month.

### Data Quality Pass (after all 7 analyses)

62. Candidate set for LCP pass: concepts in `concept_aggregates` where `spend ≥ allocation_min_spend`. If candidate set > 150, additionally filter to `spend ≥ P50 of candidate spends`.
63. Normalize each name: lowercase, remove all non-alphanumeric characters.
64. Pairwise LCP check: `len(lcp) ≥ 30 AND len(lcp) / min(len(norm_a), len(norm_b)) ≥ 0.60`.
65. Cluster using union-find (correct path-compression implementation).
66. Emit clusters with > 1 member, sorted by `cluster_spend` descending.
67. `evidence` string: `f"Names share {len(lcp)} chars of normalized prefix"` (or `"one is a prefix of the other"` if one normalized name is a prefix of the other).
68. Emit `data_quality` block with `likely_related_concept_clusters`, `total_clusters`, `total_spend_in_clusters`, `spend_pct_of_total`. Always emit even if empty.

### Output Structure

69. `computed.json` matches the `results.json` schema exactly, with these fields left empty for the LLM to fill in Phase 4:
    - `analyses[*].meaning`: `""` (empty string)
    - `analyses[*].action`: `""` (empty string)
    - `analyses[*].metrics`: `{}` (empty dict — LLM formats key numbers for the markdown report)
70. All other fields are populated by Python: `run_date`, `config`, `overview`, `data_quality`, all `analyses[*].id`, `analyses[*].title`, `analyses[*].verdict`, `analyses[*].data`.
71. `overview.spend` is a raw numeric string (no `$` or commas): `str(round(total_spend, 2))`.
72. Analysis order in output array matches the existing ID order: test_and_learn → creative_allocation → old_creative → creative_churn → slugging_rate → rolling_reach → volume_vs_spend.

---

## Technical Notes

**Key Python algorithms:**

```python
import re, os, json, math, statistics
from collections import defaultdict
from datetime import date, timedelta

# --- Canonical normalization ---
COPY_PATTERN = re.compile(r'\s*-\s*copy(\s+\d+)?\s*$', re.IGNORECASE)

def canonical_name(name: str) -> str:
    prev = None
    while prev != name:
        prev = name
        name = COPY_PATTERN.sub('', name).strip()
    return name

# --- Build concept maps ---
def build_concept_maps(ads: list[dict]) -> tuple[dict, dict, dict]:
    clusters = defaultdict(list)
    for ad in ads:
        key = canonical_name(ad.get('name', ''))
        if key:
            clusters[key].append(ad)
    
    concept_aggregates = {}
    concept_first_launch_months = {}
    name_to_concept = {}  # raw name -> display_name
    
    for key, ad_list in clusters.items():
        display = max(ad_list, key=lambda a: len(a.get('name', '')))['name']
        spend = sum(float(a.get('spend', 0)) for a in ad_list)
        conversions = sum(float(a.get('conversions', 0)) for a in ad_list)
        cpa = spend / conversions if conversions > 0 else 0.0
        created_times = [a['created_time'] for a in ad_list if a.get('created_time')]
        first_seen = min(created_times) if created_times else ''
        
        concept_aggregates[display] = {
            'spend': spend, 'conversions': conversions, 'cpa': cpa,
            'ad_id_count': len(ad_list), 'first_seen': first_seen,
            'name_variants': [a['name'] for a in ad_list if a.get('name')]
        }
        concept_first_launch_months[display] = first_seen[:7] if first_seen else ''
        
        for ad in ad_list:
            if ad.get('name'):
                name_to_concept[ad['name']] = display
    
    return concept_aggregates, concept_first_launch_months, name_to_concept

# --- Percentile (linear interpolation) ---
def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)

# --- A1 zone assignment ---
def assign_a1_zones(concepts: dict, allocation_min_spend: float) -> dict:
    spends = [c['spend'] for c in concepts.values()]
    cpas = [c['cpa'] for c in concepts.values() if c['cpa'] > 0]
    testing_max = max(allocation_min_spend, percentile(spends, 25))
    scaled_min = percentile(spends, 75)
    median_cpa = statistics.median(cpas) if cpas else 0.0
    red_multiple = 2.0
    
    zones = {}
    for name, c in concepts.items():
        s, cpa = c['spend'], c['cpa']
        if s >= testing_max and cpa >= red_multiple * median_cpa:
            zones[name] = 'Red'
        elif s >= scaled_min and 0 < cpa <= median_cpa:
            zones[name] = 'Purple'
        elif s < testing_max and (cpa == 0 or cpa <= median_cpa):
            zones[name] = 'Green'
        else:
            zones[name] = 'Unzoned'
    
    return zones, testing_max, scaled_min, median_cpa, red_multiple

# --- Spend tier determination ---
def determine_tier(account_overview: dict) -> str:
    spend_90d = float(account_overview.get('spend', 0))
    monthly = spend_90d / 3
    if monthly < 10_000:   return 'Micro'
    if monthly < 50_000:   return 'Small'
    if monthly < 200_000:  return 'Medium'
    if monthly < 1_000_000: return 'Large'
    return 'Enterprise'

# --- LCP data quality pass ---
def normalize_for_lcp(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())

def lcp_len(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i

def find_lcp_clusters(concept_aggregates: dict, allocation_min_spend: float) -> list:
    candidates = {n: d for n, d in concept_aggregates.items()
                  if d['spend'] >= allocation_min_spend}
    
    # Guard: filter further if still too large
    if len(candidates) > 150:
        spend_floor = percentile([d['spend'] for d in candidates.values()], 50)
        candidates = {n: d for n, d in candidates.items()
                      if d['spend'] >= spend_floor}
    
    names = list(candidates.keys())
    normed = [normalize_for_lcp(n) for n in names]
    
    # Union-find
    parent = list(range(len(names)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        parent[find(x)] = find(y)
    
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = normed[i], normed[j]
            if not a or not b:
                continue
            ll = lcp_len(a, b)
            min_len = min(len(a), len(b))
            if min_len > 0 and ll >= 30 and ll / min_len >= 0.60:
                union(i, j)
    
    clusters = defaultdict(list)
    for i in range(len(names)):
        clusters[find(i)].append(i)
    
    result = []
    for root, idxs in clusters.items():
        if len(idxs) < 2:
            continue
        members = [names[i] for i in idxs]
        cluster_spend = sum(candidates[m]['spend'] for m in members)
        
        # Evidence
        a_n, b_n = normed[idxs[0]], normed[idxs[1]]
        ll = lcp_len(a_n, b_n)
        is_prefix = a_n.startswith(b_n) or b_n.startswith(a_n)
        evidence = ("one name is a prefix of the other" if is_prefix
                    else f"names share {ll} chars of normalized prefix")
        
        result.append({
            'cluster_spend': cluster_spend,
            'members': sorted(
                [{'name': m, 'spend': candidates[m]['spend'],
                  'ad_id_count': candidates[m]['ad_id_count'],
                  'conversions': candidates[m]['conversions'],
                  'cpa': candidates[m]['cpa']} for m in members],
                key=lambda x: x['spend'], reverse=True
            ),
            'evidence': evidence
        })
    
    return sorted(result, key=lambda c: c['cluster_spend'], reverse=True)
```

**Verdict precedence pattern (apply to all analyses):**
```python
# Always evaluate CRITICAL first, then WARNING, then HEALTHY
def a1_verdict(red_pct, winner_pct, testing_pct, has_purple):
    if red_pct > 25 or not has_purple:
        return 'CRITICAL'
    if 20 <= winner_pct <= 40 or 15 <= red_pct <= 25:
        return 'WARNING'
    if winner_pct > 40 and 10 <= testing_pct <= 20 and red_pct < 15:
        return 'HEALTHY'
    return 'WARNING'  # catch-all for anything that doesn't meet HEALTHY threshold
```

**`computed.json` output skeleton:**
```python
output = {
    "run_date": date.today().isoformat(),
    "config": config,
    "overview": {
        "spend": str(round(total_90d_spend, 2)),
        "active_ads": len(ads_90d),
        "date_range": "last_90_days"
    },
    "data_quality": data_quality_block,
    "analyses": [
        {
            "id": "test_and_learn",
            "title": "Test & Learn Spend Optimization",
            "verdict": a1_verdict_str,
            "meaning": "",   # LLM fills in Phase 4
            "action": "",    # LLM fills in Phase 4
            "metrics": {},   # LLM fills in Phase 4
            "data": a1_data_dict
        },
        # ... repeat for all 7 analyses
    ]
}
```

**Install update** (add to `install.sh` after Story 6's changes):
```bash
cp "$REPO_ROOT/.claude/commands/meta-diagnostics/_run_analyses.py" "$INSTALL_DIR/_run_analyses.py"
```
(This is included in the Story 6 install.sh as a conditional copy — Story 7 makes it unconditional.)

---

## Definition of Done

- [ ] `_run_analyses.py` created at `.claude/commands/meta-diagnostics/_run_analyses.py`
- [ ] Script runs end-to-end on `act_748122004521787` raw data; `computed.json` written successfully
- [ ] A1: Purple zone contains 6 scaled-winner concepts (not 4 tiny-spend outliers from old percentile logic)
- [ ] A2: Top 10% concepts exclude sub-threshold noise ads; verdict reflects true allocation health
- [ ] A3: No KeyError on " - Copy" ad names — all lookups route through `name_to_concept`
- [ ] A5: Spend tier correctly determined from `account_overview.spend` + motion-benchmarks.json tiers
- [ ] A5: Winner selection uses `target_cpa` if set, `winner_top_percentile` percentile if null
- [ ] Data quality pass: LCP clustering correct on test account; filters to > `allocation_min_spend` concepts before pairing
- [ ] All 7 analysis verdicts use CRITICAL → WARNING → HEALTHY evaluation order (never assign HEALTHY when CRITICAL conditions also met)
- [ ] `computed.json` is valid JSON; `meaning` and `action` fields are empty strings (reserved for LLM)
- [ ] `install.sh` updated to copy `_run_analyses.py` to install directory
- [ ] Script exits 0 on success, 1 on fatal error with informative message
- [ ] Script uses only Python stdlib — no pip installs required

---

## Risk and Compatibility Check

**Primary Risk:** `_run_analyses.py` output must exactly match the data dict schemas in the existing SKILL.md specs. Any field name mismatch causes dashboard chart functions to silently fall back to the text-only card. Validate all field names against the current data dict specs before marking done.

**Mitigation:** Run the full dashboard against computed.json on the test account and verify all 7 charts render correctly with populated data.

**Secondary Risk:** Some raw JSON fields from MCP tools may have unexpected types (e.g., `spend` as a string `"$1,234.56"` instead of a float). Add a `safe_float()` helper that strips `$`, `,` before conversion — same logic as `_to_float()` in `dashboard_template.py`.

**Rollback:** Story 8 (SKILL.md Phase 4 rewrite) makes the LLM call this script. Until Story 8 ships, this script is unused by the skill — safe to merge independently.

- [x] Dashboard unchanged — still reads `results.json` at runtime; computed.json is an intermediate file
- [x] Script failure does not break existing LLM-compute path until Story 8 replaces Phase 4
- [x] No new Python dependencies (stdlib only)
- [x] Correct handling of all error states: empty data → empty arrays in output, not crashes

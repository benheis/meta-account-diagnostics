#!/usr/bin/env python3
"""
Meta Diagnostics Compute Engine
Reads raw API data from ~/meta-diagnostics/raw/, runs all 7 analyses deterministically,
writes computed.json with all numeric fields populated and meaning/action left empty for the LLM.
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

COPY_PATTERN = re.compile(r'\s*-\s*copy(\s+\d+)?\s*$', re.IGNORECASE)


def safe_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def canonical_name(name: str) -> str:
    prev = None
    while prev != name:
        prev = name
        name = COPY_PATTERN.sub('', name).strip()
    return name


def percentile(data: list, p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def month_label(ym: str) -> str:
    """'2026-01' -> 'Jan 2026'"""
    try:
        d = datetime.strptime(ym, '%Y-%m')
        return d.strftime('%b %Y')
    except ValueError:
        return ym


def load_json(path: str, default):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and 'error' in data:
            return default
        return data
    except (json.JSONDecodeError, IOError):
        return default


# ---------------------------------------------------------------------------
# Shared Step — concept map building
# ---------------------------------------------------------------------------

def build_concept_maps(ads: list) -> tuple:
    """
    Returns:
        concept_aggregates: dict[display_name -> {spend, conversions, cpa, ad_id_count, first_seen, name_variants}]
        concept_first_launch_months: dict[display_name -> 'YYYY-MM']
        name_to_concept: dict[raw_name -> display_name]  (reverse lookup for ALL raw names including Copy variants)
    """
    clusters = defaultdict(list)
    for ad in ads:
        raw = ad.get('name', '')
        if not raw:
            continue
        key = canonical_name(raw)
        clusters[key].append(ad)

    concept_aggregates = {}
    concept_first_launch_months = {}
    name_to_concept = {}

    for key, ad_list in clusters.items():
        # Display name = the raw name that exactly matches the canonical key (if one exists),
        # otherwise the raw name whose canonical form is longest (handles cases where the
        # original name had meaningful tags that don't survive copy-suffix stripping).
        # Critically: never use a " - Copy" variant as the display name.
        exact_matches = [a for a in ad_list if a.get('name', '') == key]
        if exact_matches:
            display = max(exact_matches, key=lambda a: len(a.get('name', '')))['name']
        else:
            display = max(ad_list, key=lambda a: len(canonical_name(a.get('name', ''))))['name']
        spend = sum(safe_float(a.get('spend', 0)) for a in ad_list)
        conversions = sum(safe_float(a.get('conversions', 0)) for a in ad_list)
        cpa = spend / conversions if conversions > 0 else 0.0
        created_times = [a['created_time'] for a in ad_list if a.get('created_time')]
        first_seen = min(created_times) if created_times else ''
        first_month = first_seen[:7] if len(first_seen) >= 7 else ''

        concept_aggregates[display] = {
            'spend': round(spend, 2),
            'conversions': round(conversions, 4),
            'cpa': round(cpa, 2),
            'ad_id_count': len(ad_list),
            'first_seen': first_seen,
            'name_variants': [a['name'] for a in ad_list if a.get('name')],
        }
        concept_first_launch_months[display] = first_month

        for ad in ad_list:
            if ad.get('name'):
                name_to_concept[ad['name']] = display

    return concept_aggregates, concept_first_launch_months, name_to_concept


# ---------------------------------------------------------------------------
# Analysis 1 — Test & Learn
# ---------------------------------------------------------------------------

def run_a1(concept_aggregates_90d: dict, config: dict) -> dict:
    allocation_min = safe_float(config.get('allocation_min_spend', 500))
    all_concepts = list(concept_aggregates_90d.values())

    if not all_concepts:
        return _empty_a1()

    spends = [c['spend'] for c in all_concepts]
    cpas_pos = [c['cpa'] for c in all_concepts if c['cpa'] > 0]

    testing_max = max(allocation_min, percentile(spends, 25))
    scaled_min = percentile(spends, 75)
    median_cpa = statistics.median(cpas_pos) if cpas_pos else 0.0
    red_cpa_multiple = 2.0
    red_cpa_threshold = median_cpa * red_cpa_multiple

    total_spend = sum(spends)
    total_conversions = sum(c['conversions'] for c in all_concepts)

    zone_spend = {'Purple': 0.0, 'Red': 0.0, 'Green': 0.0, 'Unzoned': 0.0}
    zone_conv = {'Purple': 0.0, 'Red': 0.0, 'Green': 0.0, 'Unzoned': 0.0}
    zone_count = {'Purple': 0, 'Red': 0, 'Green': 0, 'Unzoned': 0}
    ads_out = []

    for name, c in concept_aggregates_90d.items():
        s, cpa = c['spend'], c['cpa']
        if s >= testing_max and cpa >= red_cpa_threshold:
            zone = 'Red'
        elif s >= scaled_min and 0 < cpa <= median_cpa:
            zone = 'Purple'
        elif s < testing_max and (cpa == 0 or cpa <= median_cpa):
            zone = 'Green'
        else:
            zone = 'Unzoned'

        zone_spend[zone] += s
        zone_conv[zone] += c['conversions']
        zone_count[zone] += 1
        ads_out.append({
            'name': name,
            'spend': c['spend'],
            'cpa': c['cpa'],
            'conversions': c['conversions'],
            'ad_id_count': c['ad_id_count'],
            'zone': zone,
        })

    def pct(part, whole):
        return round(part / whole * 100, 1) if whole > 0 else 0.0

    zone_conc = {}
    for z in ('purple', 'red', 'green', 'unzoned'):
        Z = z.capitalize()
        zone_conc[z] = {
            'count': zone_count[Z],
            'spend': round(zone_spend[Z], 2),
            'spend_pct': pct(zone_spend[Z], total_spend),
            'conversions': round(zone_conv[Z], 4),
            'conversions_pct': pct(zone_conv[Z], total_conversions) if total_conversions > 0 else 0.0,
        }

    red_spend_pct = pct(zone_spend['Red'], total_spend)
    winner_spend_pct = pct(zone_spend['Purple'], total_spend)
    testing_budget_pct = pct(zone_spend['Green'], total_spend)
    has_purple = zone_count['Purple'] > 0

    # Verdict: CRITICAL first, then WARNING, then HEALTHY
    if red_spend_pct > 25 or not has_purple:
        verdict = 'CRITICAL'
    elif (20 <= winner_spend_pct <= 40) or (15 <= red_spend_pct <= 25):
        verdict = 'WARNING'
    elif winner_spend_pct > 40 and 10 <= testing_budget_pct <= 20 and red_spend_pct < 15:
        verdict = 'HEALTHY'
    else:
        verdict = 'WARNING'

    return {
        'verdict': verdict,
        'data': {
            'ads': sorted(ads_out, key=lambda a: a['spend'], reverse=True),
            'cpa_label': config.get('cpa_label', 'CPA'),
            'account_median_cpa': round(median_cpa, 2),
            'red_spend_pct': red_spend_pct,
            'winner_spend_pct': winner_spend_pct,
            'testing_budget_pct': testing_budget_pct,
            'zone_concentration': zone_conc,
            'box_thresholds': {
                'testing_max_spend': round(testing_max, 2),
                'scaled_min_spend': round(scaled_min, 2),
                'red_cpa_multiple': red_cpa_multiple,
                'median_cpa': round(median_cpa, 2),
            },
        },
    }


def _empty_a1():
    return {
        'verdict': 'INSUFFICIENT_DATA',
        'data': {
            'ads': [], 'cpa_label': '', 'account_median_cpa': 0.0,
            'red_spend_pct': 0.0, 'winner_spend_pct': 0.0, 'testing_budget_pct': 0.0,
            'zone_concentration': {z: {'count': 0, 'spend': 0.0, 'spend_pct': 0.0, 'conversions': 0.0, 'conversions_pct': 0.0}
                                   for z in ('purple', 'red', 'green', 'unzoned')},
            'box_thresholds': {'testing_max_spend': 0.0, 'scaled_min_spend': 0.0, 'red_cpa_multiple': 2.0, 'median_cpa': 0.0},
        },
    }


# ---------------------------------------------------------------------------
# Analysis 2 — Creative Allocation
# ---------------------------------------------------------------------------

def run_a2(concept_aggregates_90d: dict, config: dict) -> dict:
    allocation_min = safe_float(config.get('allocation_min_spend', 500))

    if not concept_aggregates_90d:
        return {'verdict': 'INSUFFICIENT_DATA', 'data': {
            'ads': [], 'top_1pct_spend_pct': 0.0, 'top_10pct_spend_pct': 0.0,
            'sub_threshold_spend_pct': 0.0, 'allocation_min_spend': allocation_min, 'budget_waste_signal': 0.0,
        }}

    total_spend = sum(c['spend'] for c in concept_aggregates_90d.values())
    ranked, sub_threshold, unranked = [], [], []

    for name, c in concept_aggregates_90d.items():
        entry = {'name': name, 'spend': c['spend'], 'cpa': c['cpa'],
                 'conversions': c['conversions'], 'ad_id_count': c['ad_id_count']}
        if c['cpa'] > 0 and c['conversions'] >= 1 and c['spend'] >= allocation_min:
            ranked.append(entry)
        elif c['cpa'] > 0 and c['conversions'] >= 1:
            sub_threshold.append(entry)
        else:
            unranked.append(entry)

    # Rank by CPA ascending (lowest CPA = best)
    ranked.sort(key=lambda x: x['cpa'])

    n = len(ranked)
    top_1_count = math.ceil(0.01 * n) if n > 0 else 0
    top_10_count = math.ceil(0.10 * n) if n > 0 else 0

    ads_out = []
    for i, entry in enumerate(ranked):
        if i < top_1_count:
            tier = 'Top 1%'
        elif i < top_10_count:
            tier = 'Top 10%'
        else:
            tier = 'Top 10%' if top_10_count == 0 else 'Other (ranked)'
        entry['tier'] = tier
        ads_out.append(entry)

    # Fix: re-assign tiers properly
    ads_out = []
    for i, entry in enumerate(ranked):
        if i < top_1_count:
            tier = 'Top 1%'
        elif i < top_10_count:
            tier = 'Top 10%'
        else:
            tier = 'Other (ranked)'
        e = dict(entry)
        e['tier'] = tier
        ads_out.append(e)

    for entry in sub_threshold:
        e = dict(entry)
        e['tier'] = 'Other (untested)'
        ads_out.append(e)

    for entry in unranked:
        e = dict(entry)
        e['tier'] = 'Other (no conversions)'
        ads_out.append(e)

    def spend_sum(lst):
        return sum(x['spend'] for x in lst)

    top_1_spend = spend_sum([a for a in ads_out if a['tier'] == 'Top 1%'])
    top_10_spend = spend_sum([a for a in ads_out if a['tier'] in ('Top 1%', 'Top 10%')])
    sub_spend = spend_sum([a for a in ads_out if a['tier'] == 'Other (untested)'])

    def pct(part):
        return round(part / total_spend * 100, 1) if total_spend > 0 else 0.0

    top_1pct_spend_pct = pct(top_1_spend)
    top_10pct_spend_pct = pct(top_10_spend)
    sub_threshold_spend_pct = pct(sub_spend)

    # budget_waste_signal: spend-weighted avg CPA - unweighted median CPA of ranked pool
    if ranked:
        total_ranked_spend = spend_sum(ranked)
        weighted_avg_cpa = (sum(x['spend'] * x['cpa'] for x in ranked) / total_ranked_spend
                            if total_ranked_spend > 0 else 0.0)
        unweighted_median_cpa = statistics.median([x['cpa'] for x in ranked])
        budget_waste_signal = round(weighted_avg_cpa - unweighted_median_cpa, 2)
        median_cpa_ranked = round(unweighted_median_cpa, 2)
    else:
        budget_waste_signal = 0.0
        median_cpa_ranked = 0.0

    # Verdict
    if top_10pct_spend_pct < 30 or (median_cpa_ranked > 0 and budget_waste_signal > 0.20 * median_cpa_ranked):
        verdict = 'CRITICAL'
    elif (30 <= top_10pct_spend_pct <= 50) or sub_threshold_spend_pct > 25:
        verdict = 'WARNING'
    elif top_10pct_spend_pct > 50 and 5 <= sub_threshold_spend_pct <= 25:
        verdict = 'HEALTHY'
    else:
        verdict = 'WARNING'

    return {
        'verdict': verdict,
        'data': {
            'ads': ads_out,
            'top_1pct_spend_pct': top_1pct_spend_pct,
            'top_10pct_spend_pct': top_10pct_spend_pct,
            'sub_threshold_spend_pct': sub_threshold_spend_pct,
            'allocation_min_spend': allocation_min,
            'budget_waste_signal': budget_waste_signal,
        },
    }


# ---------------------------------------------------------------------------
# Analysis 3 — Reliance on Old Creative
# ---------------------------------------------------------------------------

BUCKETS = ['New (0-30d)', 'Mid (31-60d)', 'Aging (61-90d)', 'Old (90d+)']
TOP_N = 5


def age_bucket(age_days: int) -> str:
    if age_days <= 30:
        return 'New (0-30d)'
    if age_days <= 60:
        return 'Mid (31-60d)'
    if age_days <= 90:
        return 'Aging (61-90d)'
    return 'Old (90d+)'


def run_a3(ad_monthly_spend: list, concept_first_launch_months: dict, name_to_concept: dict) -> dict:
    if not ad_monthly_spend:
        return {
            'verdict': 'INSUFFICIENT_DATA',
            'data': {'monthly_spend_by_age': [], 'monthly_top_ads_by_age': [],
                     'top_ads_per_bucket': TOP_N, 'old_creative_spend_pct': 0.0,
                     'data_warnings': ['No monthly spend data available.']},
        }

    data_warnings = []
    skipped = 0

    # Accumulate spend per (month, bucket)
    month_bucket_spend = defaultdict(lambda: {b: 0.0 for b in BUCKETS})
    month_bucket_ads = defaultdict(lambda: {b: [] for b in BUCKETS})
    total_spend = 0.0

    for row in ad_monthly_spend:
        raw_name = row.get('name', '')
        month = row.get('month', '')
        spend = safe_float(row.get('spend', 0))
        if not raw_name or not month or spend <= 0:
            continue

        display = name_to_concept.get(raw_name)
        if display is None:
            skipped += 1
            continue

        launch_month = concept_first_launch_months.get(display, '')
        if not launch_month:
            skipped += 1
            continue

        try:
            launch_date = datetime.strptime(launch_month, '%Y-%m').date()
            month_date = datetime.strptime(month, '%Y-%m').date()
        except ValueError:
            skipped += 1
            continue

        age_days = max(0, (month_date - launch_date).days)
        bucket = age_bucket(age_days)

        month_bucket_spend[month][bucket] += spend
        month_bucket_ads[month][bucket].append({'name': raw_name[:60] + ('…' if len(raw_name) > 60 else ''),
                                                 'spend': round(spend, 2)})
        total_spend += spend

    if skipped > 0:
        data_warnings.append(f'{skipped} ad-month rows skipped: ad name not found in concept map.')

    # Build output
    months_sorted = sorted(month_bucket_spend.keys())
    monthly_spend_by_age = []
    for m in months_sorted:
        row = {'month': m}
        row.update({b: round(month_bucket_spend[m][b], 2) for b in BUCKETS})
        monthly_spend_by_age.append(row)

    monthly_top_ads_by_age = []
    for m in months_sorted:
        buckets_top = {}
        for b in BUCKETS:
            ads_in_bucket = month_bucket_ads[m][b]
            ads_sorted = sorted(ads_in_bucket, key=lambda x: x['spend'], reverse=True)[:TOP_N]
            buckets_top[b] = [{'name': a['name'], 'spend': a['spend'], 'rank': i + 1}
                               for i, a in enumerate(ads_sorted)]
        monthly_top_ads_by_age.append({'month': m, 'buckets': buckets_top})

    old_spend = sum(month_bucket_spend[m]['Aging (61-90d)'] + month_bucket_spend[m]['Old (90d+)']
                    for m in months_sorted)
    old_creative_spend_pct = round(old_spend / total_spend * 100, 1) if total_spend > 0 else 0.0

    if old_creative_spend_pct < 40:
        verdict = 'HEALTHY'
    elif old_creative_spend_pct <= 65:
        verdict = 'WARNING'
    else:
        verdict = 'CRITICAL'

    return {
        'verdict': verdict,
        'data': {
            'monthly_spend_by_age': monthly_spend_by_age,
            'monthly_top_ads_by_age': monthly_top_ads_by_age,
            'top_ads_per_bucket': TOP_N,
            'old_creative_spend_pct': old_creative_spend_pct,
            'data_warnings': data_warnings,
        },
    }


# ---------------------------------------------------------------------------
# Analysis 4 — Creative Churn
# ---------------------------------------------------------------------------

def run_a4(ad_monthly_spend: list, concept_first_launch_months: dict, name_to_concept: dict,
           concept_aggregates: dict) -> dict:
    data_warnings = []
    using_fallback = False

    if not ad_monthly_spend:
        using_fallback = True
        data_warnings.append(
            'Cohort spend approximated using even distribution — actual spend is typically '
            'front-loaded. Run meta_get_ad_monthly_spend for accurate curves.'
        )
        ad_monthly_spend = _build_fallback_monthly_spend(concept_aggregates, concept_first_launch_months)

    # Build cohort -> set of concept display names
    cohort_concepts = defaultdict(set)
    for display, launch_month in concept_first_launch_months.items():
        if launch_month:
            cohort_concepts[launch_month].add(display)

    # Build concept -> months with spend (for cohort spend aggregation)
    concept_month_spend = defaultdict(lambda: defaultdict(float))
    for row in ad_monthly_spend:
        raw = row.get('name', '')
        month = row.get('month', '')
        spend = safe_float(row.get('spend', 0))
        if not raw or not month:
            continue
        display = name_to_concept.get(raw, raw)
        concept_month_spend[display][month] += spend

    all_months = sorted({row.get('month', '') for row in ad_monthly_spend if row.get('month')})
    if not all_months:
        return {'verdict': 'INSUFFICIENT_DATA', 'data': {
            'cohort_spend_by_month': [], 'monthly_launches': [],
            'avg_cohort_half_life_weeks': 0.0, 'data_warnings': data_warnings,
        }}

    # Build cohort_spend_by_month
    active_cohorts = sorted(cohort_concepts.keys())
    cohort_spend_by_month = []

    for m in all_months:
        row = {'month': m}
        for cohort in active_cohorts:
            if cohort > m:
                continue
            label = f"{month_label(cohort)} launches"
            cohort_spend = sum(concept_month_spend[c][m] for c in cohort_concepts[cohort])
            if cohort_spend > 0 or any(concept_month_spend[c][m] > 0 for c in cohort_concepts[cohort]):
                row[label] = round(cohort_spend, 2)
        cohort_spend_by_month.append(row)

    # Monthly launches (concept counts per month)
    launch_counts = defaultdict(int)
    for display, launch_month in concept_first_launch_months.items():
        if launch_month:
            launch_counts[launch_month] += 1

    monthly_launches = [{'month': m, 'count': launch_counts.get(m, 0)} for m in all_months]

    # Cohort half-lives
    half_lives = []
    for cohort in active_cohorts:
        cohort_label = f"{month_label(cohort)} launches"
        monthly = []
        for m in all_months:
            if m < cohort:
                continue
            row_dict = next((r for r in cohort_spend_by_month if r['month'] == m), {})
            monthly.append((m, row_dict.get(cohort_label, 0.0)))

        if not monthly:
            continue

        peak_spend = max(s for _, s in monthly)
        if peak_spend == 0:
            continue

        peak_idx = next(i for i, (_, s) in enumerate(monthly) if s == peak_spend)
        half_life = len(all_months)
        still_active = True

        for i in range(peak_idx + 1, len(monthly)):
            if monthly[i][1] < peak_spend * 0.5:
                half_life = max(1, i - peak_idx)
                still_active = False
                break

        half_lives.append(half_life)

    avg_half_life_weeks = round(statistics.mean(half_lives) * 4.33, 1) if half_lives else 0.0

    # Launch trend (last 3 months)
    last_3 = [r['count'] for r in monthly_launches[-3:]] if len(monthly_launches) >= 3 else []
    if len(last_3) == 3 and last_3[0] < last_3[1] < last_3[2]:
        launch_trend = 'growing'
    elif len(last_3) == 3 and last_3[0] > last_3[1] > last_3[2]:
        launch_trend = 'declining'
    else:
        launch_trend = 'flat'

    # Verdict
    recent_3_counts = last_3
    if launch_trend == 'declining' and avg_half_life_weeks < 4:
        verdict = 'CRITICAL'
    elif launch_trend == 'declining' or avg_half_life_weeks < 4:
        verdict = 'WARNING'
    else:
        verdict = 'HEALTHY'

    return {
        'verdict': verdict,
        'data': {
            'cohort_spend_by_month': cohort_spend_by_month,
            'monthly_launches': monthly_launches,
            'avg_cohort_half_life_weeks': avg_half_life_weeks,
            'launch_trend': launch_trend,
            'data_warnings': data_warnings,
        },
    }


def _build_fallback_monthly_spend(concept_aggregates: dict, concept_first_launch_months: dict) -> list:
    today = date.today()
    rows = []
    for display, data in concept_aggregates.items():
        launch_month = concept_first_launch_months.get(display, '')
        if not launch_month:
            continue
        try:
            start = datetime.strptime(launch_month, '%Y-%m').date()
        except ValueError:
            continue
        months = []
        cur = start.replace(day=1)
        while cur <= today.replace(day=1):
            months.append(cur.strftime('%Y-%m'))
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)
        if not months:
            continue
        per_month = data['spend'] / len(months)
        for m in months:
            rows.append({'name': display, 'month': m, 'spend': per_month})
    return rows


# ---------------------------------------------------------------------------
# Analysis 5 — Production & Slugging Rate
# ---------------------------------------------------------------------------

def determine_spend_tier(account_overview: dict) -> str:
    spend_90d = safe_float(account_overview.get('spend', 0))
    monthly = spend_90d / 3
    if monthly < 10_000:
        return 'Micro'
    if monthly < 50_000:
        return 'Small'
    if monthly < 200_000:
        return 'Medium'
    if monthly < 1_000_000:
        return 'Large'
    return 'Enterprise'


def run_a5(concept_aggregates: dict, concept_first_launch_months: dict,
           account_overview: dict, motion_benchmarks: dict, config: dict) -> dict:
    target_cpa = config.get('target_cpa')  # None or float
    winner_top_percentile = safe_float(config.get('winner_top_percentile', 0.20))

    spend_tier = determine_spend_tier(account_overview)
    tier_data = motion_benchmarks.get('avg_hit_rate_by_tier', {}).get(spend_tier, {})
    motion_target = safe_float(tier_data.get('hit_rate_pct', 8.13))

    # Group concepts by launch month
    by_month = defaultdict(list)
    for display, data in concept_aggregates.items():
        launch_month = concept_first_launch_months.get(display, '')
        if launch_month:
            by_month[launch_month].append({'name': display, **data})

    windows = []
    today_month = date.today().strftime('%Y-%m')

    for month in sorted(by_month.keys()):
        concepts = by_month[month]
        converted = [c for c in concepts if c['conversions'] >= 1]
        zero_conv = [c for c in concepts if c['conversions'] == 0]
        scoreable = len(concepts) >= 3
        hit_rate = None
        winners_list = []
        winner_cpa_threshold = None

        if scoreable:
            if not converted:
                hit_rate = 0.0
            elif target_cpa is not None:
                min_conv = 3
                winners_list = [c for c in converted if c['cpa'] <= target_cpa and c['conversions'] >= min_conv]
                winner_cpa_threshold = target_cpa
                hit_rate = round(len(winners_list) / len(concepts) * 100, 2)
            else:
                sorted_conv = sorted(converted, key=lambda c: c['cpa'])
                idx = int(winner_top_percentile * len(sorted_conv))
                winner_cpa_threshold = sorted_conv[idx]['cpa']
                winners_list = [c for c in sorted_conv if c['cpa'] <= winner_cpa_threshold]
                hit_rate = round(len(winners_list) / len(concepts) * 100, 2)

        ad_id_count = sum(c['ad_id_count'] for c in concepts)
        duplicate_pct = round((ad_id_count - len(concepts)) / ad_id_count * 100, 1) if ad_id_count > 0 else 0.0

        windows.append({
            'month': month,
            'label': month_label(month),
            'is_partial_month': month == today_month,
            'truncation_warning': False,
            'concepts_total': len(concepts),
            'converted_count': len(converted),
            'zero_conv_count': len(zero_conv),
            'winners': len(winners_list),
            'hit_rate': hit_rate,
            'winner_cpa_threshold': round(winner_cpa_threshold, 2) if winner_cpa_threshold else None,
            'ad_id_count': ad_id_count,
            'duplicate_pct': duplicate_pct,
            'scoreable': scoreable,
        })

    # Verdict
    scoreable_windows = [w for w in windows if w['scoreable'] and w['hit_rate'] is not None]
    if len(scoreable_windows) < 2:
        verdict = 'INSUFFICIENT_DATA'
        recent_avg = None
        prior_avg = None
    else:
        recent_two = scoreable_windows[-2:]
        prior_two = scoreable_windows[-4:-2] if len(scoreable_windows) >= 4 else []
        recent_avg = round(statistics.mean(w['hit_rate'] for w in recent_two), 2)
        prior_avg = round(statistics.mean(w['hit_rate'] for w in prior_two), 2) if prior_two else None
        recent_zero_winners = all(w['winners'] == 0 for w in recent_two)

        if recent_avg < motion_target * 0.5 or recent_zero_winners:
            verdict = 'CRITICAL'
        elif recent_avg < motion_target * 0.8 or (prior_avg is not None and recent_avg < prior_avg * 0.8):
            verdict = 'WARNING'
        else:
            verdict = 'HEALTHY'

    motion_median_monthly = round(safe_float(
        motion_benchmarks.get('all_verticals_fallback', {}).get(spend_tier, 9.0)) * 4.33, 1)

    return {
        'verdict': verdict,
        'data': {
            'windows': windows,
            'winner_top_percentile': winner_top_percentile,
            'recent_avg_hit_rate': recent_avg,
            'prior_avg_hit_rate': prior_avg,
            'motion_benchmark': motion_target,
            'spend_tier': spend_tier,
            'verdict_reference': 'motion',
            'target_cpa_mode': target_cpa is not None,
        },
    }


# ---------------------------------------------------------------------------
# Analysis 6 — Rolling Reach
# ---------------------------------------------------------------------------

def run_a6(monthly_reach_raw: list, ad_monthly_spend: list) -> dict:
    data_warnings = []

    if not monthly_reach_raw:
        return {
            'verdict': 'INSUFFICIENT_DATA',
            'data': {
                'monthly_reach': [], 'signal_a_fired': False, 'signal_b_fired': None,
                'prior_avg_cost_pnn': 0.0, 'recent_avg_cost_pnn': 0.0,
                'trailing_ratio': 0.0, 'recent_ratio': 0.0,
                'using_fallback': True,
                'calculation_note': 'No reach data available.',
                'data_warnings': ['No monthly reach data returned from meta_get_monthly_reach.'],
            },
        }

    # Aggregate monthly spend from ad_monthly_spend
    month_spend_total = defaultdict(float)
    for row in ad_monthly_spend:
        m = row.get('month', '')
        s = safe_float(row.get('spend', 0))
        if m:
            month_spend_total[m] += s

    # Also accept spend from monthly_reach rows if present
    reach_by_month = {}
    for row in monthly_reach_raw:
        m = row.get('month', '')
        if not m:
            continue
        reach = safe_float(row.get('reach', 0))
        row_spend = safe_float(row.get('spend', 0))
        spend = row_spend if row_spend > 0 else month_spend_total.get(m, 0.0)
        reach_by_month[m] = {'reach': reach, 'spend': spend}

    sorted_months = sorted(reach_by_month.keys())
    if not sorted_months:
        return {
            'verdict': 'INSUFFICIENT_DATA',
            'data': {'monthly_reach': [], 'signal_a_fired': False, 'signal_b_fired': None,
                     'prior_avg_cost_pnn': 0.0, 'recent_avg_cost_pnn': 0.0,
                     'trailing_ratio': 0.0, 'recent_ratio': 0.0, 'using_fallback': True,
                     'calculation_note': 'No monthly reach data after processing.',
                     'data_warnings': data_warnings},
        }

    today = date.today()
    today_month = today.strftime('%Y-%m')

    processed = []
    using_fallback = False

    for m in sorted_months:
        reach = reach_by_month[m]['reach']
        spend = reach_by_month[m]['spend']

        # Partial month
        try:
            m_date = datetime.strptime(m, '%Y-%m').date()
            dim = days_in_month(m_date.year, m_date.month)
            elapsed = (today - m_date).days + 1 if m == today_month else dim
            is_partial = (m == today_month and elapsed < dim)
        except ValueError:
            elapsed = 30
            is_partial = False
            dim = 30

        reach_per_day = round(reach / elapsed, 1) if elapsed > 0 else 0.0

        # net_new_reach: try M-12
        m12 = f"{int(m[:4]) - 1}{m[4:]}"
        if m12 in reach_by_month:
            net_new = max(reach - reach_by_month[m12]['reach'] * 0.5, 0)
            used_fallback = False
        else:
            net_new = reach * 0.7
            used_fallback = True
            using_fallback = True

        net_new_ratio = round(net_new / reach, 3) if reach > 0 else 0.0
        cost_per_net_new = round(spend / net_new, 4) if net_new > 0 and spend > 0 else 0.0

        processed.append({
            'month': m,
            'reach': int(reach),
            'net_new_reach': round(net_new),
            'net_new_ratio': net_new_ratio,
            'spend': round(spend, 2),
            'cost_per_net_new': cost_per_net_new,
            'reach_per_day': reach_per_day,
            'is_partial': is_partial,
            'used_fallback': used_fallback,
        })

    # Signal A: 20%+ rise in cost_per_net_new over last 6 active months
    active = [p for p in processed if not p['is_partial'] and p['cost_per_net_new'] > 0]
    signal_a_fired = False
    prior_avg_cost_pnn = 0.0
    recent_avg_cost_pnn = 0.0

    if len(active) >= 6:
        prior_3 = active[-6:-3]
        recent_3 = active[-3:]
        prior_avg_cost_pnn = round(statistics.mean(p['cost_per_net_new'] for p in prior_3), 4)
        recent_avg_cost_pnn = round(statistics.mean(p['cost_per_net_new'] for p in recent_3), 4)
        if recent_avg_cost_pnn >= 0.50 and recent_avg_cost_pnn >= prior_avg_cost_pnn * 1.20:
            signal_a_fired = True

    # Signal B: 5pp drop in net_new_ratio over trailing 6m vs recent 3m
    signal_b_fired = None
    trailing_ratio = 0.0
    recent_ratio = 0.0

    if using_fallback and all(p['used_fallback'] for p in processed):
        signal_b_fired = None  # suppressed
        data_warnings.append(
            'Reach saturation signal suppressed — no M−12 baseline available yet. '
            'All net-new ratios are estimated at 0.70×.'
        )
    elif len(processed) >= 6:
        trailing_6 = processed[-6:]
        recent_3p = processed[-3:]
        trailing_ratio = round(statistics.mean(p['net_new_ratio'] for p in trailing_6), 3)
        recent_ratio = round(statistics.mean(p['net_new_ratio'] for p in recent_3p), 3)
        signal_b_fired = recent_ratio <= trailing_ratio - 0.05

    # Verdict
    all_fallback = all(p['used_fallback'] for p in processed)
    if all_fallback:
        verdict = 'INSUFFICIENT_DATA'
    elif signal_a_fired and signal_b_fired:
        verdict = 'CRITICAL'
    elif signal_a_fired or signal_b_fired:
        verdict = 'WARNING'
    else:
        verdict = 'HEALTHY'

    fallback_count = sum(1 for p in processed if p['used_fallback'])
    non_fallback_count = len(processed) - fallback_count
    if all_fallback:
        calc_note = f'Net-new reach estimated using 0.7× fallback for all {len(processed)} months (no M−12 baseline available).'
    elif fallback_count > 0:
        calc_note = (f'Net-new reach estimated using M−12 overlap formula for {non_fallback_count} months; '
                     f'0.7× fallback used for {fallback_count} months where baseline was unavailable.')
    else:
        calc_note = f'Net-new reach computed using M−12 overlap formula for all {len(processed)} months.'

    return {
        'verdict': verdict,
        'data': {
            'monthly_reach': processed,
            'signal_a_fired': signal_a_fired,
            'signal_b_fired': signal_b_fired,
            'prior_avg_cost_pnn': prior_avg_cost_pnn,
            'recent_avg_cost_pnn': recent_avg_cost_pnn,
            'trailing_ratio': trailing_ratio,
            'recent_ratio': recent_ratio,
            'using_fallback': using_fallback,
            'calculation_note': calc_note,
            'data_warnings': data_warnings,
        },
    }


# ---------------------------------------------------------------------------
# Analysis 7 — Creative Volume vs. Spend
# ---------------------------------------------------------------------------

def run_a7(concept_first_launch_months: dict, account_overview: dict,
           motion_benchmarks: dict, config: dict) -> dict:
    vertical = config.get('industry_vertical', 'Other')
    spend_tier = determine_spend_tier(account_overview)
    account_monthly_run_rate = round(safe_float(account_overview.get('spend', 0)) / 3, 2)

    # Launch counts per month
    launch_counts = defaultdict(int)
    for display, launch_month in concept_first_launch_months.items():
        if launch_month:
            launch_counts[launch_month] += 1

    all_months = sorted(launch_counts.keys())
    monthly_launches_list = [{'month': m, 'count': launch_counts[m]} for m in all_months]

    # Last 3 months
    last_3_months = all_months[-3:] if len(all_months) >= 3 else all_months
    last_3_counts = [launch_counts[m] for m in last_3_months]
    avg_monthly_launches = round(statistics.mean(last_3_counts), 1) if last_3_counts else 0.0

    today_month = date.today().strftime('%Y-%m')
    window_labels = []
    for m in last_3_months:
        label = month_label(m)
        if m == today_month:
            label += ' (MTD)'
        window_labels.append(label)

    # Motion benchmark lookup
    median_vol_table = motion_benchmarks.get('median_weekly_testing_volume', {})
    top_q_table = motion_benchmarks.get('top_quartile_weekly_volume', {})
    fallback_table = motion_benchmarks.get('all_verticals_fallback', {})

    def get_median_weekly(vert, tier):
        val = median_vol_table.get(vert, {}).get(tier)
        if val is None:
            val = fallback_table.get(tier, 9.0)
            return val, True
        return val, False

    median_weekly, fallback_used = get_median_weekly(vertical, spend_tier)
    top_quartile_weekly = safe_float(top_q_table.get(spend_tier, 15.9))
    motion_median_monthly = round(median_weekly * 4.33, 1)
    motion_top_quartile_monthly = round(top_quartile_weekly * 4.33, 1)

    # Tier benchmark table
    tiers = ['Micro', 'Small', 'Medium', 'Large', 'Enterprise']
    tier_spend_ranges = motion_benchmarks.get('spend_tiers', {})
    tier_benchmark_table = []
    for t in tiers:
        mw, fb = get_median_weekly(vertical, t)
        tier_benchmark_table.append({
            'tier': t,
            'spend_range': tier_spend_ranges.get(t, ''),
            'median_monthly': round(mw * 4.33, 1),
            'is_current': t == spend_tier,
            'fallback_used': fb,
        })

    # Verdict
    if avg_monthly_launches >= motion_median_monthly:
        verdict = 'HEALTHY'
    elif avg_monthly_launches >= motion_median_monthly * 0.5:
        verdict = 'WARNING'
    else:
        verdict = 'CRITICAL'

    top_quartile_is_cross_vertical = vertical not in median_vol_table

    return {
        'verdict': verdict,
        'data': {
            'avg_monthly_launches': avg_monthly_launches,
            'motion_median_monthly': motion_median_monthly,
            'motion_top_quartile_monthly': motion_top_quartile_monthly,
            'vertical': vertical,
            'tier': spend_tier,
            'tier_spend_range': tier_spend_ranges.get(spend_tier, ''),
            'account_monthly_run_rate': account_monthly_run_rate,
            'fallback_used': fallback_used,
            'median_cohort_label': f'{vertical} × {spend_tier}-tier accounts',
            'top_quartile_cohort_label': f'All verticals × {spend_tier}-tier accounts',
            'top_quartile_is_cross_vertical': top_quartile_is_cross_vertical,
            'launch_window': {
                'label': 'Last 3 calendar months',
                'months': window_labels,
                'monthly_counts': last_3_counts,
            },
            'tier_benchmark_table': tier_benchmark_table,
            'benchmark_source': 'Motion 2026 Creative Benchmarks (550K+ ads, 6,000+ advertisers, Sep 2025–Jan 2026)',
            'data_warnings': [],
        },
    }


# ---------------------------------------------------------------------------
# Data Quality Pass — LCP clustering
# ---------------------------------------------------------------------------

def normalize_for_lcp(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def lcp_length(a: str, b: str) -> int:
    i = 0
    while i < len(a) and i < len(b) and a[i] == b[i]:
        i += 1
    return i


def run_data_quality(concept_aggregates: dict, allocation_min_spend: float) -> dict:
    total_spend = sum(c['spend'] for c in concept_aggregates.values())

    # Filter candidates to concepts with meaningful spend
    candidates = {n: d for n, d in concept_aggregates.items() if d['spend'] >= allocation_min_spend}

    # Guard: if still too large, filter to above median spend of candidates
    if len(candidates) > 150:
        cand_spends = [d['spend'] for d in candidates.values()]
        spend_floor = percentile(cand_spends, 50)
        candidates = {n: d for n, d in candidates.items() if d['spend'] >= spend_floor}

    names = list(candidates.keys())
    normed = [normalize_for_lcp(n) for n in names]

    # Union-find
    parent = list(range(len(names)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = normed[i], normed[j]
            if not a or not b:
                continue
            ll = lcp_length(a, b)
            min_len = min(len(a), len(b))
            if min_len > 0 and ll >= 30 and ll / min_len >= 0.60:
                union(i, j)

    # Group by cluster root
    cluster_map = defaultdict(list)
    for i in range(len(names)):
        cluster_map[find(i)].append(i)

    clusters_out = []
    for root, idxs in cluster_map.items():
        if len(idxs) < 2:
            continue
        members = [names[i] for i in idxs]
        cluster_spend = sum(candidates[m]['spend'] for m in members)

        # Evidence
        a_n, b_n = normed[idxs[0]], normed[idxs[1]]
        ll = lcp_length(a_n, b_n)
        is_prefix = a_n.startswith(b_n) or b_n.startswith(a_n)
        evidence = ('one name is a prefix of the other' if is_prefix
                    else f'names share {ll} chars of normalized prefix')

        member_data = sorted([
            {'name': m,
             'spend': candidates[m]['spend'],
             'ad_id_count': candidates[m]['ad_id_count'],
             'conversions': candidates[m]['conversions'],
             'cpa': candidates[m]['cpa']}
            for m in members
        ], key=lambda x: x['spend'], reverse=True)

        clusters_out.append({
            'cluster_spend': round(cluster_spend, 2),
            'members': member_data,
            'evidence': evidence,
        })

    clusters_out.sort(key=lambda c: c['cluster_spend'], reverse=True)
    total_cluster_spend = sum(c['cluster_spend'] for c in clusters_out)

    return {
        'likely_related_concept_clusters': clusters_out,
        'total_clusters': len(clusters_out),
        'total_spend_in_clusters': round(total_cluster_spend, 2),
        'spend_pct_of_total': round(total_cluster_spend / total_spend * 100, 1) if total_spend > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Meta Diagnostics Compute Engine')
    parser.add_argument('--skill-dir', default=os.path.dirname(os.path.abspath(__file__)),
                        help='Directory containing this script and motion-benchmarks.json')
    parser.add_argument('--raw-dir', default=os.path.expanduser('~/meta-diagnostics/raw'),
                        help='Directory containing raw JSON data files')
    parser.add_argument('--config', default=os.path.expanduser('~/.meta-diagnostics-config.json'),
                        help='Path to config file')
    parser.add_argument('--output', default=os.path.expanduser('~/meta-diagnostics/computed.json'),
                        help='Output path for computed.json')
    args = parser.parse_args()

    raw_dir = os.path.expanduser(args.raw_dir)
    skill_dir = os.path.expanduser(args.skill_dir)
    output_path = os.path.expanduser(args.output)

    # Load config
    config = load_json(args.config, {})
    if not config:
        print('ERROR: Config not found. Run /meta-diagnostics to set up config first.', file=sys.stderr)
        sys.exit(1)

    conversion_event = config.get('conversion_event', 'Conversion')
    conversion_label = config.get('conversion_label', '')
    config['cpa_label'] = f'{conversion_event} Cost ({conversion_label})' if conversion_label else conversion_event

    # Load motion benchmarks
    benchmarks_path = os.path.join(skill_dir, 'motion-benchmarks.json')
    motion_benchmarks = load_json(benchmarks_path, {})
    if not motion_benchmarks:
        print(f'ERROR: motion-benchmarks.json not found at {benchmarks_path}. '
              'Run install.sh to reinstall the skill.', file=sys.stderr)
        sys.exit(1)

    # Load raw data
    ads_90d = load_json(os.path.join(raw_dir, 'ads_90d.json'), [])
    ads_6m = load_json(os.path.join(raw_dir, 'ads_6m.json'), [])
    monthly_reach_raw = load_json(os.path.join(raw_dir, 'monthly_reach.json'), [])
    account_overview = load_json(os.path.join(raw_dir, 'account_overview.json'), {})
    ad_monthly_spend = load_json(os.path.join(raw_dir, 'ad_monthly_spend.json'), [])

    if not isinstance(ads_90d, list):
        ads_90d = []
    if not isinstance(ads_6m, list):
        ads_6m = []
    if not isinstance(ad_monthly_spend, list):
        ad_monthly_spend = []
    if not isinstance(monthly_reach_raw, list):
        monthly_reach_raw = []

    # Build concept maps
    concept_aggregates, concept_first_launch_months, name_to_concept = build_concept_maps(ads_6m)
    concept_aggregates_90d, _, name_to_concept_90d = build_concept_maps(ads_90d)

    # Merge reverse lookup (90d names should also resolve)
    combined_name_to_concept = {**name_to_concept, **name_to_concept_90d}

    # Account overview total spend
    total_90d_spend = sum(c['spend'] for c in concept_aggregates_90d.values())
    if total_90d_spend == 0:
        total_90d_spend = safe_float(account_overview.get('spend', 0))

    allocation_min = safe_float(config.get('allocation_min_spend', 500))

    # Run all 7 analyses
    a1 = run_a1(concept_aggregates_90d, config)
    a2 = run_a2(concept_aggregates_90d, config)
    a3 = run_a3(ad_monthly_spend, concept_first_launch_months, combined_name_to_concept)
    a4 = run_a4(ad_monthly_spend, concept_first_launch_months, combined_name_to_concept, concept_aggregates)
    a5 = run_a5(concept_aggregates, concept_first_launch_months, account_overview, motion_benchmarks, config)
    a6 = run_a6(monthly_reach_raw, ad_monthly_spend)
    a7 = run_a7(concept_first_launch_months, account_overview, motion_benchmarks, config)

    # Data quality pass
    data_quality = run_data_quality(concept_aggregates, allocation_min)

    # Assemble output
    output = {
        'run_date': date.today().isoformat(),
        'config': {k: v for k, v in config.items() if k != 'deps_checked'},
        'overview': {
            'spend': str(round(total_90d_spend, 2)),
            'active_ads': len(ads_90d),
            'date_range': 'last_90_days',
        },
        'data_quality': data_quality,
        'analyses': [
            {
                'id': 'test_and_learn',
                'title': 'Test & Learn Spend Optimization',
                'verdict': a1['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a1['data'],
            },
            {
                'id': 'creative_allocation',
                'title': 'Creative Allocation',
                'verdict': a2['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a2['data'],
            },
            {
                'id': 'old_creative',
                'title': 'Reliance on Old Creative',
                'verdict': a3['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a3['data'],
            },
            {
                'id': 'creative_churn',
                'title': 'Creative Churn',
                'verdict': a4['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a4['data'],
            },
            {
                'id': 'slugging_rate',
                'title': 'Production & Slugging Rate',
                'verdict': a5['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a5['data'],
            },
            {
                'id': 'rolling_reach',
                'title': 'Rolling Reach',
                'verdict': a6['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a6['data'],
            },
            {
                'id': 'volume_vs_spend',
                'title': 'Creative Volume vs. Spend (Motion 2026 Benchmarks)',
                'verdict': a7['verdict'],
                'meaning': '',
                'action': '',
                'metrics': {},
                'data': a7['data'],
            },
        ],
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f'computed.json written to {output_path}')


if __name__ == '__main__':
    main()

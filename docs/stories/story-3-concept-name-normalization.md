# Story 3: Concept Name Normalization + Data Quality Card — Brownfield Fix

**Size:** Large | **Source:** Round 3 Bug Report, Issue 3 | **Commit baseline:** `a2b391e`

> **Escalation note:** This story has two coordinated tiers (Tier 1 mechanical dedup + Tier 2 surface detection) and introduces a new top-level `data_quality` block in `results.json` and a new dashboard card. If development scope grows during implementation, split into two stories: `story-3a` (Tier 1 only) and `story-3b` (Tier 2 + dashboard card).

---

## User Story

As a media manager reviewing creative performance,
I want concepts that are the same creative — just duplicated across ad sets by Meta's UI — to be counted as one,
And I want to see a flag when concepts might be related but weren't auto-merged,
So that spend and conversion data reflects real creative decisions, not infrastructure artifacts.

---

## Story Context

**Existing System Integration:**
- Integrates with: `SKILL.md` § Shared Step (lines 200–225) — the concept map builder; Phase 5 `results.json` output spec; `templates/dashboard_template.py` → `main()` for dashboard card placement
- Technology: Claude LLM (SKILL.md is the analysis runner — no `_run_analyses.py`); Streamlit for new dashboard card
- Follows pattern: existing `concept_aggregates` / `concept_first_launch_months` map-building pattern in Shared Step; existing `data_warnings` card pattern in `chart_creative_churn`
- Touch points: SKILL.md Shared Step (name normalization) + SKILL.md new § Data Quality section + `dashboard_template.py` new card

**Background:**
Round 2 dedup correctly merges `ad_id` rows that share an exact name string. But Meta's UI appends `" - Copy"` (case-insensitive, may include a number: `" - Copy 2"`) when a media manager duplicates an ad — a routine workflow for scaling a winner into a new ad set. These mechanical duplicates have different names and are currently treated as separate concepts. On this account: 2 clusters ($24,872 / 11.5% of 90d spend) are split entirely by this suffix. Two additional clusters ($15,941 / 7.4%) are split by operational naming choices (bare hook vs full convention, V1 vs V3 iteration). The first type is auto-mergeable with zero false-positive risk; the second type requires the analyst's judgment and should be flagged but not silently merged.

**Critical architecture note:** There is no `_run_analyses.py`. Name normalization is implemented as a SKILL.md instruction change — the LLM normalizes names before building the concept maps on every run.

---

## Acceptance Criteria

### Tier 1 — Mechanical dedup (canonical_name normalization)

1. Before keying either concept map (`concept_aggregates` / `concept_first_launch_months`), the LLM strips trailing Meta copy suffixes from the ad name:
   - Pattern: `" - Copy"`, `" - Copy 2"`, `" - Copy N"` (case-insensitive, any integer N), applied iteratively until stable (handles `" - Copy - Copy"`)
   - Leading/trailing whitespace trimmed after stripping
2. The **display name** used in charts is the **longest raw name string** within each canonical-key cluster (preserves full naming-convention tags)
3. Each concept entry carries `name_variants: list[str]` listing every raw name string that collapsed into it (available in hover and downstream analysis)
4. All analyses (A1–A7) automatically benefit — no per-analysis changes needed
5. On `act_748122004521787`: `BrandonPodcast-V4-Video-...` cluster ($21,783) and `UGCVideo_Invisible_Millionaire_V1` cluster ($3,089) each collapse to one concept row with combined spend and conversions

### Tier 2 — Likely-related concept detection (surface-only, no auto-merge)

6. After building `concept_aggregates`, the LLM runs a prefix-similarity pass:
   - Two concepts are "likely related" if their normalized (lowercase, alphanumeric-only) longest-common-prefix is ≥ 30 chars AND covers ≥ 60% of the shorter name's normalized length
   - Concepts already merged by Tier 1 (exact canonical key) are excluded
7. Results emitted as a top-level `data_quality` block in `results.json` (sibling to `analyses`):
   ```json
   {
     "data_quality": {
       "likely_related_concept_clusters": [
         {
           "cluster_spend": 12852.20,
           "members": [
             {"name": "IfSomeone...-V6-Video-...", "spend": 9858.84, "ad_id_count": 6,
              "conversions": 22, "cpa": 448.13},
             {"name": "IfSomeone...", "spend": 2993.36, "ad_id_count": 1,
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
8. Dashboard renders a "Data Quality — Likely-related concepts" card above the Priority Action Stack when `data_quality.likely_related_concept_clusters` is non-empty
9. Each cluster card shows: combined spend, member rows (name + spend + CPA side-by-side), one-line CTA: *"These N concepts share most of their name. If they're the same creative, rename them in Meta to match. If intentionally distinct (e.g. different version), no action needed."*
10. On `act_748122004521787`: `IfSomeoneJust` cluster (~$12,852) appears in the data_quality card; `5ADayOnCoffee` V1/V3 cluster (~$20,911) is either flagged or correctly excluded depending on prefix match (V1 vs V3 share a long prefix — expected to be flagged, user decides)

**Integration Requirements:**
11. All 7 analyses use the normalized display name as the concept key — no per-analysis changes
12. `name_variants` field is additive — older `results.json` files without it degrade gracefully in the dashboard
13. If `data_quality` block is absent from `results.json`, the dashboard card is silently omitted (no crash)

**Quality Requirements:**
14. Verified: A1 scatter shows 64→~62 concepts (2 Copy clusters merged); total spend unchanged
15. Verified: Merged clusters show combined spend and conversions, not the larger row's values alone
16. Dashboard data_quality card renders without error when clusters list is empty

---

## Technical Notes

**SKILL.md — Shared Step addition (before Map 1):**

> **Concept key normalization:** Before generating the dedup key for either map, normalize the ad name by stripping trailing Meta auto-duplicate suffixes (`" - Copy"`, `" - Copy 2"`, `" - Copy N"` — case-insensitive; any non-negative integer N; strip iteratively until the name is stable). Trim whitespace. The dictionary key for both maps is the *canonical key* (normalized name); the *display name* is the longest raw name string within each canonical-key cluster, so downstream chart labels preserve the full naming-convention version. Each concept entry must carry `name_variants: list[str]` of every raw name string that collapsed into it.

**SKILL.md — New § Data Quality (after Phase 4 / before Phase 5):**

> **Likely-related concepts pass:** After all 7 analyses complete and `concept_aggregates` is finalized, run a prefix-similarity scan. For each pair of distinct concepts (not already merged by canonical normalization): normalize both names to lowercase alphanumeric, compute their longest common prefix (LCP). Flag as "likely related" if `len(LCP) ≥ 30 AND len(LCP) / min(len(name_a_normalized), len(name_b_normalized)) ≥ 0.60`. Group into clusters (union-find or simple greedy pass). Emit results in the `data_quality` top-level block as specified in the Phase 5 output structure. If no clusters found, emit `data_quality` with empty `likely_related_concept_clusters` list and zeroed totals.

**SKILL.md — Phase 5 output structure addition:**

Add `data_quality` as a required top-level key in the `results.json` spec (alongside `overview` and `analyses`).

**`dashboard_template.py` — new `render_data_quality_card()` function + wiring:**

```python
def render_data_quality_card(data_quality: dict):
    clusters = data_quality.get("likely_related_concept_clusters", [])
    if not clusters:
        return
    total_spend = data_quality.get("total_spend_in_clusters", 0)
    pct = data_quality.get("spend_pct_of_total", 0)
    st.markdown(f"### Data Quality — Likely-related concepts")
    st.caption(
        f"{len(clusters)} cluster(s) detected · "
        f"${total_spend:,.0f} combined ({pct:.1f}% of total spend) — "
        "system flagged but did not auto-merge. Review and rename in Meta if intended as the same creative."
    )
    for cluster in clusters:
        members = cluster.get("members", [])
        combined = cluster.get("cluster_spend", 0)
        st.markdown(f"**Combined spend: ${combined:,.0f}** · {cluster.get('evidence', '')}")
        rows = [{"Concept": m["name"], "Spend": f"${m['spend']:,.0f}",
                 "CPA": f"${m['cpa']:,.0f}", "Copies": m["ad_id_count"]} for m in members]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            f"These {len(members)} concepts share most of their name. "
            "If they're the same creative, rename them in Meta to match. "
            "If intentionally distinct (e.g. different version), no action needed."
        )
        st.divider()

# In main(), before the priority action stack:
data_quality = results.get("data_quality", {})
if data_quality:
    render_data_quality_card(data_quality)
```

---

## Definition of Done

- [ ] SKILL.md Shared Step: canonical name normalization documented with suffix stripping rules + iterative application + display name = longest raw name + `name_variants` field
- [ ] SKILL.md § Data Quality section: LCP detection pass, cluster emission, `data_quality` block in Phase 5 output
- [ ] SKILL.md Phase 5 results.json spec: `data_quality` key documented as required
- [ ] `dashboard_template.py`: `render_data_quality_card()` implemented and wired in `main()`
- [ ] Verified on `act_748122004521787`: BrandonPodcast and UGCVideo Copy clusters merged (Tier 1)
- [ ] Verified: IfSomeoneJust cluster appears in data_quality card (Tier 2)
- [ ] Total spend unchanged across all analyses (merge is aggregation, not loss)
- [ ] Empty `data_quality.likely_related_concept_clusters` → no card rendered (no crash)

---

## Risk and Compatibility Check

**Primary Risk (Tier 1):** Incorrectly stripping a non-copy suffix that happens to end in `" - Copy"` pattern. The regex is narrow (must be at end of string, preceded by ` - `) and handles only the documented Meta UI behavior. False-positive risk: near-zero.

**Primary Risk (Tier 2):** Two intentionally distinct concepts flagging as likely-related (V1 vs V3 version iteration). Mitigation: the card explicitly says "if intentionally distinct, no action needed" — no data is changed.

**Rollback:**
- Tier 1: Remove normalization paragraph from SKILL.md Shared Step. Rerun `/meta-diagnostics` — maps rebuild from raw names.
- Tier 2: Remove § Data Quality from SKILL.md + remove `render_data_quality_card` from dashboard. Old `results.json` files already lack `data_quality` key → no change in rendered output.

- [x] No breaking changes — `name_variants` is additive; older results degrade gracefully
- [x] All analysis verdicts remain valid after merge (aggregated spend/conversions, not dropped)
- [x] `data_quality` card is conditional (not rendered if key absent or clusters empty)
- [x] No changes to A1–A7 individual analysis logic

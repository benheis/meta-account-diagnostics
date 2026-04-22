# meta-account-diagnostics

A Claude skill that runs a full Meta Ads account audit in one command — built on proven diagnostic frameworks and the Motion Creative Benchmarks 2026.

Run `/meta-diagnostics` and get:
1. A structured **Markdown report** saved to `~/meta-diagnostics/`
2. An interactive **Streamlit dashboard** — auto-generated and auto-launched

---

## Prerequisites

This skill needs access to your Meta Ads data. It's designed to work with any MCP server or data connector that exposes the following tools:

- `check_connection` — verify the Meta connection is live
- `meta_get_ads` — ad-level spend, CPA, and `created_time`
- `meta_get_account_overview` — account-level spend summary
- `meta_get_monthly_reach` — per-month reach, impressions, and spend

**Recommended:** [ads-mcp-connector](https://github.com/benheis/ads-mcp-connector) — a free, open-source MCP server that connects Claude to live Meta Ads (and Google Ads) data. If you already have it set up, you're ready to go. If not, run `/ads-connect` in Claude Code to get connected in a few minutes.

You can also bring your own MCP server or data layer — as long as it surfaces the tools above, the skill will work.

---

## Install

**Option 1 — Global install (one command, available everywhere):**

```bash
git clone https://github.com/benheis/meta-account-diagnostics.git
cd meta-account-diagnostics
bash install.sh
```

This registers `/meta-diagnostics` as a globally available skill. Run it from any project, in any session — it's always there.

**Option 2 — Clone into your project (no terminal setup required):**

```bash
git clone https://github.com/benheis/meta-account-diagnostics.git
```

Open the `meta-account-diagnostics` folder in your AI coding tool. The `/meta-diagnostics` command is available immediately via the `.claude/commands/` directory — no additional steps.

This works in Claude Code, Cursor, Codeium, and any other tool that reads from `.claude/commands/`.

---

## What it does

The skill walks you through a one-time setup (account ID, conversion event, industry vertical, winner spend threshold), then runs 7 analyses:

| # | Analysis | What it tells you |
|---|---|---|
| 1 | Test & Learn Spend Optimization | Whether your testing budget is well-allocated — are you cutting losers fast and scaling winners? Plots CPA vs. spend across all ads to identify scaled underperformers eating budget. |
| 2 | Creative Allocation | Whether spend is following your best performers or scattered across mediocre ones. Measures spend concentration in your top 1% and top 10% of ads by CPA. |
| 3 | Reliance on Old Creative | How much of your budget is running on aging creatives. Heavy spend on older ads is a leading indicator of fatigue — financial metrics typically lag by 4–6 weeks. |
| 4 | Creative Churn | How fast your ad cohorts decay and whether you're launching enough new creative to sustain performance. Shows month-by-month cohort spend share over time. |
| 5 | Production & Slugging Rate | Your hit rate — what % of launched ads become winners. Benchmarked against Motion 2026 data by spend tier, with a baseball-style at-bats vs. hits breakdown. |
| 6 | Rolling Reach | How many net-new people you're actually adding each month, and what you're paying to reach them. Signals audience saturation before CPAs start rising. |
| 7 | Creative Volume vs. Spend | Whether you're launching enough creative for your spend level and industry vertical, benchmarked against Motion 2026 median and top quartile for your tier. |

Each analysis produces a **HEALTHY / WARNING / CRITICAL** verdict, a plain-English explanation, and a specific recommended action.

---

## Output

**Markdown report:** `~/meta-diagnostics/report-YYYY-MM-DD.md`

**Streamlit dashboard:** auto-launched at `http://localhost:8501`
- One card per analysis with Plotly charts
- Sidebar health score summary
- Priority Action Stack at the bottom

---

## Benchmarks

Analysis 5 (Slugging Rate) and Analysis 7 (Creative Volume vs. Spend) use data from the [Motion Creative Benchmarks 2026](https://content.motionapp.com/hubfs/Benchmarks-Report-2026.pdf) — 550K+ ads, 6,000+ advertisers, $1.3B spend across 16 industry verticals and 5 spend tiers. The benchmark table is hardcoded in `data/motion-benchmarks.json`.

---

## Repo structure

```
meta-account-diagnostics/
├── .claude/commands/meta-diagnostics/SKILL.md   — skill prompt
├── data/motion-benchmarks.json                  — Motion 2026 benchmark table
├── templates/dashboard_template.py              — Streamlit dashboard template
├── scripts/launch.sh                            — dashboard launcher
├── config/config-schema.json                    — ~/.meta-diagnostics-config.json schema
├── secrets_check.py                             — pre-commit credential scan
└── install.sh                                   — global skill registration
```

---

## Python dependencies

Installed automatically by the skill on first run:
- `streamlit` — dashboard server
- `plotly` — charts
- `pandas` — data manipulation
- `requests` — API calls

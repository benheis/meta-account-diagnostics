# meta-account-diagnostics

A Claude Code skill that runs a full Meta Ads account audit in one command — built on Curtis Howland's diagnostic frameworks and the Motion Creative Benchmarks 2026.

Run `/meta-diagnostics` and get:
1. A structured **Markdown report** saved to `~/meta-diagnostics/`
2. An interactive **Streamlit dashboard** — auto-generated and auto-launched

---

## Prerequisites

**[ads-mcp-connector](https://github.com/benheis/ads-mcp-connector)** must be installed and connected to your Meta account. Run `/ads-connect` in Claude Code first if you haven't already.

---

## Install

```bash
git clone https://github.com/benheis/meta-account-diagnostics.git
```

Open the `meta-account-diagnostics` folder in Claude Code. The `/meta-diagnostics` command is available immediately — no terminal setup required.

```
/meta-diagnostics
```

**Want it available globally** (from any project, not just this folder)? Run:

```bash
bash install.sh
```

---

## What it does

The skill walks you through a one-time setup (account ID, conversion event, industry vertical, winner spend threshold), then runs 7 analyses:

| # | Analysis | Source |
|---|---|---|
| 1 | Test & Learn Spend Optimization | Curtis Howland |
| 2 | Creative Allocation | Curtis Howland |
| 3 | Reliance on Old Creative | Curtis Howland |
| 4 | Creative Churn | Curtis Howland |
| 5 | Production & Slugging Rate | Curtis Howland + Motion 2026 |
| 6 | Rolling Reach | Curtis Howland |
| 7 | Creative Volume vs. Spend | Motion Creative Benchmarks 2026 |

Each analysis produces a **HEALTHY / WARNING / CRITICAL** verdict, a plain-English explanation, and a specific recommended action.

---

## Output

**Markdown report:** `~/meta-diagnostics/report-YYYY-MM-DD.md`

**Streamlit dashboard:** auto-launched at `http://localhost:8501`
- One card per analysis with Plotly charts
- Sidebar health score summary
- Priority Action Stack at the bottom

---

## Framework credits

- [Curtis Howland](https://www.linkedin.com/in/curtishowland/) — Test & Learn, Creative Allocation, Creative Churn, Rolling Reach frameworks
- [Motion Creative Benchmarks 2026](https://content.motionapp.com/hubfs/Benchmarks-Report-2026.pdf) — 550K+ ads, $1.3B spend, industry vertical × spend tier benchmarks

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
└── install.sh                                   — registers the skill
```

---

## Python dependencies

Installed automatically by the skill on first run:
- `streamlit` — dashboard server
- `plotly` — charts
- `pandas` — data manipulation
- `requests` — API calls

---
name: skills-trending-analysis
description: Fetches trending skills directly from skills.sh, generates statistics, and creates a trend summary. Optimized for ultra-fast, direct execution without complex setup.
---

# Skills Trending Analysis (Direct API)

Fetches trending information from the `skills.sh` ecosystem by directly communicating with its internal JSON API.

This Skill is designed to be **"Zero-Setup Ready"** by focusing on standard Python libraries.

---

# Input

A keyword can be optionally specified for filtering.

- With keyword: Filters the fetched items by the keyword.
- Without keyword: Fetches the top trending items.

Examples: `swift`, `python`, `agent`

---

# Output

Generates results including the following:

1. Trending summary
2. Top skills
3. Keyword ranking
4. Developer ranking
5. Ecosystem analysis

---

# Execution Steps (Smart Flow)

### 1. Try Direct Execution (Fastest)

Most environments already have the necessary `requests` library. Try running directly:

```bash
python3 scripts/fetch_trending.py
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

---

### 2. If it fails (Environment Setup)

If you get a `ModuleNotFoundError: No module named 'requests'`, then set up the environment:

**Using uv (Recommended)**:
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

**Using standard pip**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

# Data Fetching Strategy

- **Direct API Access**: Communicates directly with `https://skills.sh/api/skills/all-time`.
- **No Browser Required**: Eliminates dependencies like Chromium or Playwright.
- **Efficient**: Uses pagination to fetch precisely what is needed.
- **Cached**: Results are cached locally for 1 hour.

---

# Statistical Analysis Specifications

- **summary**: Total skills, installs, unique developers/keywords.
- **skill_ranking**: Sorted by install counts.
- **keyword_ranking**: Frequency and install impact.
- **developer_ranking**: Top developers and their specialties.
- **concentration**: Market share analysis.

---

# Final Summary by AI

Based on the Python analysis results, the AI will provide a premium trend report. Use the output of `analyze_trending.py` as the source of truth for all numerical data.

---

# Referenced Files

- requirements.txt
- scripts/fetch_trending.py
- scripts/analyze_trending.py
- references/output-format.md

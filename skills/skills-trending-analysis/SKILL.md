---
name: skills-trending-analysis
description: Fetches trending skills directly from skills.sh, generates statistics, and creates a trend summary. Optimized for ultra-fast, direct execution without complex setup. Provides deep insights into the Agent Skills ecosystem.
---

# Skills Trending Analysis (Direct API)

Fetches trending information from the `skills.sh` ecosystem by directly communicating with its internal JSON API.

This Skill is optimized for maximum simplicity and speed. No browser, Chromium, or middleman servers are required.

---

# Input

A keyword can be optionally specified for filtering.

- With keyword: Filters the fetched items by the keyword.
- Without keyword: Fetches the top trending items.

Examples: `swift`, `python`, `agent`

---

# Output

Generates results including the following:

1. **Trending summary**: High-level overview of the current ecosystem state.
2. **Top skills**: Ranking of the most popular skills by install count.
3. **Keyword ranking**: Analysis of dominant topics and technologies.
4. **Developer ranking**: Insights into top creators and their specialized areas.
5. **Ecosystem analysis**: Market concentration and growth tendencies.

Statistical processing is performed in Python to ensure accuracy, and the AI provides premium insights based on those results.

---

# Execution Steps (Smart Flow)

### 1. Try Direct Execution (Fastest)

Most environments already have the necessary `requests` library. Try running directly:

```bash
# Fetch data
python3 scripts/fetch_trending.py --limit 1000

# Perform statistical analysis
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

---

### 2. If it fails (Environment Setup)

If you get a `ModuleNotFoundError: No module named 'requests'`, then set up the environment:

**Using uv (Recommended)**:
```bash
uv venv
source .venv/bin/activate
uv pip install requests
```

**Using standard pip**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
```

---

# Data Fetching Strategy

- **Direct API Access**: Communicates directly with `https://skills.sh/api/skills/all-time`.
- **Standalone**: Does not require any background processes or external servers.
- **Efficient**: Uses pagination to fetch the requested number of items.
- **Cached**: Results are cached locally for 1 hour to improve UX.

---

# Statistical Analysis Specifications

The `analyze_trending.py` script generates a detailed JSON report. The AI should use the following data points:

- **summary**: 
    - `total_skills`: Count of items fetched.
    - `total_installs`: Sum of all installs.
    - `unique_developers`: Number of distinct creators.
    - `unique_keywords`: Number of distinct topics found in titles.
- **skill_ranking**: 
    - Top items sorted by `installs`.
    - Identifying "Hero Skills" that define the current trend.
- **keyword_ranking**: 
    - `keyword_ranking_by_installs`: Keywords associated with the highest install volume.
    - `keyword_ranking_by_skill_count`: Keywords with the most varied skill entries.
- **developer_ranking**: 
    - Ranking by `total_installs`.
    - Lists `top_keywords` for each developer to identify their expertise.
- **concentration**: 
    - `top_10_skill_install_share`: How much of the market is held by the top 10 items.
    - `top_10_developer_install_share`: Market dominance of the top 10 creators.

---

# Final Summary by AI

Based on the Python analysis results, the AI will generate a comprehensive report including:

1. **Mainstream technologies and topics**: What is currently "hyped" in the ecosystem.
2. **Trends among high-install skills**: Shared characteristics of the most successful skills.
3. **Keyword concentration tendencies**: Whether the market is focusing on specific tech (e.g., React, AI, Automation).
4. **Developer Expertise**: Short descriptions of each top developer's specialized area based on their keywords.
5. **Overall summary and insights**: Actionable conclusion and future outlook.

> [!IMPORTANT]
> The AI must not recalculate statistical values itself. Use the output of `analyze_trending.py` as the absolute source of truth for all numerical data.

---

# Principles Upon Failure

If script execution fails:
1. Check if the direct API endpoint has changed.
2. Verify network connectivity.
3. Check if the local cache (`tmp/trending.json`) can be used as a fallback.

---

# Referenced Files

- requirements.txt
- scripts/fetch_trending.py
- scripts/analyze_trending.py
- references/output-format.md

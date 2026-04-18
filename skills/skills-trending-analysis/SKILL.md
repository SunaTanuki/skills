---
name: skills-trending-analysis
description: Fetches trending skills directly from skills.sh, generates statistics, and outputs a comprehensive trend report to the chat. Use this for ultra-fast, data-driven analysis of the Agent Skills ecosystem.
---

# Skills Trending Analysis (Direct API)

Fetches trending information from the `skills.sh` ecosystem by directly communicating with its internal JSON API and generating a premium report.

---

# Input

A keyword can be optionally specified for filtering.

- `--limit`: Number of items to fetch (default: 1000).
- With keyword: Filters the fetched items by the keyword.
- Without keyword: Fetches the top trending items.

Examples: `swift`, `python`, `agent`

---

# Output & Deliverables

The goal of this skill is to provide the user with a **final report in the chat**, not just generating data files.

1. **Data Artifacts (Internal)**: JSON files in `tmp/` containing the raw and analyzed statistics.
2. **Final Report (User-Facing)**: A structured summary output directly to the chat, following the specific format in `references/output-format.md`.

---

# Standard Workflow (Essential Steps)

To complete this skill, you MUST execute ALL three steps below in order.

### Step 1: Data Fetching (Direct API)
Fetch the trending data from the ecosystem.
```bash
python3 scripts/fetch_trending.py --limit 1000
```
*Artifact: `tmp/trending.json`*

### Step 2: Statistical Analysis
Process the fetched data to generate ranked statistics and concentration metrics.
```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```
*Artifact: `tmp/trending_analysis.json`*

### Step 3: Final Report Generation (Required)
1. Read the analyzed results from `tmp/trending_analysis.json`.
2. **Read `references/output-format.md`** to confirm the required report structure and rules.
3. Output the final report directly to the chat. **The task is NOT complete until this report is visible to the user.**

---

# Definition of Completion
This skill is considered "SUCCESSFUL" only when:
- The statistical scripts have executed without error.
- The AI has provided a long-form report in the chat that interprets the numerical data.
- All numerical values in the report exactly match the `tmp/trending_analysis.json` output.

---

# Environment Setup (If needed)

If `requests` is missing from your environment, follow these steps:

**Using uv (Recommended)**:
```bash
uv venv && source .venv/bin/activate && uv pip install requests
```

**Using standard pip**:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install requests
```

---

# Statistical Analysis Specifications (Default)

Running analyze_trending.py with default arguments (suffix phrase merge off, top 20 items) generates the following.

**summary**

- total_skills
- total_installs
- unique_developers
- unique_keywords

**skill_ranking**

Ranked in descending order of installs. Fields: rank, title, developer, installs

**keyword_ranking** (Default: simple split)

Splits titles by `-` into keywords. Only when `--suffix-merge` is specified, specific suffixes (practices, review, design, generation, browser) are merged with the previous word into a 2-word phrase (e.g., best-practices, code-review).

Rules:

- Convert to lowercase
- Exclude empty strings
- Count identical keywords within the same skill only once
- If a phrase is used, do not count the original words as separate keywords

There are 2 rankings: `keyword_ranking_by_installs` and `keyword_ranking_by_skill_count`. Fields for each: rank, keyword, skill_count, total_installs

**developer_ranking**

Aggregated by the developer. Fields: rank, developer, skill_count, total_installs, **top_keywords**, **top_skills_by_installs**. top_keywords are frequent keywords appearing in the developer's skill titles. top_skills_by_installs are a maximum of 3 skills with the highest installs (title, installs).

**concentration**

- top_10_skill_install_share: Sum of installs of top 10 skills / total_installs (0~1)
- top_10_developer_install_share: Sum of total_installs of top 10 developers / total_installs (0~1)

---

# Final Summary by AI

Based on the Python analysis results, the AI will generate:

1. Mainstream technologies and topics
2. Trends among skills with high install counts
3. Keyword concentration tendencies
4. Short descriptions of each developer's area of expertise
5. Overall summary and insights

The AI must not recalculate statistical values itself. Use the output of analyze_trending.py as the basis for numbers. See `references/output-format.md` for details.

---

# Referenced Files
- requirements.txt
- scripts/fetch_trending.py
- scripts/analyze_trending.py
- references/output-format.md

---
name: skills-trending-analysis
description: Fetches the trending page from skills.sh, generates statistics for skills, developers, and keywords, and creates a trend summary. Use this when you want to know about popular skills, trend analysis, developer rankings, and keyword trends on skills.sh.
---

# Skills Trending Analysis

Fetches trending information from `skills.sh` and generates statistical analysis and summaries of the skill ecosystem.

This Skill retrieves a list of trending skills, performs extraction with structure validation, processes statistics, and summarizes overall trends based on the results.

---

# Input

A keyword can be optionally specified.

- With keyword: `https://skills.sh/trending?q=<keyword>`
- Without keyword: `https://skills.sh/trending`

Examples: `swift`, `python`, `agent`

---

# Output

Generates results including the following:

1. Trending summary
2. Top skills
3. Keyword ranking
4. Developer ranking
5. Ecosystem analysis

Statistical processing is performed in Python, and the AI provides insights and summaries based on those results.

---

# Execution Environment

This Skill uses Python and Playwright to fetch web pages.

Expected execution environment:

- Python 3.10 or higher
- Python virtual environment `.venv` within the skill directory
- Playwright
- Chromium

Dependencies must be installed only in `.venv`.  
Adding dependencies to the global Python environment is prohibited.

The purpose of this design is to:

- Maintain reproducibility of Skill execution
- Avoid dependency conflicts with the user's environment
- Enable standalone execution of the Skill

---

# First-Time Setup

Run the following only the first time:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Virtual environment rules:

- Do not recreate `.venv` if it already exists
- Create `.venv` only if it does not exist
- Install dependencies only in `.venv`
- Do not add dependencies to the global environment
- Recreate the virtual environment only if it is corrupted

---

# Data Fetching Strategy

No official public API has been confirmed for skills.sh.  
Additionally, the site uses Next.js App Router + React Server Components, and regular HTTP GET requests may return static HTML that does not reflect search results.

Therefore, this Skill adopts the following method:

1. Render the page using Playwright
2. Retrieve the DOM after executing JavaScript
3. Save the rendered HTML to `tmp/`
4. Parse the HTML with the extraction script

The browser MCP is not used. This Skill prioritizes reproducible Python script execution.

---

# Future API Support

If an official API for skills.sh becomes public in the future, the fetching method will switch to the following priority:

API → HTML Parsing (Playwright)

In other words:

1. Use the API if available
2. Use HTML parsing only if the API does not exist

---

# Pipeline

The processing of this Skill proceeds in the following order:

```
fetch
  ↓
validate + extract
  ↓
analyze
  ↓
summary
```

Role division:

- **Python**: fetch, structure validation, extraction, statistical analysis
- **AI**: Interpretation of statistical results, summarization of developer trends, overall reasoning, and final report generation

---

# Execution Steps

**Default Execution**: Run "1. Data Fetching" followed by "3. Statistical Analysis" below. This combination is the standard pipeline, and the analysis results will include **developer's top_skills_by_installs** (top 3 representative skills) and **concentration** (concentration metrics). Keywords are split using `-` (suffix phrase merge is **off by default**. To enable it, specify `--suffix-merge`). The number of top ranking items is **20 by default**.

---

## 1. Data Fetching

Without keyword:

```bash
python3 scripts/fetch_trending.py
```

With keyword:

```bash
python3 scripts/fetch_trending.py --keyword swift
```

- **Default (with scrolling collection)**: Concatenates links while scrolling and saves to **`tmp/trending.json`** (`tmp/trending_<keyword>.json` if a keyword is specified). HTML is not saved in this case. Proceed to "3. Statistical Analysis" (Skip 2).
- **When `--no-collect-while-scroll` is specified**: Scrolls, returns to the top, and saves `tmp/trending_raw.html`. Then, proceed to "2. Structure Validation and Extraction" to generate `tmp/trending.json` from the HTML before moving to "3. Statistical Analysis".

In all cases, the input for statistical analysis will always be **`tmp/trending.json`** (`tmp/trending_<keyword>.json` if a keyword is specified).

---

## 2. Structure Validation and Extraction (Only when `--no-collect-while-scroll`)

Performed only when fetching is executed with `--no-collect-while-scroll`. The extraction script includes structure validation functionality.

Regular trending:

```bash
python3 scripts/extract_trending.py --html tmp/trending_raw.html --output tmp/trending.json
```

With keyword:

```bash
python3 scripts/extract_trending.py --html tmp/trending_swift_raw.html --output tmp/trending_swift.json
```

Extraction script rules:

- Extract only if the HTML structure matches expectations
- If the structure does not match, stop and report failure
- AI directly reading HTML and guessing values is prohibited
- If the structure changes, modify or recreate the extraction script

---

## 3. Statistical Analysis (Default)

The input is always `tmp/trending.json` (or `tmp/trending_<keyword>.json`).  
The output of this step includes developer's top_skills_by_installs and concentration. Keywords are split simply by `-` (suffix phrase merge is enabled only when `--suffix-merge` is specified). Rankings are limited to the top **20** by default.

Regular trending:

```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

With keyword:

```bash
python3 scripts/analyze_trending.py --input tmp/trending_swift.json --output tmp/trending_swift_analysis.json
```

Specifying the number of top items:

```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json --top 20
```

`--top 0` means all items. If omitted, the top 20 items are used. Attach `--suffix-merge` to use suffix phrase merging.

---

# Extracted Data Specifications

JSON upon successful extraction:

- Each item includes **rank** (the # column in the table, starting from 1), title, developer, and installs.
- **rank_consistency**: Verifies if the rank starts from 1. If a different range is fetched in an infinite scroll, min(rank) > 1 will make 'ok' false.
- Available rank range can be checked with rank_min / rank_max.

```json
{
  "ok": true,
  "structure_valid": true,
  "rank_consistency": true,
  "rank_min": 1,
  "rank_max": 97,
  "items": [
    {
      "rank": 1,
      "title": "agent-tools",
      "developer": "toolshell",
      "installs": 11400
    }
  ]
}
```

JSON upon extraction failure:

```json
{
  "ok": false,
  "structure_valid": false,
  "errors": [
    "skill card not found",
    "install count selector missing"
  ]
}
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

# Principles Upon Failure

If script execution fails, do the following:

1. Identify the name of the failed process
2. Check the observed errors
3. Provide a concise summary to the user

Include the following in the report:

- Which process failed
- What was observed
- The cause as far as currently known
- Whether additional response is needed

Separate observed facts from speculations.

---

# Unexpected Issues

The following situations are treated as unexpected issues:

- Playwright fails to start
- Chromium installation fails
- HTML structure differs significantly from expectations
- Script stops due to an undefined exception
- Missing necessary dependencies
- Recovery outside standard procedures is required

In these cases:

- Do not force execution
- Do not attempt unauthorized workarounds
- Immediately report the situation to the user
- Ask the user for instructions on the next steps

---

# Referenced Files

Refer to the following as needed.

- requirements.txt
- scripts/fetch_trending.py
- scripts/extract_trending.py
- scripts/analyze_trending.py
- references/output-format.md

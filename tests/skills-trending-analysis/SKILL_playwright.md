---
name: skills-trending-analysis-playwright
description: (LEGACY/VALIDATION) Fetches the trending page from skills.sh using Playwright. Use this only for validating the primary API-based skill or if the direct API fails.
---

# Skills Trending Analysis (Playwright/Legacy)

Fetches trending information from `skills.sh` using browser-based scraping with Playwright.

> [!IMPORTANT]
> This is a legacy method used for validation. For standard use, please refer to [SKILL.md](file:///Users/t.miyano/solaair/skills/skills/skills-trending-analysis/SKILL.md).

---

# Input

A keyword can be optionally specified.

- With keyword: `https://skills.sh/trending?q=<keyword>`
- Without keyword: `https://skills.sh/trending`

---

# Execution Environment

This Skill uses Python and Playwright.

Expected execution environment:

- Python 3.10 or higher
- Playwright
- Chromium

---

# Setup

```bash
uv pip install playwright beautifulsoup4
playwright install chromium
```

---

# Execution Steps

### 1. Data Fetching (Playwright)

Without keyword:
```bash
python3 scripts/fetch_trending_playwright.py
```

With keyword:
```bash
python3 scripts/fetch_trending_playwright.py --keyword swift
```

- **Default**: Saves to `tmp/trending.json`.
- **With `--no-collect-while-scroll`**: Saves `tmp/trending_raw.html`. Then run step 2.

### 2. Structure Validation and Extraction (Legacy)

Only if using `--no-collect-while-scroll`:
```bash
python3 scripts/extract_trending.py --html tmp/trending_raw.html --output tmp/trending.json
```

### 3. Statistical Analysis

```bash
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

---

# Pipeline

```
fetch (Playwright)
  ↓
validate + extract (Optional)
  ↓
analyze
  ↓
summary (AI)
```

---

# Referenced Files

- scripts/fetch_trending_playwright.py
- scripts/extract_trending.py
- scripts/analyze_trending.py

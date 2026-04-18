# Skills Trending Analysis (Zero-Setup Ready)

This is a high-performance Skill that fetches trending items directly from the `skills.sh` ecosystem via its internal JSON API.

## Core Values

- **Smart Execution**: No `venv` required if `requests` is already in your environment. Just run and go.
- **Direct API**: Bypasses browser-based scraping for 10x faster execution.
- **Minimalist**: Only 1 essential dependency (`requests`).
- **Reliable**: Uses stable JSON endpoints instead of fragile HTML parsing.

## Quick Start

### 1. Try running directly
```bash
python3 scripts/fetch_trending.py
python3 scripts/analyze_trending.py --input tmp/trending.json --output tmp/trending_analysis.json
```

### 2. If it fails (Setup)
If you see a `ModuleNotFoundError`:
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
# Now repeat step 1
```

## Output

- **tmp/trending.json** — Raw JSON data from the API
- **tmp/trending_analysis.json** — Processed statistical results
- **Report** — Premium AI analysis based on the statistics

## References

- **SKILL.md** — Detailed instructions and smart flow specifications
- **references/output-format.md** — AI report format specifications

# page-streaming

A common observation Skill to fetch dynamic web pages **synchronously**.  
It opens a URL using Playwright, executes an optional arbitrary init script, and then **continuously captures up to N pages**, saving the meta-information of each page to `sessions/<name>/pages/page_0NN.json` before completing.

## Role

- **What it does**: Opens a URL, executes an init script (such as searching or clicking) if provided, scrolls and captures up to N pages, and saves the results to `sessions/<name>/pages/`.
- **What it does not do**: Domain-specific extraction, ranking calculation, or site-by-site normalization.

It does not use background polling or state/command files. The fetching completes within one command.

## Prerequisites

- Python 3.10+
- Playwright (Chromium)

Dependencies are installed exclusively in the `.venv` inside this Skill's directory.

## Quick Start

```bash
# First time only
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Fetch (executes synchronously and waits until completion. --max-pages is the maximum number of new pages to fetch; default is 3)
python3 scripts/page_streamer.py --url "https://example.com/list" --session-name skills

# Fetch after manipulating the page using an init script (e.g., MakerWorld)
python3 scripts/page_streamer.py --url "https://makerworld.com/en" --session-name maker --init-script scripts/init_scripts/makerworld_household.js --max-pages 5
```

The results are output as meta-information for each page (e.g., `page_001.json`) and logged to `sessions/<name>/logs/streamer.log`.

**If data already exists under the same `--session-name`**: The `sessions/{session-name}` directory will be **completely deleted** at the start of execution before fetching. The save destination is fixed to `sessions/{session-name}` relative to the script location. The process will terminate with an error if the folder cannot be created.

## Folder Structure

- **sessions/** — Output for each session (pages/, logs/)
- **scripts/page_analyzer/** — Scripts to combine and display the fetched results
- **scripts/init_scripts/** — JavaScript to run after the page loads (specified by `--init-script`)


## Cleanup (Initialization)

The following can be safely deleted and will be regenerated as needed:

| Target | Description |
|------|------|
| **sessions/** | Session output (pages/, logs/, curl.html, page_type.json, etc.). If deleted, they will be regenerated upon the next fetch. |
| **.venv/** | Virtual environment. If deleted, recreate it following the "Prerequisites" step (or the installation steps in SKILL.md). |

## Documentation

- **SKILL.md** — Responsibilities, execution procedures, and options
- **references/output-format.md** — Output format of the Skill's execution results

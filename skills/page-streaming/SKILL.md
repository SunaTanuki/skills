---
name: page-streaming
description: Determines the web page type and fetches its content using Playwright with the optimal fetching strategy.
---

# page-streaming

A support Skill that saves web page content to structured files for efficient use in analysis.

A key feature is that for sites that dynamically change upon scrolling, it fetches content by **dividing it into page units** while scrolling.

Also, if content cannot be fetched using standard methods, it **detects the page type** from the content's meta-information and **re-fetches** it using a strategy tailored to that type.

---

## Responsibilities

The AI executes this Skill as a task according to the user's instructions and only returns the result.

### What this Skill does

1. First, fetches and saves the page using Playwright.
2. Checks the contents of the fetched results (meta-information of each page).
3. If there are issues, determines the page type (`content_delivery_type` + auxiliary attributes) and decides the fetching strategy and parameters.
4. Adjusts parameters as needed, re-fetches, and outputs the result.

### What this Skill does NOT do

- Subsequent analysis using the complete fetched results (full text).

---

## Rules (Mandatory)

### Prohibition of Data Imputation

- **Do not supplement any un-fetchable data with information from other sources (other sites, APIs, manual lists, etc.).**
- Example: If expected content isn't rendered in the DOM after scrolling, do not use other sources to fill it in.

### Procedures in the Event of a Problem

- If issues occur such as deficiencies, omissions, or inconsistencies in the fetched data, **report the situation to the user and ask for their judgment**.
- Do not make up or supplement data without the user's instructions and assume it's complete.

---

## Execution Environment

- Python 3.10+
- Playwright (Chromium)
- Dependencies are isolated in the `.venv` inside the Skill directory.

**Check Installation** (If successful, `OK` will be displayed. If not displayed, it is not installed):

```bash
source .venv/bin/activate && python3 -c "import playwright; print('OK')"
```

**Execute the following ONLY if not installed:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Execution Steps

Refer to each script's `--help` for explanations. `page_streamer.py` performs **page fetching using Playwright** and outputs a list of objects (JSON array) expanding the **meta-information of each page** (the contents of page_0NN.json) to standard output.

### Step 1: Fetch Page
Use Playwright to fetch the content of the specified url.

```bash
python3 scripts/page_streamer.py --url "https://example.com/list" --session-name example
```

To resume from the previous execution:

```bash
python3 scripts/page_streamer.py --session-name example --continue
```

- Refer to `python3 scripts/page_streamer.py --help` for details.

### Step 2: Check Results and Determine Completion
Judge the fetch results from the console output from Step 1.

- **If there are no problems**: Output the results according to the format (`references/output-format.md`) and finish the Skill.
- **If there are problems**: Proceed to Step 3 below (Follow the rule to report fetch defects, omissions, or contradictions to the user and ask for their judgment).

### Step 3: Detect Page Type
If there was a problem with page fetching, detect the page type from the console output of Step 1.

```bash
python3 scripts/detect_page_type.py --url "https://example.com/list" --playwright-json sessions/example/pages/page_001.json
```

- Refer to `python3 scripts/detect_page_type.py --help` for details.

### Step 4: Adjust Parameters and Re-fetch

Based on the judgment result from Step 3, determine the `page_streamer.py` parameters and re-execute.

- Strategy Guidelines:
  - `static_or_ssr` -> If a single page is enough, use `--max-pages=1`, etc.
  - `spa_csr` / `hybrid` -> Keep Playwright as is. Increase `--wait-ms` if necessary.
  - `spa_csr` + `infinite_scroll` -> Check `--scroll-strategy=incremental` and increase `--max-pages`.
  - `spa_csr` + `pagination` -> Consider page navigation using `--init-script`.

- Re-execution Example:

```bash
python3 scripts/page_streamer.py --url "https://example.com/list" --session-name example --scroll-strategy incremental --max-pages 5
```

- After re-fetching, output the result in the same way as Step 2 and finish the Skill.

---

## Session Directory Structure

The results of Step 1 (page fetching) are saved in `sessions/<name>/`.

```
page-streaming/
  sessions/
    <name>/
      pages/
        page_001.json
        page_001.html
        page_001.txt
        page_002.json
        ...
      logs/
        streamer.log
```

---

## References

- **references/output-format.md** — Schema for the meta-information (page_0NN.json) and output format for the execution results

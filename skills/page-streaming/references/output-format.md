# page-streaming Output Format

This file defines the **output format of the Skill's execution results** for the user.

---

## Prohibition Rules (For User-facing Output)

- **Do not output the commands that the Skill uses internally.**  
  Example: Do not include execution examples containing paths, venv activation, or script names like `cd release/page-streaming && source .venv/bin/activate && python3 scripts/page_streamer.py --session-name <name> --continue --max-pages <N>` in the report to the user. If they want to continue fetching, only convey the **usage guidance**, such as "If you wish to fetch more, you can continue by using this Skill again", rather than the specific procedure.

---

## 1. Execution Result (Success / Error)

Indicate whether the execution succeeded or terminated with an error.

---

## 2. Content Summary

Based on the console output of `page_streamer.py`, output **a text summarizing the content of the URL**.
Summarize concisely what was retrieved based on `snippets` and `end_reason` for each page.
Also, if it's possible to resume fetching, add a note advising that they can continue by using the Skill again.

---

## 3. List of Output Files

Based on the console output of `page_streamer.py`, list the files generated as the execution result.

The following paths are used within the same session.

| Type | Path Example | Description |
|------|--------|------|
| Meta-information (JSON) | `sessions/<name>/pages/page_0NN.json` | Meta-information for page number N. Includes snippets, `output_files`, etc. The content is identical to the output of `page_streamer.py`. |
| Full Text | `sessions/<name>/pages/page_0NN.txt` | The full text of the main content (`output_files.all_text`). |
| Full HTML | `sessions/<name>/pages/page_0NN.html` | The full raw HTML of the main content (`output_files.raw_html`). |
| Logs | `sessions/<name>/logs/streamer.log` | Logs of the fetching process. |

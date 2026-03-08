# Output Format (Final AI Summary)

This file defines the format and generation rules for the report produced in the "Final Summary by AI" section of SKILL.md.

The basis for statistical values is strictly limited to the **JSON output of analyze_trending.py**.  
The AI must **not recalculate numerical values**.

---

# Report Structure

The report consists of the following sections:

1. **Trending summary**
2. **Top skills**
3. **Keyword ranking**
4. **Developer ranking**
5. **Ecosystem analysis**

The section order must be maintained.

---

# 1. Trending summary

Explain the overview of the trends using **around 3 to 6 bullet points**.

Content examples:

- Mainstream technologies
- Popular topics
- New categories
- Areas concentrating a high number of installs

Rules:

- Quote numbers from summary / ranking
- Specifically name keywords and skills
- Use **explanations based on observation**, not guesses

Examples:

- Agent-based tools occupy the top ranks
- Many keywords relate to design / ui
- Image / generator related skills are popular

---

# 2. Top skills

Display the **top N skills by installs** in a table format, based on `skill_ranking`.

Table format:

| Rank | Title | Developer | Installs |
|-----|------|------|------|

The number of items is based on the output of analyze_trending.py.

Rules:

- Descending order by installs
- Quote title / developer / installs exactly as they are
- The AI must not alter the rankings

Add a **short 1-2 sentence description** after the table.

Examples:

- The top skills feature many agent-related tools
- Image and video generation skills are also popular

---

# 3. Keyword ranking

Use **both** of the following:

- `keyword_ranking_by_installs`
- `keyword_ranking_by_skill_count`

## Ranking by Installs

| Rank | Keyword | Skill count | Total installs |

The number of items is based on the output of analyze_trending.py.

## Ranking by Skill Count

| Rank | Keyword | Skill count | Total installs |

The number of items is based on the output of analyze_trending.py.

Rules:

- Use the keywords exactly as output by analyze_trending.py
- Default is a simple split of the title by `-` (phrase merging only when --suffix-merge is specified)
- The AI must not independently reconstruct keywords

Write an **interpretation of 2-3 sentences** after the tables.

Examples:

- With many instances of design / ui, there is a high demand for UI-related skills
- Generative types like generator / image are popular

---

# 4. Developer ranking

Use `developer_ranking`.

Table format:

| Rank | Developer | Skill count | Total installs | Top keywords |

The number of items is based on the output of analyze_trending.py.

Display `top_keywords` exactly as it is.

After that, explain the tendencies of each developer in **one line**.

Consider the following for the explanation:

- top_keywords
- top_skills_by_installs

Examples:

toolshell — Agent, image generation, and UI skills
trailofbits — Security and auditing tools

Rules:

- Semantic grouping of keywords is permitted
- Do not alter the numerical value of installs

---

# 5. Ecosystem analysis

Summarize the overall trends in **about 4 to 6 sentences**.

Information to reference:

- summary
- keyword ranking
- developer ranking
- concentration

Perspectives to include:

### Concentration and Distribution

Explain using the `concentration` metrics.

Examples:

- top_10_skill_install_share
- top_10_developer_install_share

### Technical Themes

Examples:

- agent
- design
- image-generation
- data

### Ecosystem Structure

Examples:

- A diverse range of developers exist
- Concentration among specific developers
- Emergence of new categories

---

# Rules for Quoting Numbers

Quote numerical values from the **JSON output of analyze_trending.py**.

Available data:

- summary
- skill_ranking
- keyword_ranking_by_installs
- keyword_ranking_by_skill_count
- developer_ranking
- concentration

The AI must NOT do the following:

- Recalculate installs
- Regenerate rankings
- Re-split keywords

---

# Separation of Fact and Interpretation

**Do not confuse facts with interpretations** in the report.

Facts:

- installs
- rankings
- keyword counts
- developer counts

Interpretations:

- Tech trends
- Popular categories
- Ecosystem structure

Present the facts first, followed by the interpretation.

---

# Final Note

Always include the following statement at the end of the report:

All numerical values and rankings in this report are based on the output of analyze_trending.py.


⸻

# AI Agent Skills

This repository is a collection for publishing and managing **Skills** for AI agents.

Each Skill is a **reusable package of knowledge, workflows, and tools** designed to execute specific tasks.

Skills are independent by folder and can be used or installed individually.

---

# About This Repository

The objectives of this project are:

- Publish practical Skills for AI agents
- Design them as reproducible workflows
- Automate tasks such as scripting, analysis, and data fetching
- Experiment with and share the Skill ecosystem

Many Skills are designed as a **Python script + explicit processing pipeline**.

Example:

fetch
↓
validate
↓
extract
↓
analyze
↓
report

By separating processes in this way, we aim to design Skills that:

- Are easy to debug
- Are highly reusable
- Prevent erroneous inferences by the AI

---

# Skill List

In this repository, Skills are managed by folder.

## skills-trending-analysis

A Skill that fetches trending skills from skills.sh and generates:

- Skill rankings
- Keyword analysis
- Developer rankings
- Ecosystem analysis

It can be used for trend analysis and observing the Skill ecosystem.

Folder:

`skills/skills-trending-analysis/`

---

## page-streaming

*Description pending (Skill related to page units and streaming)*

Folder:

`skills/page-streaming/`

---

# Skill Structure

Each Skill basically has the following structure:

skills/<skill-name>/
├─ SKILL.md
├─ README.md
├─ requirements.txt
├─ scripts/
├─ references/
├─ evals/
└─ examples/

### SKILL.md

Execution specifications for AI agents.

Defines:
- What the Skill does
- How to execute it
- Input/output specifications
- Error handling

### README.md

Explanation for humans.

### scripts/

Scripts that perform the actual processing.

### evals/

Files for evaluation and validation of the Skill.

---

# Design Philosophy

The Skills in this repository are designed with the following principles in mind:

## 1. Separation of Responsibilities between AI and Code

**Deterministic processing**, such as numerical and statistical processing, **is handled by code**.

The AI is mainly responsible for:

- Summarization
- Interpretation
- Explanation

This ensures:

- Reproducibility
- Accuracy
- Stability

---

## 2. Structural Validation

Skills that handle external data always follow this structure:

fetch
↓
validate
↓
extract

If HTML structures or other data formats change, the Skill **halts extraction** to prevent the generation of incorrect data.

---

## 3. Reproducible Execution Environment

Skills are designed to run in an **independent execution environment** as much as possible.

In most cases, it uses:

- Python
- Virtual environment `.venv`
- requirements.txt

---

# Usage

Each Skill can be installed using the `npx skills add` command.

### Install All

```bash
npx skills add tmiyano89/skills
```

### Install Individually (Example)

```bash
npx skills add tmiyano89/skills --skill skills-trending-analysis
```

---

# License

MIT License

---

# Author

t.miyano

GitHub:
https://github.com/tmiyano89

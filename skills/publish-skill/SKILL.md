---
name: publish-skill
description: A workflow for an AI agent to publish a new skill to the public repository, including structure review, clean transfer, and English translation.
---

# publish-skill

A meta-skill that defines the experiential procedure for publishing a newly developed skill into the public `skills` repository. By following this skill, the AI agent can efficiently copy, review, translate, and publish new skills without missing necessary steps.

## When to use

- When a new skill is ready in the development laboratory (e.g., `skills-lab/release/<skill-name>`).
- When you are instructed by the user to "publish the skill".

## Execution Steps

Follow these steps sequentially to publish a skill accurately.

### Step 1: Review and Propose Structure

Check the source directory using available file exploration capabilities.
Review the files against the expected public skill structure:
- `README.md` (Required: User-facing explanation)
- `SKILL.md` (Required: AI execution instructions)
- Dependency files (e.g., `requirements.txt` for Python, `package.json` for Node.js)
- `scripts/` or `src/` (Required if the skill uses executable scripts)
- `references/` or `docs/` (Optional but highly recommended for complex specs, data formats, etc.)

**Action:** If significant structural elements are missing or files are haphazardly placed, propose a better folder structure to the user before proceeding.

### Step 2: Clean Copy to the Public Repository

Copy the necessary files from the source directory to the public repository's `skills/<skill-name>` folder.
**Crucial Exclusions**: You MUST NOT copy environment or temporary files. Judge which files are unnecessary based on the programming language and framework used.
- Exclude language-specific environment folders (e.g., `.venv/`, `node_modules/`, `vendor/`)
- Exclude build caches or temporary files (e.g., `__pycache__/`, `*.pyc`, `.next/`, `dist/`)
- Exclude execution outputs like `sessions/`, `logs/`, `tmp/`
- Exclude redundant `.gitignore` files from the skill subdirectory if the root `.gitignore` suffices
- Exclude evaluation or test data (`evals/`) unless the user explicitly asks to keep them public.

Ensure you perform a clean and controlled copy of only the required source files.

### Step 3: Translate All Content to English

The public repository targets a global audience. Content might be written in various languages depending on the developer's preference.
Locate all copied files and perform translations.
- **Markdown files** (`README.md`, `SKILL.md`, `references/*.md`, etc.): Fully translate the content into English. Ensure the tone is clear and concise.
- **Source Code files** (`scripts/*.py`, `src/*.js`, etc.): Translate all inline comments, docstrings, and CLI help texts (e.g., argument parsing descriptions) into English.
  
*Caution: During script translation, NEVER change the deterministic processing logic, variable names, or function names unless strictly required for translation. Preserve formatting and syntax.*

### Step 4: Update the Root README.md

Open the public repository's root `README.md`.
Add a new section under `# Skill List` for the newly published skill.
Include a brief, localized (English) description of what the skill does and state its folder path explicitly (`skills/<skill-name>/`).

### Step 5: Commit and Push

Verify that all changes are accurate and no unintended files were added.
Execute standard version control commands (e.g., `git add`, `git commit`, `git push`) to publish the changes to the remote repository.
The commit message should concisely state what was added, following standard conventional commits: e.g., `feat: add <skill-name> skill and translate to English`.

## Rules

- **Do not modify the core logic of scripts** during the translation phase.
- **Ensure professional formatting:** The resulting translated documentation must read professionally and retain the original meaning perfectly.
- **Language Adaptability:** Apply relevant cleanup and translation patterns intelligently based on the specific programming language used in the skill.
- **Never commit generated execution data:** Environments, log files, and caches must stay local.

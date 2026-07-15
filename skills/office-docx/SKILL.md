---
name: office-docx
description: Create or edit Word .docx with python-docx (no LibreOffice scripts). Use when user asks to 生成/修改 Word、.docx、报告正文排版 — not for PDF, spreadsheets, or unrelated coding.
---

# Office DOCX (lightweight)

This harness does **not** ship Anthropic’s LibreOffice `scripts/office/*`. Prefer **`python-docx`** (and existing project scripts under `deliverables/` when present).

## When to use

- Generate a new `.docx` from markdown/outline
- Patch headings, paragraphs, tables in an existing `.docx`
- Extract plain text for RAG / review

## Preferred approach

```bash
python -c "import docx; print('ok')"
# or project scripts, e.g. deliverables/*/scripts/*docx*.py
```

### Create

1. Outline headings in markdown first if the doc is long
2. Use `Document()`, styles for Heading 1/2, normal paragraphs
3. Write to a path under `output/` or a user-specified folder
4. Tell the user the output path

### Edit

1. Open with `Document(path)`
2. Prefer paragraph-level edits; avoid brittle XML surgery unless necessary
3. Keep a backup copy before large rewrites when the file is user-owned

### Extract

- Walk `paragraphs` and table cells; preserve heading text for RAG chunking hints

## Anti-patterns

- Calling nonexistent `scripts/office/unpack.py` / `soffice.py` from Anthropic’s full office skill
- Rebuilding an entire 50-page doc when only one section changed
- Mixing PDF pipelines into this skill (`load_skill(pdf)` instead)

## Dependencies

```text
pip install python-docx
```
---

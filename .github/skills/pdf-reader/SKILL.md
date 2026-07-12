---
name: pdf-reader
description: >-
  Use when the user needs to read, extract, or analyze content from a PDF file
  in the workspace. Triggers on: reading a PDF, extracting text from a PDF,
  analyzing a paper or PDF document, checking references in a PDF.
argument-hint: '<path-to-pdf> [--pages 1-5] [--output extracted.txt]'
---

# PDF Reader

## Purpose

Extract plain text from PDF files so the AI can read and reason about their
content. Since AI tools cannot natively parse binary PDFs, this skill provides
a deterministic extraction pipeline that converts any PDF in the repository to
plain text.

## Tool

`tools/extract_pdf.py` — a Python script using `pypdf`.

### Quick usage

```bash
# Extract full PDF to stdout (AI reads from stdout)
python tools/extract_pdf.py path/to/paper.pdf

# Extract specific pages
python tools/extract_pdf.py path/to/paper.pdf --pages 1-5

# Save to a .txt file for later reference
python tools/extract_pdf.py path/to/paper.pdf -o paper.txt

# Handle encrypted PDFs
python tools/extract_pdf.py path/to/paper.pdf --password "secret"
```

### Dependencies

- `pypdf` (installed in the project `.venv`). If missing, run:
  `pip install pypdf`

## Workflow

1. **Locate the PDF** — the user provides a path (absolute or relative to the
   workspace root).
2. **Run the extraction** — execute `python tools/extract_pdf.py <pdf_path>`.
   For large PDFs (>50 pages), use `--pages` to extract a manageable range
   first; iterate as needed.
3. **Read the output** — the extracted text is written to stdout. Use
   `read_file` on stdout output, or redirect to a `.txt` file with `-o` and
   read that file.
4. **Reason about the content** — treat the extracted text as the canonical
   content of the PDF. Be aware of extraction artifacts (merged columns,
   missing tables, garbled equations) and qualify conclusions accordingly.

## Caveats

- **Scanned/image-only PDFs**: `pypdf` cannot extract text from bitmap images.
  For those, OCR (e.g., `pytesseract`) would be needed — this is not part of
  the current tool.
- **Complex layouts**: multi-column text, tables, and equations may be garbled
  or out of order. Flag these when interpreting the text.
- **Large files**: stdout may be truncated. Use `-o <file>` and then read the
  file in chunks.
- **Encodings**: the script attempts UTF-8 output. If the terminal codepage
  causes issues, use `-o` to write to a file.

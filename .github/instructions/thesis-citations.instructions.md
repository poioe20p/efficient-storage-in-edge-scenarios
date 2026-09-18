---
description: "Thesis citation policy: cite only papers whose PDFs are already stored in the literature corpus; never add out-of-corpus papers or BibTeX entries without the user's approval."
applyTo: "tese/**"
---

# Thesis Citations — Cite Only Papers in the Corpus

*The user vets and downloads papers. The agent never adds sources on its own.*

## Corpus-first citations

- For `tese/main.tex` (and any thesis text), cite only papers whose PDFs are
  already stored in `tese/literature_review/`. The citable pool is the
  39-paper RQ review corpus plus the `99_reference/` background subfolders
  (`sdn_background/`, `containers_background/`, `databases_background/`,
  `autoscaling_background/`, `scheduling_background/`, `edge_storage_background/`).

## No out-of-corpus additions without approval

- Never add a paper, DOI, or BibTeX entry to `tese/references.bib` for a
  source whose PDF is not in the corpus. The user is the one who vets and
  downloads new papers.

## Propose first

- When a passage needs a source the corpus does not cover, propose candidate
  papers (Author, Year, Title, Relevance, DOI) to the user and wait for them
  to download the PDF and approve before citing.
- Remove any BibTeX entry that becomes uncited if the paper is out-of-corpus;
  for corpus papers, an unused entry may stay and be flagged.

## BibTeX at first citation

- Entries in `tese/references.bib` are added only when the paper is actually
  cited in the text, via `tools/add_bib_from_doi.py` for DOIs already in the
  corpus. Verify generated keys (e.g., the tool can mangle non-ASCII author
  names) and fix HTML-escaped ampersands before building.

## Extractions next to PDFs

- Before reading a paper, check for an existing full-text extraction (`.txt`)
  next to its PDF and reuse it instead of re-extracting. New extractions are
  written to the PDF's folder, not `temp/`.
- Never delete extraction files; they are kept so that papers do not have to
  be extracted repeatedly.

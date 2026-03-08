#!/usr/bin/env python3
"""Add a BibTeX entry to a .bib file from a DOI.

Fetches metadata from Crossref and appends a generated BibTeX entry.

Examples:
  python tools/add_bib_from_doi.py 10.1109/TNET.2022.3152150
  python tools/add_bib_from_doi.py "https://doi.org/10.1109/INCOFT60753.2023.10425524"
  python tools/add_bib_from_doi.py --dry-run 10.1109/TNET.2022.3152150

Notes:
- Uses only the Python standard library.
- Avoids adding duplicates by DOI (unless --force).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


CROSSREF_WORKS_URL = "https://api.crossref.org/works/{}"
DEFAULT_BIB_PATH = Path("tese") / "references.bib"


_DOI_RE = re.compile(
    r"\b10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+\b",
    re.IGNORECASE,
)


def _squash_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_doi(text: str) -> str:
    """Extract a DOI from arbitrary text/URL/doi:... strings."""
    match = _DOI_RE.search(text)
    if not match:
        raise ValueError("Could not find a DOI in the provided input.")
    return match.group(0)


def _http_get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "bibtex-helper/1.0 (mailto:local)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def fetch_crossref_work(doi: str) -> dict[str, Any]:
    doi_encoded = urllib.parse.quote(doi)
    url = CROSSREF_WORKS_URL.format(doi_encoded)
    data = _http_get_json(url)
    message = data.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Unexpected Crossref response format (missing message).")
    return message


def _first(values: Any, default: str = "") -> str:
    if isinstance(values, list) and values:
        if isinstance(values[0], str):
            return values[0]
    if isinstance(values, str):
        return values
    return default


def _date_parts(work: dict[str, Any]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    for key in ("issued", "published-print", "published-online", "published"):
        node = work.get(key)
        if isinstance(node, dict):
            parts = node.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                year = int(parts[0][0]) if len(parts[0]) >= 1 else None
                month = int(parts[0][1]) if len(parts[0]) >= 2 else None
                day = int(parts[0][2]) if len(parts[0]) >= 3 else None
                return year, month, day
    return None, None, None


def _month_to_bib(month: Optional[int]) -> Optional[str]:
    if not month:
        return None
    months = {
        1: "jan",
        2: "feb",
        3: "mar",
        4: "apr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "aug",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dec",
    }
    return months.get(month)


def _authors_to_bib(authors: Any) -> str:
    if not isinstance(authors, list) or not authors:
        return ""
    formatted: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        given = _squash_ws(str(author.get("given", "")))
        family = _squash_ws(str(author.get("family", "")))
        if family and given:
            name = f"{family}, {given}"
        else:
            name = _squash_ws(" ".join(p for p in (given, family) if p))
        if name:
            formatted.append(name)
    return " and ".join(formatted)


def _slug_words(title: str) -> list[str]:
    # Keep alphanumerics; split; remove common stopwords.
    words = re.findall(r"[A-Za-z0-9]+", title)
    stop = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "based",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "via",
        "with",
    }
    kept = [w for w in words if w.lower() not in stop]
    return kept


def _camel(words: Iterable[str]) -> str:
    return "".join(w[:1].upper() + w[1:] for w in words if w)


def generate_bib_key(authors_bib: str, year: int, title: str) -> str:
    family = ""
    if authors_bib:
        first = authors_bib.split(" and ", 1)[0]
        if "," in first:
            family = first.split(",", 1)[0]
        else:
            family = first.split()[-1]
    family = re.sub(r"[^A-Za-z0-9]+", "", family) or "Anon"

    words = _slug_words(title)
    short = _camel(words[:5]) or "Untitled"
    return f"{family}{year}{short}"


def _format_bibtex_entry(entry_type: str, key: str, fields: list[tuple[str, str]]) -> str:
    rendered_fields = []
    for k, v in fields:
        if not v:
            continue
        if k == "month":
            rendered_fields.append(f"  {k} = {v},")
        else:
            rendered_fields.append(f"  {k} = {{{v}}},")
    if rendered_fields:
        rendered_fields[-1] = rendered_fields[-1].rstrip(",")

    inner = "\n".join(rendered_fields)
    return f"@{entry_type}{{{key},\n{inner}\n}}\n"


def _existing_contains_doi(bib_text: str, doi: str) -> bool:
    return doi.lower() in bib_text.lower()


def _existing_keys(bib_text: str) -> set[str]:
    keys = set()
    for m in re.finditer(r"^@\w+\{\s*([^,\s]+)", bib_text, flags=re.IGNORECASE | re.MULTILINE):
        keys.add(m.group(1).strip())
    return keys


def _ensure_unique_key(desired: str, existing: set[str]) -> str:
    if desired not in existing:
        return desired
    suffix = "a"
    while f"{desired}{suffix}" in existing:
        suffix = chr(ord(suffix) + 1)
        if suffix > "z":
            # Fall back to timestamp if something is really odd.
            return f"{desired}{datetime.now().strftime('%H%M%S')}"
    return f"{desired}{suffix}"


def build_bibtex_from_work(work: dict[str, Any], key_override: Optional[str] = None) -> tuple[str, str]:
    work_type = str(work.get("type", "")).strip().lower()

    title = _squash_ws(_first(work.get("title"), default=""))
    doi = _squash_ws(str(work.get("DOI", "")))
    url = _squash_ws(str(work.get("URL", "")))
    authors = _authors_to_bib(work.get("author"))

    year, month_num, _day = _date_parts(work)
    if not year:
        raise RuntimeError("Crossref metadata did not include a publication year.")
    month = _month_to_bib(month_num)

    # Determine entry type.
    if work_type == "journal-article":
        entry_type = "article"
        journal = _squash_ws(_first(work.get("container-title"), default=""))
        volume = _squash_ws(str(work.get("volume", "")))
        number = _squash_ws(str(work.get("issue", "")))
        pages = _squash_ws(str(work.get("page", "")))
        if pages and "--" not in pages and "-" in pages:
            pages = pages.replace("-", "--")

        fields: list[tuple[str, str]] = [
            ("author", authors),
            ("title", title),
            ("journal", journal),
            ("volume", volume),
            ("number", number),
            ("year", str(year)),
            ("month", month or ""),
            ("pages", pages),
            ("doi", doi),
            ("url", url or (f"https://doi.org/{doi}" if doi else "")),
        ]

    else:
        # Crossref uses e.g. "proceedings-article" for conference papers.
        entry_type = "inproceedings"
        booktitle = _squash_ws(_first(work.get("container-title"), default=""))
        pages = _squash_ws(str(work.get("page", "")))
        if pages and "--" not in pages and "-" in pages:
            pages = pages.replace("-", "--")

        event = work.get("event") if isinstance(work.get("event"), dict) else {}
        address = ""
        if isinstance(event, dict):
            address = _squash_ws(str(event.get("location", "")))

        isbn_value = ""
        isbn = work.get("ISBN")
        if isinstance(isbn, list) and isbn:
            isbn_value = _squash_ws(str(isbn[0]))

        fields = [
            ("author", authors),
            ("title", title),
            ("booktitle", booktitle),
            ("year", str(year)),
            ("month", month or ""),
            ("address", address),
            ("pages", pages),
            ("doi", doi),
            ("url", url or (f"https://doi.org/{doi}" if doi else "")),
            ("isbn", isbn_value),
        ]

    key = key_override or generate_bib_key(authors, year, title)
    entry = _format_bibtex_entry(entry_type, key, fields)
    return key, entry


@dataclass
class AddResult:
    key: str
    doi: str
    wrote: bool
    path: Path


def add_bib_from_doi(
    doi: str,
    bib_path: Path,
    *,
    dry_run: bool,
    force: bool,
    key_override: Optional[str],
) -> AddResult:
    bib_text = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""

    if not dry_run and not force and bib_text and _existing_contains_doi(bib_text, doi):
        return AddResult(key="", doi=doi, wrote=False, path=bib_path)

    work = fetch_crossref_work(doi)
    # Preserve the user's DOI casing and prefer an https doi.org URL.
    work["DOI"] = doi
    work["URL"] = f"https://doi.org/{doi}"
    desired_key, entry = build_bibtex_from_work(work, key_override=key_override)

    existing = _existing_keys(bib_text)
    final_key = _ensure_unique_key(desired_key, existing)
    if final_key != desired_key:
        entry = entry.replace(f"{{{desired_key},", f"{{{final_key},", 1)

    if dry_run:
        sys.stdout.write(entry)
        return AddResult(key=final_key, doi=doi, wrote=False, path=bib_path)

    # Ensure file ends with a single blank line before appending.
    out = bib_text
    if out and not out.endswith("\n"):
        out += "\n"
    if out and not out.endswith("\n\n"):
        out += "\n"
    out += entry

    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text(out, encoding="utf-8", newline="\n")
    return AddResult(key=final_key, doi=doi, wrote=True, path=bib_path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="add_bib_from_doi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Append a BibTeX entry to a .bib file using a DOI (via Crossref).",
        epilog=textwrap.dedent(
            """\
            Tips:
              - You can paste the whole reference text; the script will extract the DOI.
              - Use --dry-run to preview without editing the .bib file.
            """
        ),
    )
    parser.add_argument("input", help="DOI, DOI URL, or any text containing a DOI")
    parser.add_argument(
        "--file",
        dest="bib_file",
        default=str(DEFAULT_BIB_PATH),
        help=f"BibTeX file path (default: {DEFAULT_BIB_PATH.as_posix()})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print entry, do not modify file")
    parser.add_argument("--force", action="store_true", help="Append even if DOI already exists")
    parser.add_argument("--key", dest="key", default=None, help="Override BibTeX key")

    args = parser.parse_args(argv)

    try:
        doi = extract_doi(args.input)
        bib_path = Path(args.bib_file)
        result = add_bib_from_doi(
            doi,
            bib_path,
            dry_run=args.dry_run,
            force=args.force,
            key_override=args.key,
        )
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 2

    if args.dry_run:
        return 0

    if not result.wrote:
        sys.stdout.write(f"DOI already present; no changes made: {doi}\n")
        return 0

    sys.stdout.write(f"Added entry {result.key} to {result.path.as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

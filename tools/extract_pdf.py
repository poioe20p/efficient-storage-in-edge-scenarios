#!/usr/bin/env python3
"""Extract plain text from a PDF file for reading by AI tools.

Uses pypdf to extract text from all pages and writes the result to stdout
or an optional output file. Handles password-protected PDFs and supports
page-range extraction.

Examples:
  python tools/extract_pdf.py paper.pdf
  python tools/extract_pdf.py paper.pdf -o paper.txt
  python tools/extract_pdf.py paper.pdf --pages 1-5
  python tools/extract_pdf.py paper.pdf --password secret

Notes:
- Requires pypdf (pip install pypdf).
- Extracted text may need manual review for tables, multi-column layouts,
  or PDFs that are image-only (scanned documents).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    sys.exit(
        "pypdf is not installed. Run: pip install pypdf\n"
        "Or from the project root: .venv\\Scripts\\pip install pypdf"
    )


def build_page_range(spec: str, total: int) -> list[int]:
    """Parse a page-range string like '1-5,8,10-12' into a 1-indexed list."""
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo_str, hi_str = part.split("-", 1)
            lo, hi = int(lo_str.strip()), int(hi_str.strip())
            if lo < 1 or hi > total:
                raise ValueError(
                    f"Page range {lo}-{hi} out of bounds (1-{total})"
                )
            pages.extend(range(lo, hi + 1))
        else:
            p = int(part)
            if p < 1 or p > total:
                raise ValueError(f"Page {p} out of bounds (1-{total})")
            pages.append(p)
    return sorted(set(pages))


def extract_text(
    pdf_path: Path,
    *,
    pages: list[int] | None = None,
    password: str | None = None,
) -> str:
    """Return the full extracted text of *pdf_path* as a single string."""
    reader = PdfReader(str(pdf_path), password=password)

    if reader.is_encrypted and password is None:
        raise RuntimeError(
            "PDF is encrypted. Provide a password with --password."
        )

    total = len(reader.pages)
    target = pages if pages else list(range(1, total + 1))
    out_lines: list[str] = []

    for page_num in target:
        page = reader.pages[page_num - 1]  # zero-indexed
        text = page.extract_text()
        if text is not None:
            out_lines.append(f"--- Page {page_num} ---")
            out_lines.append(text.strip())
        else:
            out_lines.append(
                f"--- Page {page_num} (no extractable text — may be image-only) ---"
            )

    return "\n\n".join(out_lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract plain text from a PDF file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to the PDF file.",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Write output to this file instead of stdout.",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Page range to extract, e.g. '1-5' or '1,3,7-9'. Default: all pages.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for encrypted PDFs.",
    )
    parser.add_argument(
        "--no-page-markers",
        action="store_true",
        help="Omit '--- Page N ---' markers between pages.",
    )

    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    if args.pdf.suffix.lower() != ".pdf":
        print(
            f"Warning: '{args.pdf}' does not have a .pdf extension. "
            f"Attempting to read anyway.",
            file=sys.stderr,
        )

    reader = PdfReader(str(args.pdf))
    if reader.is_encrypted and args.password is None:
        sys.exit(
            "PDF is encrypted. Provide a password with --password."
        )

    total = len(reader.pages)

    page_list: list[int] | None = None
    if args.pages:
        try:
            page_list = build_page_range(args.pages, total)
        except ValueError as exc:
            sys.exit(str(exc))

    try:
        text = extract_text(
            args.pdf,
            pages=page_list,
            password=args.password,
        )
    except RuntimeError as exc:
        sys.exit(str(exc))

    if args.no_page_markers:
        text = "\n\n".join(
            block for block in text.split("\n\n")
            if not block.startswith("--- Page ")
        )

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Extracted {total} pages → {args.output}")
    else:
        # Write in chunks to avoid Windows console encoding issues with large
        # outputs, but still use UTF-8. Reconfigure stdout for UTF-8 if possible.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        sys.stdout.write(text)


if __name__ == "__main__":
    main()

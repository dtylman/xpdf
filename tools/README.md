# pretty_sicil.py — pretty-print / clean the pass-2 JSON

Consumes the JSON emitted by `xpdf/pdftotext -tablecells`
(`data/out/*.json`) and renders it for humans or for further analysis.

## Run

```bash
python3 tools/pretty_sicil.py data/out/24_Sicil_no.031.json            # terminal view
python3 tools/pretty_sicil.py data/out/24_Sicil_no.031.json --pages 1-10 \
    --format md --fonts                                               # markdown
python3 tools/pretty_sicil.py data/out/24_Sicil_no.031.json \
    --format json -o /tmp/clean.json                                  # cleaned data
python3 tools/pretty_sicil.py --selftest                               # verify bidi inversion
```

Stdlib only (Python 3, no third-party packages).

## Formats

- `--format ascii` (default) — terminal view: paragraphs as labeled
  blocks, tables as aligned ASCII grids (`--wrap` sets the max cell
  width).  Text is printed **as-is** — xpdf's visual order with its
  `U+202A/U+202B/U+202C` bidi embedding marks — which is exactly what a
  bidi-aware terminal expects, so mixed Arabic/Latin lines display like
  the source page.
- `--format md` — Markdown: pages as sections, paragraphs by type,
  tables as MD tables.  Text is cleaned (see `--bidi`).
- `--format json` — the same document with every text field cleaned —
  the analysis-ready form.  (Several input files are emitted as NDJSON.)

## `--bidi` (md/json text cleaning)

- `strip` (**default**) — remove the bidi control marks, keep the text
  order.  Correct for these sicil PDFs: Ghostscript drew their glyphs
  in visual left-to-right order, so the raw JSON text (marks aside) is
  already in reading order.
- `invert` — additionally un-reverse the marked runs (the exact inverse
  of xpdf's `TextPage::encodeFragment`).  Correct for well-formed PDFs
  whose lines xpdf reads in true logical order; re-reverses the Arabic
  into garbage if used on the sicil JSONs.

## Other options

- `--pages 3` / `--pages 1-5` / `--pages 1,3,5-7` — page filter.
- `--fonts` — annotate each paragraph/cell with its `fonts` array
  (normalized `name/style` as used in `data/gylph_index.db`), so a
  wrong character can be traced back to the db rows to fix in
  `glyph_editor`.
- `-o FILE` — write to a file instead of stdout.

Known limitation: the source PDFs draw paren/bracket *glyph shapes* in
visual order, so their logical open/close identity is ambiguous; a bidi
renderer may place them slightly differently than the original page.

# Glyph Index Editor

A small Tkinter GUI for reviewing/correcting `data/gylph_index.db` (the
CID → Unicode correction table built in pass 1, see the root
[README](../README)).

## Run

```bash
python3 glyph_editor.py
```

Defaults to `../data/gylph_index.db` and `../data/gylph_db/`. Both can be
overridden:

```bash
python3 glyph_editor.py path/to/index.db path/to/glyph_db_dir
```

Requires Python 3 with Tkinter (stdlib) and Pillow (`pip install pillow`).

## Use

- **Filter bar** (top): filter by Font (substring), CID (substring), Char
  (substring), and Confidence (H/L/C/All) — updates live as you type.
- The window is split **master/detail** with a draggable divider:
  - **Upper pane** — the chars table (click a column header to sort; click
    again to reverse).
  - **Lower pane** — the selected row's glyph bitmap and index info on the
    left, and the **Char** / **Confidence** edit form, Prev/Next buttons,
    and an **Arabic keyboard** on the right.
- **Click a row** to load its glyph bitmap and current Char/Confidence
  into the lower pane.
- Three ways to apply a correction (all rewrite `gylph_index.db` in place
  immediately, row order preserved, only the edited row changed):
  - **Arabic keyboard** — click a letter to set Char to that letter and
    Confidence to `C`, then save automatically.
  - **Enter inside the Char field** — sets Confidence to `C`, saves, and
    advances to the next row so you can correct glyphs in quick
    succession. (Tabbing/clicking away from the field does *not* save,
    so you can type a value, then pick `H` or `L` from the Confidence
    box and save manually.)
  - **Save button** / global **`Enter`** — saves with whatever
    Confidence is currently chosen; global `Enter` also advances to the
    next row. **`Ctrl+S`** saves without advancing.
- **Prev / Next** step through whatever the current filter shows, so you
  can work through e.g. `Confidence = L` end to end.

Navigating away from a row with unedited changes discards them (a
"unsaved changes" note appears under the form as a reminder) — there's no
multi-row undo, so save each correction before moving on.


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

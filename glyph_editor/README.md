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

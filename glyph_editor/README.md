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
- Click a **column header** to sort by that column (click again to
  reverse).
- **Click a row** to load its glyph bitmap and current Char/Confidence
  into the panel on the right.
- Edit **Char** and/or **Confidence**, then **Save** (button, `Enter`, or
  `Ctrl+S`). This rewrites `gylph_index.db` in place immediately —
  row order is preserved and only the edited row changes.
- **Prev / Next** step through whatever the current filter shows, so you
  can work through e.g. `Confidence = L` end to end.

Navigating away from a row with unedited changes discards them (a
"unsaved changes" note appears under the form as a reminder) — there's no
multi-row undo, so save each correction before moving on.

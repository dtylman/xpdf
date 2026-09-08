#!/usr/bin/env python3
"""
glyph_editor.py -- viewer/editor for data/gylph_index.db

A small Tkinter GUI for reviewing the CID->Unicode correction table built
from data/gylph_db/*.ppm (see ../README.md, pass 1). Lets you filter the
index by font / CID / char / confidence, look at the actual glyph bitmap
for a row, and correct its char and/or confidence (H/L/C) -- saving
rewrites data/gylph_index.db in place (order preserved) after every edit.

Usage:
    python3 glyph_editor.py [path/to/gylph_index.db] [path/to/gylph_db]

Both arguments default to ../data/gylph_index.db and ../data/gylph_db
relative to this script, matching the project layout in README.md.
"""

import glob
import os
import re
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INDEX = os.path.join(HERE, "..", "data", "gylph_index.db")
DEFAULT_GLYPH_DIR = os.path.join(HERE, "..", "data", "gylph_db")

COLUMNS = ("name", "style", "cid", "char", "confidence")
CONF_VALUES = ("H", "L", "C")


class GlyphRow:
    __slots__ = ("name", "style", "cid", "char", "confidence")

    def __init__(self, name, style, cid, char, confidence):
        self.name = name
        self.style = style
        self.cid = cid
        self.char = char
        self.confidence = confidence


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 5:
                raise ValueError(
                    f"{path}:{lineno}: expected 5 tab-separated fields, "
                    f"got {len(parts)}: {line!r}"
                )
            rows.append(GlyphRow(*parts))
    return rows


def save_rows(path, rows):
    # write-then-replace so a crash mid-write can't corrupt the real file
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(
                f"{r.name}\t{r.style}\t{r.cid}\t{r.char}\t{r.confidence}\n"
            )
    os.replace(tmp, path)


class GlyphEditorApp:
    def __init__(self, root, index_path, glyph_dir):
        self.root = root
        self.index_path = index_path
        self.glyph_dir = glyph_dir
        if os.path.isfile(index_path):
            self.rows = load_rows(index_path)
        else:
            self.rows = []
        self.filtered = list(range(len(self.rows)))
        self.current_idx = None
        self.photo = None  # keep a reference so Tk doesn't GC it
        self._sort_reverse = {}
        self._sync_stop = False

        root.title(f"Glyph Index Editor — {os.path.basename(index_path)}")
        root.geometry("1150x650")

        self._build_ui()
        self._refresh_list()

    # ---- UI construction -------------------------------------------------

    def _build_ui(self):
        bar = ttk.Frame(self.root, padding=6)
        bar.pack(side="top", fill="x")

        ttk.Label(bar, text="Name:").pack(side="left")
        self.font_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.font_var, width=18).pack(
            side="left", padx=(2, 10)
        )

        ttk.Label(bar, text="Style:").pack(side="left")
        self.style_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.style_var, width=10).pack(
            side="left", padx=(2, 10)
        )

        ttk.Label(bar, text="CID:").pack(side="left")
        self.cid_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.cid_var, width=10).pack(
            side="left", padx=(2, 10)
        )

        ttk.Label(bar, text="Char:").pack(side="left")
        self.char_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.char_var, width=10).pack(
            side="left", padx=(2, 10)
        )

        ttk.Label(bar, text="Confidence:").pack(side="left")
        self.conf_filter_var = tk.StringVar(value="All")
        ttk.Combobox(
            bar,
            textvariable=self.conf_filter_var,
            values=("All",) + CONF_VALUES,
            width=6,
            state="readonly",
        ).pack(side="left", padx=(2, 10))

        ttk.Button(bar, text="Clear", command=self._clear_filters).pack(
            side="left", padx=(4, 0)
        )

        ttk.Button(
            bar, text="Sync from glyphs", command=self._sync_from_glyphs
        ).pack(side="left", padx=(8, 0))

        for var in (self.font_var, self.style_var, self.cid_var, self.char_var):
            var.trace_add("write", lambda *_: self._refresh_list())
        self.conf_filter_var.trace_add("write", lambda *_: self._refresh_list())

        self.status_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.status_var, foreground="#555").pack(
            side="right"
        )

        body = ttk.Frame(self.root)
        body.pack(side="top", fill="both", expand=True)

        list_frame = ttk.Frame(body)
        list_frame.pack(side="left", fill="both", expand=True)

        self.tree = ttk.Treeview(
            list_frame, columns=COLUMNS, show="headings", selectmode="browse"
        )
        widths = {
            "name": 160, "style": 70, "cid": 60,
            "char": 60, "confidence": 90,
        }
        for c in COLUMNS:
            self.tree.heading(
                c, text=c.capitalize(), command=lambda c=c: self._sort_by(c)
            )
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail = ttk.Frame(body, padding=10, width=340)
        detail.pack(side="right", fill="y")
        detail.pack_propagate(False)

        self.image_label = ttk.Label(detail, relief="sunken", anchor="center")
        self.image_label.pack(fill="x", pady=(0, 10), ipady=40)

        self.info_var = tk.StringVar(value="(no selection)")
        ttk.Label(detail, textvariable=self.info_var, justify="left").pack(
            anchor="w"
        )

        form = ttk.Frame(detail, padding=(0, 15, 0, 0))
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Char:").grid(row=0, column=0, sticky="w")
        self.edit_char_var = tk.StringVar()
        char_font = self._arabic_font()
        self.edit_char_entry = ttk.Entry(
            form, textvariable=self.edit_char_var, font=char_font
        )
        self.edit_char_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Confidence:").grid(row=1, column=0, sticky="w")
        self.edit_conf_var = tk.StringVar()
        ttk.Combobox(
            form,
            textvariable=self.edit_conf_var,
            values=CONF_VALUES,
            width=5,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", pady=4)

        btns = ttk.Frame(detail, padding=(0, 15, 0, 0))
        btns.pack(fill="x")
        ttk.Button(btns, text="Save (Enter)", command=self._save_current).pack(
            side="left"
        )
        ttk.Button(btns, text="← Prev", command=lambda: self._step(-1)).pack(
            side="left", padx=6
        )
        ttk.Button(btns, text="Next →", command=lambda: self._step(1)).pack(
            side="left"
        )

        self.dirty_var = tk.StringVar(value="")
        ttk.Label(detail, textvariable=self.dirty_var, foreground="#a00").pack(
            anchor="w", pady=(8, 0)
        )

        self.root.bind("<Return>", lambda e: self._save_current())
        self.root.bind("<Control-s>", lambda e: self._save_current())
        self.edit_char_var.trace_add("write", lambda *_: self._mark_dirty())
        self.edit_conf_var.trace_add("write", lambda *_: self._mark_dirty())

    @staticmethod
    def _arabic_font():
        # falls back to Tk's default if this family isn't installed
        try:
            import tkinter.font as tkfont

            fams = set(tkfont.families())
            if "Noto Sans Arabic" in fams:
                return ("Noto Sans Arabic", 16)
        except Exception:
            pass
        return ("TkDefaultFont", 16)

    # ---- filtering / listing ----------------------------------------------

    def _clear_filters(self):
        self.font_var.set("")
        self.style_var.set("")
        self.cid_var.set("")
        self.char_var.set("")
        self.conf_filter_var.set("All")

    def _matches(self, r):
        f = self.font_var.get().strip().lower()
        st = self.style_var.get().strip().lower()
        c = self.cid_var.get().strip().lower()
        ch = self.char_var.get().strip()
        cf = self.conf_filter_var.get()
        if f and f not in r.name.lower():
            return False
        if st and st not in r.style.lower():
            return False
        if c and c not in r.cid.lower():
            return False
        if ch and ch not in r.char:
            return False
        if cf != "All" and r.confidence != cf:
            return False
        return True

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        self.filtered = [i for i, r in enumerate(self.rows) if self._matches(r)]
        for i in self.filtered:
            self._insert_row(i)
        self._update_status()

    def _insert_row(self, i):
        r = self.rows[i]
        self.tree.insert(
            "", "end", iid=str(i),
            values=(r.name, r.style, r.cid, r.char, r.confidence),
        )

    def _update_status(self):
        counts = {"H": 0, "L": 0, "C": 0}
        for r in self.rows:
            counts[r.confidence] = counts.get(r.confidence, 0) + 1
        self.status_var.set(
            f"{len(self.filtered)}/{len(self.rows)} shown   "
            f"H={counts['H']}  L={counts['L']}  C={counts['C']}"
        )

    def _sort_by(self, col):
        reverse = self._sort_reverse.get(col, False)
        self.filtered.sort(key=lambda i: getattr(self.rows[i], col), reverse=reverse)
        self._sort_reverse[col] = not reverse
        self.tree.delete(*self.tree.get_children())
        for i in self.filtered:
            self._insert_row(i)

    # ---- selection / editing ----------------------------------------------

    def _on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        self._load_detail(int(sel[0]))

    def _load_detail(self, idx):
        self.current_idx = idx
        r = self.rows[idx]
        self.edit_char_var.set(r.char)
        self.edit_conf_var.set(r.confidence)
        self.info_var.set(f"Name: {r.name}\nStyle: {r.style}\nCID: {r.cid}")
        self._show_image(r.name, r.style, r.cid)
        self.dirty_var.set("")

    # target on-screen size for the glyph preview: small glyphs get
    # upscaled (crisp, nearest-neighbor) to at least this size; large ones
    # (high-DPI captures can run past 400px) get downscaled to fit.
    _PREVIEW_TARGET = 260
    _PREVIEW_MAX = 300

    def _show_image(self, name, style, cid):
        path = os.path.join(self.glyph_dir, f"{name}_{style}_{cid}.ppm")
        try:
            im = Image.open(path).convert("RGB")
        except (FileNotFoundError, OSError):
            self.image_label.configure(image="", text=f"(missing: {os.path.basename(path)})")
            self.photo = None
            return
        longest = max(im.width, im.height)
        if longest > self._PREVIEW_MAX:
            # large capture (high -r): downscale to fit, smoothly
            factor = self._PREVIEW_MAX / longest
            im2 = im.resize(
                (max(1, int(im.width * factor)), max(1, int(im.height * factor))),
                Image.LANCZOS,
            )
        else:
            # small capture: upscale with nearest-neighbor so individual
            # pixels/dots stay sharp instead of blurring
            scale = max(1, min(12, self._PREVIEW_TARGET // longest))
            im2 = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(im2)
        self.image_label.configure(image=self.photo, text="")

    def _mark_dirty(self):
        if self.current_idx is None:
            return
        r = self.rows[self.current_idx]
        if self.edit_char_var.get() != r.char or self.edit_conf_var.get() != r.confidence:
            self.dirty_var.set("unsaved changes — press Enter/Save")
        else:
            self.dirty_var.set("")

    def _save_current(self):
        if self.current_idx is None:
            return
        r = self.rows[self.current_idx]
        new_char = self.edit_char_var.get()
        new_conf = self.edit_conf_var.get()
        if not new_char:
            messagebox.showerror("Invalid", "Char cannot be empty.")
            return
        if new_conf not in CONF_VALUES:
            messagebox.showerror("Invalid", "Confidence must be H, L, or C.")
            return
        changed = (r.char != new_char) or (r.confidence != new_conf)
        r.char = new_char
        r.confidence = new_conf
        if changed:
            save_rows(self.index_path, self.rows)
        iid = str(self.current_idx)
        if self.tree.exists(iid):
            self.tree.item(
                iid,
                values=(r.name, r.style, r.cid, r.char, r.confidence),
            )
        self.dirty_var.set("")
        self._update_status()

    def _step(self, delta):
        children = self.tree.get_children()
        if not children:
            return
        if self.current_idx is None or str(self.current_idx) not in children:
            new_iid = children[0]
        else:
            pos = children.index(str(self.current_idx))
            pos = max(0, min(len(children) - 1, pos + delta))
            new_iid = children[pos]
        self.tree.selection_set(new_iid)
        self.tree.see(new_iid)

    # ---- Sync from glyph folder ---------------------------------------

    def _parse_glyph_filename(self, fname):
        """Parse <name>_<style>_<cid>.ppm -> (name, style, cid)
        or None if the name doesn't match the expected pattern."""
        if not fname.endswith(".ppm"):
            return None
        stem = fname[:-4]
        parts = stem.split("_")
        if len(parts) < 3:
            return None
        cid = parts[-1]
        style = parts[-2]
        name = "_".join(parts[:-2])
        return (name, style, cid)

    def _run_tesseract(self, png_path, lang):
        """Run tesseract on a single glyph, return (text, conf or 0)."""
        try:
            r = subprocess.run(
                ["tesseract", png_path, "stdout", "-l", lang,
                 "--psm", "10", "hocr"],
                capture_output=True, text=True, timeout=15,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "", 0
        confs = [int(c) for c in re.findall(r"x_wconf (\d+)", r.stdout)]
        texts = re.findall(
            r"<span class='ocrx_word'[^>]*>(.*?)</span>",
            r.stdout, re.DOTALL,
        )
        for t in texts:
            t = re.sub(r"&[^;]+;", "", t).strip()
            if t:
                return t, confs[0] if confs else 0
        return "", 0

    def _ocr_glyph(self, ppm_path):
        """Preprocess the PPM and run tesseract (ara + eng). Return
        (char, conf_letter) where conf_letter is H/L/C."""
        try:
            im = Image.open(ppm_path).convert("RGB")
        except (FileNotFoundError, OSError):
            return "?", "C"
        w, h = im.size
        # upsample 4x with LANCZOS + 30px white border so tesseract has
        # enough pixels to work with on small glyphs
        scale = 4
        border = 30
        out = Image.new(
            "RGB", (w * scale + border * 2, h * scale + border * 2), "white"
        )
        out.paste(
            im.resize((w * scale, h * scale), Image.LANCZOS), (border, border)
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            png_path = tmp.name
        try:
            out.save(png_path, "PNG")
            ara_text, ara_conf = self._run_tesseract(png_path, "ara")
            eng_text, eng_conf = self._run_tesseract(png_path, "eng")
        finally:
            os.unlink(png_path)
        # pick the higher-confidence result
        if eng_conf > ara_conf:
            text, conf = eng_text, eng_conf
        else:
            text, conf = ara_text, ara_conf
        # tesseract on isolated glyphs often returns multi-char garbage;
        # only accept single-char results with conf >= 50
        if conf >= 80 and len(text) == 1:
            return text, "H"
        elif conf >= 50 and len(text) == 1:
            return text, "L"
        else:
            return "?", "C"

    def _sync_from_glyphs(self):
        """Scan the glyph folder, add missing entries to the index,
        running tesseract (ara+eng) to guess the char for each new glyph."""
        all_ppm = [f for f in os.listdir(self.glyph_dir) if f.endswith(".ppm")]
        parsed = []
        for fname in all_ppm:
            p = self._parse_glyph_filename(fname)
            if p:
                parsed.append(p)
        if not parsed:
            messagebox.showinfo("Sync", f"No .ppm glyphs in {self.glyph_dir}")
            return
        existing = {(r.name, r.style, r.cid) for r in self.rows}
        new_glyphs = [p for p in parsed if p not in existing]
        if not new_glyphs:
            messagebox.showinfo(
                "Sync", f"All {len(parsed)} glyphs already in the index."
            )
            return

        # progress popup (keeps the main window responsive while tesseract runs
        # one glyph at a time via root.after)
        popup = tk.Toplevel(self.root)
        popup.title("Syncing glyphs")
        popup.transient(self.root)
        popup.geometry("450x120")
        popup.resizable(False, False)
        msg_var = tk.StringVar(value=f"OCR-ing 0/{len(new_glyphs)} glyphs...")
        ttk.Label(popup, textvariable=msg_var).pack(pady=(10, 4))
        pb = ttk.Progressbar(popup, maximum=len(new_glyphs), mode="determinate")
        pb.pack(fill="x", padx=20, pady=4)
        self._sync_stop = False

        def do_stop():
            self._sync_stop = True

        ttk.Button(popup, text="Stop", command=do_stop).pack(pady=4)
        popup.grab_set()

        added = [0]

        def process_one(i):
            if self._sync_stop or i >= len(new_glyphs):
                save_rows(self.index_path, self.rows)
                self._refresh_list()
                popup.grab_release()
                popup.destroy()
                if self._sync_stop:
                    messagebox.showinfo(
                        "Sync stopped",
                        f"Added {added[0]} of {len(new_glyphs)} glyphs (stopped).",
                    )
                else:
                    messagebox.showinfo(
                        "Sync done",
                        f"Added {added[0]} glyphs from tesseract OCR.",
                    )
                return
            name, style, cid = new_glyphs[i]
            msg_var.set(f"OCR-ing {i+1}/{len(new_glyphs)}: {name}_{style}_{cid}")
            pb["value"] = i
            ppm_path = os.path.join(
                self.glyph_dir, f"{name}_{style}_{cid}.ppm"
            )
            char, conf = self._ocr_glyph(ppm_path)
            self.rows.append(GlyphRow(name, style, cid, char, conf))
            added[0] += 1
            self.root.after(10, process_one, i + 1)

        self.root.after(10, process_one, 0)
def main():
    index_path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INDEX)
    glyph_dir = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_GLYPH_DIR)
    if not os.path.isdir(glyph_dir):
        print(f"Glyph directory not found: {glyph_dir}", file=sys.stderr)
        sys.exit(1)
    # the index file may not exist yet (first run / before "Sync") -- that's
    # fine; the editor starts empty and the Sync button builds it from the
    # glyph folder.

    root = tk.Tk()
    GlyphEditorApp(root, index_path, glyph_dir)
    root.mainloop()


if __name__ == "__main__":
    main()

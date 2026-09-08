#!/usr/bin/env python3
"""
convert_index_to_md5.py -- one-time converter for the glyph database.

Reads the existing 4-column glyph index (font, CID, char, confidence),
computes the MD5 of each referenced .ppm file, splits each font name into a
kebab-case (name, style) pair, dedups by MD5 (visual duplicates -- e.g. the
same letter from a synthetic bold and the regular master -- collapse to one
row and one .ppm), and writes a new 6-column index:

    md5 \t name \t style \t cid \t char \t confidence

Each surviving .ppm is renamed to <name>_<style>_<cid>_<md5>.ppm. The old
index is backed up to <index>.bak (only if no .bak exists yet). Visual-dup
.ppm files are removed (the canonical copy is kept); they are regenerable
by re-running pdftoglyphs at its fixed 900 DPI, which reproduces them
byte-for-byte (see README, pass 1).

This is a one-time bridge from the old format (hand-labelled 4-column index
+ style-suffixed font names) to the MD5-keyed format that pdftoglyphs will
emit natively going forward.

Usage:
    python3 convert_index_to_md5.py [--dry-run] [path/to/gylph_index.db] [path/to/gylph_db]

    --dry-run    compute and report everything, but do not rename/remove .ppm
                 files or rewrite the index (the .bak is not touched either).
Both positional args default to ../data/gylph_index.db and ../data/gylph_db
relative to this script, matching the project layout in README.md.
"""

import os
import sys
import hashlib
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INDEX = os.path.join(HERE, "..", "data", "gylph_index.db")
DEFAULT_GLYPH_DIR = os.path.join(HERE, "..", "data", "gylph_db")

# Style tokens peeled off the END of the font name. Multi-word / longer tokens
# first so "bolditalic" is matched before "bold", "semibold" before "bold".
STYLE_TOKENS = ("bolditalic", "boldoblique", "semibold",
                "bold", "italic", "oblique")
# Separators that may appear before a trailing style token; '' covers names
# like "AL-MohanadBold" (token appended with no separator).
STYLE_SEPS = (",", "-", "")
EMPTY_STYLE = "regular"


def to_kebab(s):
    """lowercase; collapse runs of non-[a-z0-9] to a single '-'; strip ends.

    No CamelCase splitting (TimesNewRoman -> timesnewroman), so the two
    distinct master fonts TimesNewRoman and Times New Roman stay distinct
    as timesnewroman vs times-new-roman."""
    out = []
    for ch in s.lower():
        out.append(ch if (ch.isascii() and ch.isalnum()) else "-")
    s2 = "".join(out)
    while "--" in s2:
        s2 = s2.replace("--", "-")
    return s2.strip("-")


def split_name_style(font):
    """Strip a subset tag (XXXXXX+) if present, peel one trailing style
    token, and return (kebab-name, kebab-style or EMPTY_STYLE). The name is
    only stripped if a non-empty name remains, so a font literally named
    'Bold' is kept whole with style=regular."""
    name = font
    # strip a 'XXXXXX+' Ghostscript subset tag if somehow still present
    if len(name) > 7 and name[6] == "+" and name[:6].isalpha() and name[:6].isupper():
        name = name[7:]

    low = name.lower()
    style = ""
    for sep in STYLE_SEPS:
        for tok in STYLE_TOKENS:
            suffix = sep + tok
            if low.endswith(suffix) and len(name) - len(suffix) > 0:
                name = name[:len(name) - len(suffix)]
                style = tok
                break
        if style:
            break

    kebab_name = to_kebab(name) or "unnamed"
    return kebab_name, (style or EMPTY_STYLE)


def md5_of_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    dry_run = "--dry-run" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--dry-run"]
    index_path = os.path.abspath(argv[0] if len(argv) > 0 else DEFAULT_INDEX)
    glyph_dir = os.path.abspath(argv[1] if len(argv) > 1 else DEFAULT_GLYPH_DIR)

    if not os.path.isfile(index_path):
        print(f"Index not found: {index_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isdir(glyph_dir):
        print(f"Glyph dir not found: {glyph_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"index:   {index_path}")
    print(f"glyphs:  {glyph_dir}")
    print(f"dry-run: {dry_run}")

    # --- 1. read old 4-column index ---
    rows = []
    with open(index_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                print(f"warn: {index_path}:{lineno}: expected 4 fields, got "
                      f"{len(parts)}: {line!r} -- skipped", file=sys.stderr)
                continue
            rows.append(parts)  # [font, cid, char, conf]
    print(f"old index rows read: {len(rows)}")

    # --- 2. find each .ppm, compute md5, split name/style ---
    # tuple: (md5, name, style, cid, char, conf, old_ppm_path)
    enriched = []
    missing = []
    for font, cid, char, conf in rows:
        old_ppm = os.path.join(glyph_dir, f"{font}_{cid}.ppm")
        if not os.path.isfile(old_ppm):
            missing.append((font, cid, char, conf))
            continue
        enriched.append((md5_of_file(old_ppm), *split_name_style(font),
                         cid, char, conf, old_ppm))
    print(f"rows with .ppm: {len(enriched)}; rows missing .ppm: {len(missing)}")
    for font, cid, char, conf in missing:
        print(f"  missing (skipped): {font}_{cid}.ppm  (char={char!r} conf={conf})",
              file=sys.stderr)

    # --- 3. dedup by md5 (first-seen wins) ---
    by_md5 = {}          # md5 -> [name, style, cid, char, conf, old_ppm]
    conflicts = []       # (md5, dup_file, kept_char, dup_char)
    for md5, name, style, cid, char, conf, old_ppm in enriched:
        if md5 in by_md5:
            kept_char = by_md5[md5][3]
            if kept_char != char:
                conflicts.append((md5, os.path.basename(old_ppm),
                                  kept_char, char))
        else:
            by_md5[md5] = [name, style, cid, char, conf, old_ppm]
    dups = len(enriched) - len(by_md5)
    print(f"unique md5s: {len(by_md5)}; visual duplicates collapsed: {dups}")
    if conflicts:
        print(f"CONFLICTS (same glyph labelled with different chars): "
              f"{len(conflicts)}", file=sys.stderr)
        for md5, dup_file, kept, dup in conflicts:
            print(f"  md5 {md5}: kept char={kept!r}, dup {dup_file} had "
                  f"char={dup!r}", file=sys.stderr)

    # --- 4. rename canonical .ppm files; remove visual-dup originals ---
    survivor_old = {rec[5] for rec in by_md5.values()}
    renamed = 0
    rename_errors = []
    deleted_dups = 0
    for md5, rec in by_md5.items():
        name, style, cid = rec[0], rec[1], rec[2]
        old_ppm = rec[5]
        new_ppm = os.path.join(glyph_dir, f"{name}_{style}_{cid}_{md5}.ppm")
        if dry_run:
            renamed += 1
            continue
        try:
            os.rename(old_ppm, new_ppm)
            renamed += 1
        except OSError as e:
            rename_errors.append((old_ppm, new_ppm, str(e)))
    if not dry_run:
        for md5, name, style, cid, char, conf, old_ppm in enriched:
            if old_ppm not in survivor_old:
                try:
                    if os.path.isfile(old_ppm):
                        os.remove(old_ppm)
                        deleted_dups += 1
                except OSError as e:
                    print(f"warn: could not remove dup {old_ppm}: {e}",
                          file=sys.stderr)
    print(f".ppm renamed (canonical): {renamed}; "
          f"visual-dup .ppm removed: {deleted_dups}")
    if rename_errors:
        print(f"RENAME ERRORS: {len(rename_errors)}", file=sys.stderr)
        for o, n, e in rename_errors:
            print(f"  {o} -> {n}: {e}", file=sys.stderr)

    # --- 5. write new 6-column index; back up old first ---
    if not dry_run:
        bak = index_path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(index_path, bak)
            print(f"backed up old index to {bak}")
        tmp = index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for md5, rec in by_md5.items():
                name, style, cid = rec[0], rec[1], rec[2]
                char, conf = rec[3], rec[4]
                f.write(f"{md5}\t{name}\t{style}\t{cid}\t{char}\t{conf}\n")
        os.replace(tmp, index_path)
        print(f"wrote new index: {index_path} ({len(by_md5)} rows)")
    else:
        print(f"[dry-run] would write new index: {index_path} "
              f"({len(by_md5)} rows)")

    print("done.")


if __name__ == "__main__":
    main()


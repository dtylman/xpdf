#!/usr/bin/env python3
"""
pretty_sicil.py -- pretty-print / clean pdftotext -tablecells JSON.

Consumes the JSON emitted by `xpdf/pdftotext -tablecells` (the pass-2
extractor of this fork; see ../README) and renders it for humans or for
further analysis:

  --format ascii  (default)  terminal view: paragraphs as labeled blocks,
                             tables as aligned ASCII grids.  Cell/paragraph
                             text is printed AS-IS, i.e. in xpdf's visual
                             order with its U+202A/U+202B/U+202C bidi
                             embedding marks -- exactly the form a
                             terminal expects, so mixed Arabic/Latin lines
                             display like the source page.

  --format md                 Markdown: pages as sections, paragraphs by
                             type, tables as MD tables.  Text is converted
                             to Unicode logical order with the bidi marks
                             stripped (browsers/MD viewers run the bidi
                             algorithm themselves), so it is also safe to
                             copy/paste/search.

  --format json               the same document, cleaned: identical schema
                             but every text field in logical order without
                             bidi marks.  This is the analysis-ready form.
                             (Multiple input files are emitted as NDJSON.)

The visual->logical handling comes in two flavors (--bidi):

  strip (default)   just remove the bidi control marks, keep the text
                    order as-is.  This is the RIGHT choice for the sicil
                    PDFs this fork targets: Ghostscript pdfwrite drew
                    their glyphs in visual left-to-right order, so
                    xpdf's line order is already visual, and
                    encodeFragment's re-reversal brought it back to true
                    logical order -- the raw JSON text (marks aside) is
                    already in reading order.

  invert            fully invert encodeFragment (un-reverse the runs).
                    This is the theoretically-correct inverse for
                    well-formed PDFs, where xpdf's line order is true
                    logical order and the emitted stream is visual
                    order.  Using it on the sicil JSONs re-reverses the
                    Arabic words into garbage ("مقر" instead of "رقم").

Known limitation (both modes): the source PDFs draw paren/bracket GLYPH
shapes in visual order, so their logical open/close identity is
ambiguous; a bidi renderer may place them slightly differently than the
original page looks.

Usage:
    pretty_sicil.py data/out/24_Sicil_no.031.json
    pretty_sicil.py data/out/24_Sicil_no.031.json --pages 1-10 --format md
    pretty_sicil.py data/out/24_Sicil_no.031.json --format json -o clean.json
    pretty_sicil.py --selftest

Stdlib only.
"""

import argparse
import json
import sys
import textwrap
import unicodedata

# Unicode bidi control characters.
LRE = '\u202a'          # LEFT-TO-RIGHT EMBEDDING
RLE = '\u202b'          # RIGHT-TO-LEFT EMBEDDING
PDF = '\u202c'          # POP DIRECTIONAL FORMATTING
BIDI_MARKS = set('\u200e\u200f'                # LRM, RLM
                 '\u202a\u202b\u202c\u202d\u202e'    # LRE RLE PDF LRO RLO
                 '\u2066\u2067\u2068\u2069')   # LRI RLI FSI PDI


def strip_bidi_marks(text):
    """Remove all bidi control characters from <text>."""
    return ''.join(c for c in text if c not in BIDI_MARKS)


# ---- visual order -> logical order (inverse of encodeFragment) ----------

def _find_close(chars, i):
    """<chars[i-1]> was an opening LRE/RLE; return the index of its
    matching PDF, skipping nested LRE/RLE..PDF pairs.  If unbalanced,
    returns len(chars)."""
    depth = 0
    n = len(chars)
    while i < n:
        c = chars[i]
        if c == LRE or c == RLE:
            depth += 1
        elif c == PDF:
            if depth == 0:
                return i
            depth -= 1
        i += 1
    return n


def _parse_runs(chars):
    """Split a line into depth-0 items:
         ('plain', [chars])   unwrapped text
         ('rle',   [items])   content of an RLE..PDF pair (nested items)
         ('lre',   [chars])   content of an LRE..PDF pair
    Stray PDF marks (and any other bidi marks in plain runs are dropped
    later) are handled defensively."""
    items = []
    buf = []
    i = 0
    n = len(chars)
    while i < n:
        c = chars[i]
        if c == RLE:
            if buf:
                items.append(('plain', buf))
                buf = []
            j = _find_close(chars, i + 1)
            items.append(('rle', _parse_runs(chars[i + 1:j])))
            i = j + 1
        elif c == LRE:
            if buf:
                items.append(('plain', buf))
                buf = []
            j = _find_close(chars, i + 1)
            items.append(('lre', chars[i + 1:j]))
            i = j + 1
        elif c == PDF:            # stray close; drop it
            i += 1
        else:
            buf.append(c)
            i += 1
    if buf:
        items.append(('plain', buf))
    return items


def _clean_plain(chars):
    return [c for c in chars if c not in BIDI_MARKS]


def _render_rle(items):
    """Invert an RLE-wrapped region.  xpdf emitted (a) LTR-primary lines:
    a single reversed run, or (b) RTL-primary lines: the run order
    reversed, each RTL run itself reversed, LTR islands forward inside
    LRE..PDF.  Both invert with the same rule: walk the sections in
    reverse order, un-reverse plain sections, keep LRE sections forward."""
    out = []
    for kind, content in reversed(items):
        if kind == 'plain':
            out.extend(reversed(content))
        elif kind == 'lre':
            out.extend(_clean_plain(content))
        else:                     # unexpected deeper nesting; recurse
            out.extend(_render_rle(content))
    return out


def _render_runs(items):
    out = []
    for kind, content in items:
        if kind == 'plain':
            out.extend(_clean_plain(content))
        elif kind == 'lre':
            out.extend(_clean_plain(content))
        else:
            out.extend(_render_rle(content))
    return out


def to_logical(text):
    """Fully invert encodeFragment: un-reverse the marked runs back into
    xpdf's line order, dropping the marks.  Correct for well-formed
    PDFs (xpdf line order == logical order); WRONG for the sicil PDFs,
    whose glyphs were drawn in visual order -- see --bidi."""
    lines = text.split('\n')
    return '\n'.join(''.join(_render_runs(_parse_runs(list(line))))
                     for line in lines)


def clean_text(text, mode):
    """Apply the requested --bidi strategy to a text field."""
    if mode == 'strip':
        return strip_bidi_marks(text)
    return to_logical(text)

# ---- selftest ----------------------------------------------------------

def _bidi_cls(ch):
    """Approximate xpdf's unicodeTypeR/L/Num classification."""
    b = unicodedata.bidirectional(ch)
    if b in ('R', 'AL'):
        return 'R'
    if b == 'L':
        return 'L'
    if b in ('EN', 'AN'):
        return 'Num'
    return None


def _encode_like_xpdf(line, primary_lr):
    """Python port of xpdf's TextPage::encodeFragment() (the UTF-8 branch),
    used by the selftest to verify that to_logical() is its exact
    inverse."""
    text = list(line)
    n = len(text)
    out = []
    if primary_lr:
        i = 0
        while i < n:
            j = i
            while j < n and _bidi_cls(text[j]) != 'R':
                j += 1
            out.extend(text[i:j])
            i = j
            j = i
            while j < n and _bidi_cls(text[j]) not in ('L', 'Num'):
                j += 1
            if j > i:
                out.append(RLE)
                out.extend(reversed(text[i:j]))
                out.append(PDF)
                i = j
    else:
        out.append(RLE)
        i = n - 1
        while i >= 0:
            j = i
            while j >= 0 and _bidi_cls(text[j]) not in ('L', 'Num'):
                j -= 1
            out.extend(text[k] for k in range(i, j, -1))
            i = j
            j = i
            while j >= 0 and _bidi_cls(text[j]) != 'R':
                j -= 1
            if j < i:
                out.append(LRE)
                out.extend(text[k] for k in range(j + 1, i + 1))
                out.append(PDF)
                i = j
        out.append(PDF)
    return ''.join(out)


def run_selftest():
    samples = [
        'plain english text',
        '',
        'سجل رقم',
        'سجل رقم (٣١)',
        'abc سجل رقم 123 def',
        'mixed مقتطف test (42) نهاية',
        'number ٣١ inside',
        'trailing neutral).',
        '(٣١) رقم سجل',
    ]
    n = 0
    for primary_lr in (True, False):
        for s in samples:
            enc = _encode_like_xpdf(s, primary_lr)
            got = to_logical(enc)
            if got != s:
                print('SELFTEST FAILED (primary_lr=%s):\n  in : %r\n  enc: %r\n'
                      '  out: %r' % (primary_lr, s, enc, got), file=sys.stderr)
                return False
            n += 1
    # mark-free text must pass through unchanged
    if to_logical('hello\nworld\n') != 'hello\nworld\n':
        print('SELFTEST FAILED: identity case', file=sys.stderr)
        return False
    # a real line from 24_Sicil_no.031 page 1: marks must be gone
    real = ('\u202b)سجل رقم \u202a(\u0663\u0661\u202c\u202c\n'
            '\n \u202b\u202a24\u202c\u202c')
    out = to_logical(real)
    if set(out) & BIDI_MARKS:
        print('SELFTEST FAILED: marks remain in %r' % out, file=sys.stderr)
        return False
    print('selftest OK (%d round-trip cases)' % n)
    return True


# ---- small helpers ------------------------------------------------------

def parse_pages(spec):
    """'3' / '1-5' / '1,3,5-7' -> predicate over page numbers."""
    def in_range(tok):
        if '-' in tok:
            a, b = tok.split('-', 1)
            return int(a), int(b)
        v = int(tok)
        return v, v
    ranges = [in_range(tok) for tok in spec.split(',') if tok.strip()]
    return lambda p: any(a <= p <= b for a, b in ranges)


def fmt_bbox(bbox):
    return '[' + ', '.join(str(v) for v in bbox) + ']'


def fmt_fonts(fonts):
    return ', '.join('%s/%s' % (f['name'], f['style']) for f in fonts)

# ---- ascii writer -------------------------------------------------------

def _cell_lines(text, width):
    """Wrap a cell's text (printed as-is, visual order) to <width>."""
    lines = []
    for raw in text.split('\n'):
        if not raw.strip():
            lines.append('')
        else:
            lines.extend(textwrap.wrap(raw, width=width,
                                       break_long_words=True,
                                       break_on_hyphens=False) or [''])
    return lines or ['']


def ascii_table(table, out, show_fonts, wrap):
    rows = table.get('rows') or []
    grid = []
    maxcol = 0
    for r in rows:
        cells = {c['col']: c for c in r.get('cells', [])}
        if cells:
            maxcol = max(maxcol, max(cells))
        grid.append((r.get('row', 0), cells))
    if maxcol < 1:
        return

    # column 0 holds the row number
    widths = [max(3, len('row'),
                  max([len(str(rn)) for rn, _ in grid] or [0]))]
    for i in range(1, maxcol + 1):
        w = len(str(i))
        for _, cells in grid:
            c = cells.get(i)
            if c and c.get('text'):
                w = max(w, max(len(l) for l in c['text'].split('\n')))
        widths.append(min(max(w, 3), wrap))

    sep = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'

    def emit(col_lines):
        height = max(len(v) for v in col_lines)
        for k in range(height):
            parts = [(v[k] if k < len(v) else '').ljust(widths[i])
                     for i, v in enumerate(col_lines)]
            print('| ' + ' | '.join(parts) + ' |', file=out)
        print(sep, file=out)

    print(sep, file=out)
    emit([[h] for h in ['row'] + [str(i) for i in range(1, maxcol + 1)]])
    for rn, cells in grid:
        col_lines = [[str(rn)]]
        for i in range(1, maxcol + 1):
            c = cells.get(i)
            col_lines.append(_cell_lines(c['text'], widths[i])
                             if c and c.get('text') else [''])
        emit(col_lines)
    if show_fonts:
        for rn, cells in grid:
            for i in sorted(cells):
                c = cells[i]
                if c.get('text') and c.get('fonts'):
                    print('  [row %s, col %d] fonts: %s'
                          % (rn, i, fmt_fonts(c['fonts'])), file=out)


def write_ascii(doc, out, show_fonts, wrap):
    for page in doc:
        print('', file=out)
        print('== page %s  (%s x %s) ==' % (page.get('page'),
                                           page.get('width'),
                                           page.get('height')), file=out)
        for p in page.get('paragraphs', []):
            print('', file=out)
            if p['type'] == 'table':
                print('[table]  rows %d  bbox %s'
                      % (len(p.get('rows') or []), fmt_bbox(p['bbox'])),
                      file=out)
                ascii_table(p, out, show_fonts, wrap)
            else:
                print('[%s]  bbox %s' % (p['type'], fmt_bbox(p['bbox'])),
                      file=out)
                for line in p.get('text', '').split('\n'):
                    print('    ' + line, file=out)
                if show_fonts and p.get('fonts'):
                    print('    fonts: %s' % fmt_fonts(p['fonts']), file=out)

# ---- markdown writer ----------------------------------------------------

def _md_cell(text, bidi):
    return (clean_text(text, bidi).replace('|', '\\|')
            .replace('\n', '<br>'))


def write_md(doc, out, show_fonts, bidi):
    for page in doc:
        print('', file=out)
        print('## page %s (%s x %s)' % (page.get('page'), page.get('width'),
                                        page.get('height')), file=out)
        for p in page.get('paragraphs', []):
            print('', file=out)
            if p['type'] == 'table':
                grid = [(r.get('row', 0),
                         {c['col']: c for c in r.get('cells', [])})
                        for r in (p.get('rows') or [])]
                maxcol = max([max(c) for _, c in grid if c] or [0])
                if maxcol < 1:
                    continue
                print('**table** (bbox %s)' % fmt_bbox(p['bbox']), file=out)
                print('', file=out)
                print('| row | ' +
                      ' | '.join(str(i) for i in range(1, maxcol + 1)) +
                      ' |', file=out)
                print('|' + '|'.join(['---'] * (maxcol + 1)) + '|',
                      file=out)
                for rn, cells in grid:
                    print('| %s | ' % rn +
                          ' | '.join(_md_cell(cells[i]['text'], bidi)
                                     if i in cells and cells[i].get('text')
                                     else ' '
                                     for i in range(1, maxcol + 1)) + ' |',
                          file=out)
                if show_fonts:
                    notes = []
                    for rn, cells in grid:
                        for i in sorted(cells):
                            c = cells[i]
                            if c.get('text') and c.get('fonts'):
                                notes.append('row %s col %d: %s'
                                             % (rn, i, fmt_fonts(c['fonts'])))
                    if notes:
                        print('', file=out)
                        for nt in notes:
                            print('- fonts %s' % nt, file=out)
            else:
                print('**%s** (bbox %s)' % (p['type'],
                                            fmt_bbox(p['bbox'])), file=out)
                print('', file=out)
                print(clean_text(p.get('text', ''), bidi), file=out)
                if show_fonts and p.get('fonts'):
                    print('', file=out)
                    print('*fonts: %s*' % fmt_fonts(p['fonts']), file=out)

# ---- json cleaner -------------------------------------------------------

def clean_document(doc, bidi):
    """Same schema, every text field cleaned per the --bidi strategy."""
    pages = []
    for page in doc:
        paras = []
        for p in page.get('paragraphs', []):
            q = dict(p)
            if p['type'] == 'table':
                rows = []
                for r in p.get('rows', []):
                    r2 = dict(r)
                    r2['cells'] = [dict(c, text=clean_text(c.get('text', ''),
                                                           bidi))
                                   for c in r.get('cells', [])]
                    rows.append(r2)
                q['rows'] = rows
            else:
                q['text'] = clean_text(p.get('text', ''), bidi)
            paras.append(q)
        page2 = dict(page)
        page2['paragraphs'] = paras
        pages.append(page2)
    return pages


# ---- main ---------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description='Pretty-print pdftotext -tablecells JSON '
                    '(ascii / md / cleaned json).')
    ap.add_argument('files', nargs='*',
                    help='JSON file(s) from `pdftotext -tablecells`')
    ap.add_argument('--pages',
                    help='page filter, e.g. 3 or 1-5 or 1,3,5-7')
    ap.add_argument('--format', choices=('ascii', 'md', 'json'),
                    default='ascii',
                    help='ascii: terminal view (text as-is, visual order '
                         'with bidi marks); md: markdown; json: same '
                         'document, text cleaned.  For md/json the text '
                         'is cleaned according to --bidi (marks always '
                         'removed)')
    ap.add_argument('--bidi', choices=('strip', 'invert'), default='strip',
                    help='how md/json text is cleaned: "strip" just '
                         'removes the bidi marks keeping the text order '
                         '(correct for these Ghostscript sicil PDFs, '
                         'whose glyphs were drawn in visual order so the '
                         'raw text is already in reading order); '
                         '"invert" additionally un-reverses the marked '
                         'runs (the exact inverse of xpdf\'s '
                         'encodeFragment, correct for well-formed PDFs)')
    ap.add_argument('-o', '--output',
                    help='write here instead of stdout')
    ap.add_argument('--fonts', action='store_true',
                    help='annotate paragraphs/cells with their fonts '
                         '(useful for tracing wrong chars back to '
                         'gylph_index.db)')
    ap.add_argument('--wrap', type=int, default=40,
                    help='max ascii table cell width (default 40)')
    ap.add_argument('--selftest', action='store_true',
                    help='verify the visual->logical inversion and exit')
    args = ap.parse_args(argv)

    if args.selftest:
        return 0 if run_selftest() else 1
    if not args.files:
        ap.error('no input file(s) given (or use --selftest)')

    pred = parse_pages(args.pages) if args.pages else None
    out = (open(args.output, 'w', encoding='utf-8')
           if args.output else sys.stdout)
    try:
        for path in args.files:
            with open(path, encoding='utf-8') as f:
                doc = json.load(f)
            if pred:
                doc = [p for p in doc if pred(p.get('page'))]
            if args.format == 'json':
                cleaned = clean_document(doc, args.bidi)
                if len(args.files) == 1:
                    json.dump(cleaned, out, ensure_ascii=False, indent=2)
                    print(file=out)
                else:            # several files -> NDJSON, one doc per line
                    print(json.dumps(cleaned, ensure_ascii=False), file=out)
            elif args.format == 'md':
                if len(args.files) > 1:
                    print('# %s' % path, file=out)
                write_md(doc, out, args.fonts, args.bidi)
            else:
                if len(args.files) > 1:
                    print('== %s ==' % path, file=out)
                write_ascii(doc, out, args.fonts, args.wrap)
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())





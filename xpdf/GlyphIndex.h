//========================================================================
//
// GlyphIndex.h
//
// An in-memory copy of data/gylph_index.db -- the hand-corrected
// font/style/CID -> UTF-8 text table built in pass 1 (pdftoglyphs +
// glyph_editor).  TableOutputDev instantiates this class so the text
// it extracts (garbled by broken embedded /ToUnicode CMaps) can be
// translated to the correct text.
//
// The db is a UTF-8, tab-separated file with one row per glyph:
//
//     <font> \t <style> \t <cid-hex> \t <text> \t <confidence>
//
// e.g. "al-mohanad\tbold\t004A\tb\tC" (with <text> in real Arabic).
// <font> is the font name with the Ghostscript subset tag stripped
// (as computed by GlyphDbOutputDev in pass 1), <style> is one of
// regular/bold/italic/oblique/semibold/boldoblique/bolditalic,
// <cid-hex> is the CID in hex (e.g. "004A"), <text> is the corrected
// text -- one or more Unicode characters in UTF-8, since ligature
// glyphs can map to several letters -- and <confidence> is H (high),
// L (low) or C (confirmed by a human via glyph_editor).  The
// confidence column is only advisory metadata for the editor, so it
// is not kept in memory; only <font>/<style>/<cid> -> <text> is.
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#ifndef GLYPHINDEX_H
#define GLYPHINDEX_H

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma interface
#endif

#include <map>
#include <string>
#include "gtypes.h"

// Default location of the glyph index db, relative to the directory
// pdftotext is run from (the documented usage runs it from the repo
// root, where data/ lives).
#define GLYPH_INDEX_DEFAULT_DB "data/gylph_index.db"

//------------------------------------------------------------------------
// GlyphIndex
//------------------------------------------------------------------------

class GlyphIndex {
public:

  GlyphIndex();
  ~GlyphIndex();

  // Load the CID -> Unicode correction table into memory.  <fileName>
  // may be NULL (or empty) to use the default, GLYPH_INDEX_DEFAULT_DB.
  // Returns gTrue on success.  On failure (file missing, unreadable) a
  // warning is printed and the index is left empty, so translation
  // would just pass text through unchanged rather than crash.
  GBool load(const char *fileName = NULL);

  GBool isLoaded() { return loaded; }
  int getNumEntries() { return numEntries; }

  // Look up the corrected UTF-8 text for a given font/style/CID.
  // Returns NULL if there is no entry for that key.
  const char *lookup(const char *fontName, const char *style, int cid) const;

private:

  // "font\tstyle" -> (CID -> corrected UTF-8 text)
  std::map<std::string, std::map<int, std::string> > index;

  GBool loaded;
  int numEntries;
};

#endif

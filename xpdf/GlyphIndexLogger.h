//========================================================================
//
// GlyphIndexLogger.h
//
// A debugging aid for the glyph index (data/gylph_index.db): a side
// log written next to TableOutputDev's output file (same path and
// base name, with the extension replaced by ".log") that records, for
// every line of output text, the text as emitted, the char codes
// (CIDs) of the glyphs in it, and the font names involved.  Comparing
// the log against the output -- and against the db rows for those
// font/CID keys -- makes it possible to find wrong or missing entries
// in the index db.
//
// The log is always generated (no flag); it is only disabled when the
// output itself goes to stdout, where there is no output path to
// derive a log file name from.
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#ifndef GLYPHINDEXLOGGER_H
#define GLYPHINDEXLOGGER_H

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma interface
#endif

#include <cstdio>
#include <set>
#include <string>
#include <vector>
#include "gtypes.h"

//------------------------------------------------------------------------
// GlyphIndexLogger
//------------------------------------------------------------------------

class GlyphIndexLogger {
public:

  // Open the log file: <outputFileName> with its extension replaced
  // by ".log" (e.g. "out/foo.json" -> "out/foo.log").  If
  // <outputFileName> is NULL or "-" (stdout output), or the log file
  // can't be opened, logging is disabled and log() is a no-op.
  GlyphIndexLogger(const char *outputFileName);

  // Flush any accumulated-but-unfinished line and close the log file.
  ~GlyphIndexLogger();

  // Record one character handed to TextPage::addChar(): <text> is the
  // UTF-8 text as it is emitted to the output, <cid> the char code of
  // the glyph, <fontName> the normalized font name (as used for the
  // index db lookup), and <y> the glyph's baseline position.  The
  // characters are accumulated until the baseline moves (a new line);
  // the finished line is then written to the log as:
  //   1. the line's text,
  //   2. the line's array of char codes (hex, as in the db),
  //   3. the font names seen in the line (in no particular order).
  void log(const char *text, int cid, const char *fontName, double y);

private:

  // Write the accumulated line to the log file and reset the
  // accumulator.
  void flushLine();

  FILE *logFile;                    // NULL if logging is disabled

  std::string lineText;             // UTF-8 text of the line so far
  std::vector<int> lineCids;        // char codes of the line, in order
  std::set<std::string> lineFonts;  // unique font names in the line

  double lastY;                     // baseline of the line so far
  GBool haveLastY;                  // false until the first character
};

#endif

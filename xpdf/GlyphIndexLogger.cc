//========================================================================
//
// GlyphIndexLogger.cc
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma implementation
#endif

#include <cmath>
#include <cstdio>
#include <cstring>
#include "gtypes.h"
#include "GlyphIndexLogger.h"

// Glyphs whose baselines differ by more than this (in PDF user space)
// are considered to be on different lines.
static const double lineChangeTolerance = 0.01;

//------------------------------------------------------------------------

GlyphIndexLogger::GlyphIndexLogger(const char *outputFileName) {
  std::string logName;
  size_t slashPos, dotPos;

  logFile = NULL;
  lastY = 0;
  haveLastY = gFalse;

  // With the output going to stdout there is no path to derive a log
  // file name from -- logging is disabled in that case.
  if (!outputFileName || !outputFileName[0] ||
      !strcmp(outputFileName, "-")) {
    return;
  }

  // Same path and base name as the output file, with the extension
  // (if any) replaced by ".log": "out/foo.json" -> "out/foo.log",
  // "out/foo" -> "out/foo.log".
  logName = outputFileName;
  slashPos = logName.find_last_of('/');
  dotPos = logName.find_last_of('.');
  if (dotPos != std::string::npos &&
      (slashPos == std::string::npos || dotPos > slashPos)) {
    logName.resize(dotPos);
  }
  logName += ".log";

  if (!(logFile = fopen(logName.c_str(), "wb"))) {
    fprintf(stderr, "GlyphIndexLogger: couldn't open %s -- glyph index logging disabled\n",
	    logName.c_str());
  }
}

GlyphIndexLogger::~GlyphIndexLogger() {
  if (logFile) {
    // the last line of the document is never followed by a baseline
    // change, so flush whatever is still accumulated
    flushLine();
    fclose(logFile);
    logFile = NULL;
  }
}

void GlyphIndexLogger::log(const char *text, int cid, const char *fontName,
			   double y) {
  if (!logFile) {
    return;
  }

  // a baseline change means the previous line is finished
  if (haveLastY && fabs(y - lastY) > lineChangeTolerance) {
    flushLine();
  }

  if (text) {
    lineText += text;
  }
  lineCids.push_back(cid);
  if (fontName && fontName[0]) {
    lineFonts.insert(fontName);
  }
  lastY = y;
  haveLastY = gTrue;
}

void GlyphIndexLogger::flushLine() {
  std::set<std::string>::const_iterator it;

  if (lineText.empty() && lineCids.empty()) {
    return;
  }

  // 1. the text, exactly as it was emitted to the output
  fprintf(logFile, "TEXT: %s\n", lineText.c_str());

  // 2. the char codes, in output order, formatted like the db's CID
  // column (4-digit hex)
  fprintf(logFile, "CHAR-CODES: [");
  for (size_t i = 0; i < lineCids.size(); ++i) {
    fprintf(logFile, "%s%04X", i > 0 ? ", " : "", lineCids[i]);
  }
  fprintf(logFile, "]\n");

  // 3. the font names seen in this line (a set, so order is
  // arbitrary)
  fprintf(logFile, "FONTS:");
  for (it = lineFonts.begin(); it != lineFonts.end(); ++it) {
    fprintf(logFile, " %s", it->c_str());
  }
  fprintf(logFile, "\n\n");

  // flush after every line so the log stays usable even if extraction
  // dies mid-document
  fflush(logFile);

  lineText.clear();
  lineCids.clear();
  lineFonts.clear();
}

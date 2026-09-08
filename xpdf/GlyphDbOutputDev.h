//========================================================================
//
// GlyphDbOutputDev.h
//
// A SplashOutputDev subclass that captures one clean, isolated bitmap
// per unique (font, CID) glyph seen while rendering a document, for
// hand-labelling CID->Unicode correction tables against fonts whose
// embedded ToUnicode CMap is wrong (see README.md). It performs no
// page output of its own -- it exists purely to drive drawChar() over
// every page.
//
// Part of the Sicil-reader fork of xpdf.
//
//========================================================================

#ifndef GLYPHDBOUTPUTDEV_H
#define GLYPHDBOUTPUTDEV_H

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma interface
#endif

#include <set>
#include <string>
#include "SplashOutputDev.h"

struct SplashGlyphBitmap;
class GfxFont;

//------------------------------------------------------------------------
// GlyphDbOutputDev
//------------------------------------------------------------------------

class GlyphDbOutputDev: public SplashOutputDev {
public:

  // <outDirA> is the directory glyph bitmaps are written into; it must
  // already exist.
  GlyphDbOutputDev(char *outDirA);

  virtual ~GlyphDbOutputDev();

  virtual void drawChar(GfxState *state, double x, double y,
			double dx, double dy,
			double originX, double originY,
			CharCode c, int nBytes, Unicode *u, int uLen);

  // Number of distinct (font, CID) glyphs captured so far.
  int getNumCaptured() { return (int)seen.size(); }

  // Returns true if any glyph file could not be created, so the caller
  // can fail the whole run with a non-zero exit code instead of
  // silently finishing with exit 0.
  GBool getHadWriteError() { return hadWriteError; }

private:

  // "<strippedFontName>_<CIDhex>", used both as the dedup key and (with
  // ".ppm" appended) as the output filename.
  std::string makeKey(GfxFont *font, CharCode c);

  void writeGlyphPPM(const std::string &key, SplashGlyphBitmap *glyph);

  std::string outDir;
  std::set<std::string> seen;
  GBool hadWriteError;
};

#endif

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

  // "<strippedFontName>_<CIDhex>": the raw (font,CID) key used to skip
  // re-rasterizing the same glyph on every page it appears on.
  std::string makeKey(GfxFont *font, CharCode c);

  // lowercase kebab: collapse non-[a-z0-9] to '-', strip ends.  No
  // CamelCase split, so distinct master fonts stay distinct
  // (TimesNewRoman -> timesnewroman vs "Times New Roman" ->
  // times-new-roman).
  static std::string toKebab(const std::string &s);

  // strip a 'XXXXXX+' subset tag, peel one trailing style token, and
  // return (kebab name, style).  Empty style becomes "regular".
  static void splitNameStyle(const std::string &font,
			     std::string &name, std::string &style);

  // Write the glyph as <name>_<style>_<cid>.ppm.  Overwrites if it exists
  // (a re-run or a different PDF with the same (font, CID) simply
  // overwrites -- the bitmap is the same glyph at 900 DPI except for
  // cosmetic sub-pixel variance).  Logs "created"; does NOT touch the
  // index (the .ppm folder is the source of truth, the index is derived
  // from it; see glyph_editor).
  void writeGlyphPPM(const std::string &name, const std::string &style,
		     const std::string &cidHex,
		     const SplashGlyphBitmap *glyph);

  std::string outDir;
  std::set<std::string> seen;  // raw (font,CID) -> avoid re-rasterizing
                               // the same glyph on every page it appears on
  GBool hadWriteError;
};

#endif

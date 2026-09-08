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

  // Build the full PPM (header + white margins + glyph rows) into <buf>.
  // The bytes are identical to the old file writer's output, so the md5
  // of <buf> equals the on-disk .ppm md5.  Returns gFalse for a
  // degenerate glyph (nothing to write).
  static GBool buildPpmBuffer(const SplashGlyphBitmap *glyph,
			      std::string &buf);

  // hex-stringify the MD5 of <bytes> -> 32 lower-hex chars.  Uses xpdf's
  // own md5() (Decrypt.h) -- no new dependency.
  static std::string md5Hex(const std::string &bytes);

  // lowercase kebab: collapse non-[a-z0-9] to '-', strip ends.  No
  // CamelCase split, so distinct master fonts stay distinct
  // (TimesNewRoman -> timesnewroman vs "Times New Roman" ->
  // times-new-roman).
  static std::string toKebab(const std::string &s);

  // strip a 'XXXXXX+' subset tag, peel one trailing style token, and
  // return (kebab name, style).  Empty style becomes "regular".
  static void splitNameStyle(const std::string &font,
			     std::string &name, std::string &style);

  // md5-keyed dedup: build the ppm, md5 it, write the .ppm only for a
  // genuinely new md5 (named <name>_<style>_<cid>_<md5>.ppm), and append
  // a row to the index.  Logs "created" / "duplicate" per request.
  void writeGlyphPPM(const std::string &name, const std::string &style,
		     const std::string &cidHex,
		     const SplashGlyphBitmap *glyph);

  // read <outDir>/gylph_index.db (if present) and seed seenMd5 with its
  // md5s, so a re-run over the same PDF rewrites nothing.  If the index
  // is the old 4-column format, refuse (set hadWriteError) and tell the
  // user to run glyph_editor/convert_index_to_md5.py first, so
  // hand-labels are never silently lost.
  void loadExistingIndex();

  // append a brand-new row (md5,name,style,cid,?,C) to the index file.
  void appendIndexRow(const std::string &md5, const std::string &name,
		      const std::string &style, const std::string &cidHex);

  std::string outDir;
  std::string indexPath;
  std::set<std::string> seen;      // raw (font,CID) -> avoid re-raster
  std::set<std::string> seenMd5;   // ppm-image md5 -> visual dedup
  GBool hadWriteError;
  FILE *indexFile;   // append handle for gylph_index.db (or NULL)
};

#endif

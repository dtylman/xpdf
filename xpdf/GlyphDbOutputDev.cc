//========================================================================
//
// GlyphDbOutputDev.cc
//
// Part of the Sicil-reader fork of xpdf.
//
//========================================================================

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma implementation
#endif

#include <cstdio>
#include <cstring>
#include <vector>
#include "gmem.h"
#include "GString.h"
#include "GfxFont.h"
#include "GfxState.h"
#include "SplashFont.h"
#include "SplashGlyphBitmap.h"
#include "GlyphDbOutputDev.h"

// White border, in pixels, added around each captured glyph so ink
// never touches the image edge.
static const int glyphMargin = 3;

static SplashColor whitePaper = { 0xff, 0xff, 0xff };

//------------------------------------------------------------------------

GlyphDbOutputDev::GlyphDbOutputDev(char *outDirA):
  SplashOutputDev(splashModeRGB8, 1, gFalse, whitePaper)
{
  outDir = outDirA;
}

GlyphDbOutputDev::~GlyphDbOutputDev() {
}

// Ghostscript (and most other subsetting tools) prefix a subsetted
// font's PostScript name with a random 6-uppercase-letter "subset
// tag" followed by '+' (PDF32000 section 9.6.4). Stripping it means
// the same master font gets the same key across different documents
// that happen to embed different subsets of it (see README.md).
static GBool looksLikeSubsetTag(const std::string &name) {
  if (name.size() <= 7 || name[6] != '+') {
    return gFalse;
  }
  for (int i = 0; i < 6; ++i) {
    if (name[i] < 'A' || name[i] > 'Z') {
      return gFalse;
    }
  }
  return gTrue;
}

std::string GlyphDbOutputDev::makeKey(GfxFont *gfxFont, CharCode c) {
  std::string name;
  GString *gname = gfxFont->getName();
  if (gname && gname->getLength() > 0) {
    name = gname->getCString();
  } else {
    Ref *id = gfxFont->getID();
    char buf[64];
    snprintf(buf, sizeof(buf), "unnamed-%d-%d", id->num, id->gen);
    name = buf;
  }

  if (looksLikeSubsetTag(name)) {
    name = name.substr(7);
  }

  // filenames are friendlier without commas (e.g. "Foo,Bold")
  for (size_t i = 0; i < name.size(); ++i) {
    if (name[i] == ',' || name[i] == '/' || name[i] == '\\') {
      name[i] = '-';
    }
  }

  char hex[8];
  snprintf(hex, sizeof(hex), "%04X", (unsigned)(c & 0xffff));
  return name + "_" + hex;
}

void GlyphDbOutputDev::writeGlyphPPM(const std::string &key,
				     SplashGlyphBitmap *glyph) {
  std::string path = outDir + "/" + key + ".ppm";
  FILE *f = fopen(path.c_str(), "wb");
  if (!f) {
    return;
  }

  int w = glyph->w + 2 * glyphMargin;
  int h = glyph->h + 2 * glyphMargin;
  fprintf(f, "P6\n%d %d\n255\n", w, h);

  std::vector<unsigned char> blankRow(w * 3, 0xff);
  std::vector<unsigned char> row(w * 3);
  int rowBytes = (glyph->w + 7) / 8; // only used when !glyph->aa

  for (int i = 0; i < glyphMargin; ++i) {
    fwrite(blankRow.data(), 1, blankRow.size(), f);
  }
  for (int y = 0; y < glyph->h; ++y) {
    row = blankRow;
    for (int x = 0; x < glyph->w; ++x) {
      unsigned char ink;
      if (glyph->aa) {
	// 8-bit alpha: 0 = no ink, 255 = full ink
	unsigned char a = glyph->data[y * glyph->w + x];
	ink = (unsigned char)(255 - a);
      } else {
	// 1 bit per pixel, packed MSB-first, byte-aligned per row
	unsigned char byte = glyph->data[y * rowBytes + x / 8];
	GBool set = (byte >> (7 - (x % 8))) & 1;
	ink = set ? 0 : 255;
      }
      row[(glyphMargin + x) * 3 + 0] = ink;
      row[(glyphMargin + x) * 3 + 1] = ink;
      row[(glyphMargin + x) * 3 + 2] = ink;
    }
    fwrite(row.data(), 1, row.size(), f);
  }
  for (int i = 0; i < glyphMargin; ++i) {
    fwrite(blankRow.data(), 1, blankRow.size(), f);
  }

  fclose(f);
}

void GlyphDbOutputDev::drawChar(GfxState *state, double x, double y,
				double dx, double dy,
				double originX, double originY,
				CharCode c, int nBytes,
				Unicode *u, int uLen) {
  // Let the normal Splash renderer resolve/cache the current font and
  // paint the glyph onto the (never written out) page bitmap. This is
  // wasted rendering work, but it means font resolution -- embedded
  // vs. substituted, CID-to-GID mapping, matrix setup, etc. -- exactly
  // matches real rendering, with none of that delicate logic
  // duplicated here.
  SplashOutputDev::drawChar(state, x, y, dx, dy, originX, originY,
			    c, nBytes, u, uLen);

  GfxFont *gfxFont = state->getFont();
  if (!gfxFont) {
    return;
  }

  std::string key = makeKey(gfxFont, c);
  if (seen.find(key) != seen.end()) {
    return;
  }
  seen.insert(key);

  SplashFont *splashFont = getCurrentFont();
  if (!splashFont) {
    // e.g. Type3 font, or the font failed to load -- nothing to
    // rasterize
    return;
  }

  SplashGlyphBitmap glyph;
  if (!splashFont->getGlyph((int)c, 0, 0, &glyph)) {
    return;
  }
  if (glyph.w > 0 && glyph.h > 0 && glyph.data) {
    writeGlyphPPM(key, &glyph);
  }
  if (glyph.freeData) {
    gfree(glyph.data);
  }
}

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
#include <cctype>
#include <cstring>
#include <string>
#include <vector>
#include "gmem.h"
#include "GString.h"
#include "GlobalParams.h"
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
  hadWriteError = gFalse;
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

std::string GlyphDbOutputDev::toKebab(const std::string &s) {
  std::string out;
  out.reserve(s.size());
  for (size_t i = 0; i < s.size(); ++i) {
    unsigned char ch = (unsigned char)s[i];
    if (isalnum(ch) && ch < 0x80) {
      out.push_back((char)tolower(ch));
    } else {
      out.push_back('-');
    }
  }
  // collapse runs of '-'
  std::string out2;
  out2.reserve(out.size());
  GBool prevDash = gFalse;
  for (size_t i = 0; i < out.size(); ++i) {
    if (out[i] == '-') {
      if (!prevDash) {
	out2.push_back('-');
      }
      prevDash = gTrue;
    } else {
      out2.push_back(out[i]);
      prevDash = gFalse;
    }
  }
  // strip leading/trailing '-'
  size_t a = 0, b = out2.size();
  while (a < b && out2[a] == '-') {
    ++a;
  }
  while (b > a && out2[b - 1] == '-') {
    --b;
  }
  return out2.substr(a, b - a);
}

void GlyphDbOutputDev::splitNameStyle(const std::string &font,
				      std::string &name,
				      std::string &style) {
  static const char *styleTokens[] = {
    "bolditalic", "boldoblique", "semibold",
    "bold", "italic", "oblique"
  };
  static const char *styleSeps[] = { ",", "-", "" };

  std::string n = font;
  // strip a 'XXXXXX+' subset tag if present
  if (n.size() > 7 && n[6] == '+') {
    GBool isSubset = gTrue;
    for (int i = 0; i < 6; ++i) {
      if (!isupper((unsigned char)n[i])) {
	isSubset = gFalse;
	break;
      }
    }
    if (isSubset) {
      n = n.substr(7);
    }
  }

  // lowercase copy for trailing-suffix matching
  std::string low = n;
  for (size_t i = 0; i < low.size(); ++i) {
    low[i] = (char)tolower((unsigned char)low[i]);
  }

  style.clear();
  GBool peeled = gFalse;
  for (int si = 0; si < 3 && !peeled; ++si) {
    for (int ti = 0; ti < 6 && !peeled; ++ti) {
      std::string suffix = std::string(styleSeps[si]) + styleTokens[ti];
      size_t sl = suffix.size();
      if (low.size() > sl &&
	  low.compare(low.size() - sl, sl, suffix) == 0) {
	n.erase(n.size() - sl);
	style = styleTokens[ti];
	peeled = gTrue;
      }
    }
  }

  name = toKebab(n);
  if (name.empty()) {
    name = "unnamed";
  }
  if (style.empty()) {
    style = "regular";
  }
}

void GlyphDbOutputDev::writeGlyphPPM(const std::string &name,
				     const std::string &style,
				     const std::string &cidHex,
				     const SplashGlyphBitmap *glyph) {
  std::string path = outDir + "/" + name + "_" + style + "_" + cidHex + ".ppm";
  FILE *f = fopen(path.c_str(), "wb");
  if (!f) {
    if (!globalParams || !globalParams->getErrQuiet()) {
      fprintf(stderr, "pdftoglyphs: couldn't create %s\n", path.c_str());
    }
    hadWriteError = gTrue;
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
  if (!globalParams || !globalParams->getErrQuiet()) {
    fprintf(stderr, "pdftoglyphs: created %s\n", path.c_str());
  }
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

  if (hadWriteError) {
    // a .ppm couldn't be created (e.g. the output dir doesn't exist);
    // keep doing nothing rather than logging the error again.
    return;
  }

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
    // name/style from the raw font name (subset tag stripped + style
    // token peeled); cid as upper-hex for the filename.
    std::string fontName;
    GString *gname = gfxFont->getName();
    if (gname && gname->getLength() > 0) {
      fontName = gname->getCString();
    } else {
      Ref *id = gfxFont->getID();
      char buf[64];
      snprintf(buf, sizeof(buf), "unnamed-%d-%d", id->num, id->gen);
      fontName = buf;
    }
    std::string name, style;
    splitNameStyle(fontName, name, style);
    char cidHex[8];
    snprintf(cidHex, sizeof(cidHex), "%04X", (unsigned)(c & 0xffff));
    writeGlyphPPM(name, style, cidHex, &glyph);
  }
  if (glyph.freeData) {
    gfree(glyph.data);
  }
}

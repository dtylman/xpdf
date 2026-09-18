//========================================================================
//
// GlyphIndex.cc
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma implementation
#endif

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "gtypes.h"
#include "GlyphIndex.h"

//------------------------------------------------------------------------

GlyphIndex::GlyphIndex() {
  loaded = gFalse;
  numEntries = 0;
}

GlyphIndex::~GlyphIndex() {
}

GBool GlyphIndex::load(const char *fileName) {
  FILE *f;
  char line[1024];
  char *fields[5], *p, *end;
  int len, lineNum, nFields;
  unsigned long cid;

  index.clear();
  numEntries = 0;
  loaded = gFalse;

  if (!fileName || !fileName[0]) {
    fileName = GLYPH_INDEX_DEFAULT_DB;
  }
  if (!(f = fopen(fileName, "rb"))) {
    fprintf(stderr, "GlyphIndex: couldn't open %s -- text translation disabled\n",
	    fileName);
    return gFalse;
  }

  lineNum = 0;
  while (fgets(line, sizeof(line), f)) {
    ++lineNum;

    // strip trailing newline / CR
    len = (int)strlen(line);
    while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) {
      line[--len] = '\0';
    }
    if (len == 0) {
      continue;
    }

    // the db has exactly 5 tab-separated fields:
    // font, style, cid(hex), text, confidence
    nFields = 1;
    for (p = line; *p; ++p) {
      if (*p == '\t') {
	++nFields;
      }
    }
    if (nFields != 5) {
      fprintf(stderr, "GlyphIndex: %s:%d: expected 5 tab-separated fields, skipping\n",
	      fileName, lineNum);
      continue;
    }
    fields[0] = line;
    nFields = 1;
    for (p = line; *p; ++p) {
      if (*p == '\t') {
	*p = '\0';
	fields[nFields++] = p + 1;
      }
    }

    // parse the CID (hex)
    cid = strtoul(fields[2], &end, 16);
    if (fields[2][0] == '\0' || *end != '\0' || cid > 0xffff) {
      fprintf(stderr, "GlyphIndex: %s:%d: bad CID \"%s\", skipping\n",
	      fileName, lineNum, fields[2]);
      continue;
    }

    index[std::string(fields[0]) + "\t" + fields[1]][(int)cid] =
        std::string(fields[3]);
    ++numEntries;
  }
  fclose(f);

  loaded = gTrue;
  return gTrue;
}

const char *GlyphIndex::lookup(const char *fontName, const char *style,
			       int cid) const {
  std::map<std::string, std::map<int, std::string> >::const_iterator it;
  std::map<int, std::string>::const_iterator it2;

  it = index.find(std::string(fontName) + "\t" + style);
  if (it == index.end()) {
    return NULL;
  }
  it2 = it->second.find(cid);
  if (it2 == it->second.end()) {
    return NULL;
  }
  return it2->second.c_str();
}

//------------------------------------------------------------------------

std::string GlyphIndex::toKebab(const std::string &s) {
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

void GlyphIndex::splitNameStyle(const std::string &font,
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

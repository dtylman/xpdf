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

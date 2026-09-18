//========================================================================
//
// TableOutputDev.cc
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma implementation
#endif

#include <algorithm>
#include <cmath>
#include <cstring>
#include "gmem.h"
#include "GlyphIndex.h"
#include "GString.h"
#include "GfxState.h"
#include "TableOutputDev.h"

// Fills/strokes thinner than this (in points) are treated as table
// ruling lines rather than shaded boxes.
static const double ruleThickness = 3.0;

// Coordinates within this many points of each other are considered
// the same grid line (handles rounding / near-miss rules).
static const double snapTolerance = 2.0;

//------------------------------------------------------------------------

TableOutputDev::TableOutputDev(char *fileName, TextOutputControl *controlA):
  TextOutputDev(NULL, controlA, gFalse)
{
  // Load the CID -> Unicode correction table (data/gylph_index.db) so
  // the text GStrings we emit can be translated from ToUnicode-garbled
  // to correct text.  A missing/unreadable db is not fatal -- load()
  // warns and translation is simply disabled.
  glyphIndex = new GlyphIndex();
  glyphIndex->load();

  tblOk = gTrue;
  curPageNum = 0;
  pageW = pageH = 0;
  havePages = gFalse;
  inPage = gFalse;
  needParagraphComma = gFalse;
  tableRows = NULL;
  tableHasRows = gFalse;
  tblXMin = tblYMin = tblXMax = tblYMax = 0;
  rowCells = NULL;
  rowHasCells = gFalse;
  curRowNum = 0;
  rowXMin = rowYMin = rowXMax = rowYMax = 0;
  if (fileName) {
    if (!strcmp(fileName, "-")) {
      outFile = stdout;
    } else if (!(outFile = fopen(fileName, "wb"))) {
      tblOk = gFalse;
    }
  } else {
    outFile = stdout;
  }
  if (outFile) {
    fprintf(outFile, "[\n");
  }
}

TableOutputDev::~TableOutputDev() {
  // Defensive: if we're destroyed mid-page (error path), close any
  // dangling structures and the page/document arrays so the output is
  // still parseable JSON.
  if (tableRows) {
    endTable();
  }
  if (inPage && outFile) {
    fprintf(outFile, "\n    ]\n  }");
  }
  if (havePages && outFile) {
    fprintf(outFile, "\n]\n");
  }
  if (outFile && outFile != stdout) {
    fclose(outFile);
  }
  delete glyphIndex;
}

void TableOutputDev::startPage(int pageNum, GfxState *state) {
  TextOutputDev::startPage(pageNum, state);
  curPageNum = pageNum;
  hLines.clear();
  vLines.clear();
  if (state) {
    pageW = state->getPageWidth();
    pageH = state->getPageHeight();
  } else {
    pageW = pageH = 0;
  }
}

void TableOutputDev::addHSegment(double x0, double x1, double y) {
  Segment seg;
  if (x0 > x1) {
    std::swap(x0, x1);
  }
  seg.a0 = x0;
  seg.a1 = x1;
  seg.pos = y;
  hLines.push_back(seg);
}

void TableOutputDev::addVSegment(double y0, double y1, double x) {
  Segment seg;
  if (y0 > y1) {
    std::swap(y0, y1);
  }
  seg.a0 = y0;
  seg.a1 = y1;
  seg.pos = x;
  vLines.push_back(seg);
}

// Shared corner-detection logic for stroke()/fill(): recognizes a
// 2-point straight line or a 5-point (closed) axis-aligned rectangle
// in the current path, in device space, and records it as a ruling
// segment if it's thin enough to be a rule rather than a shaded area.
void TableOutputDev::captureRulingsFromPath(GfxState *state) {
  GfxPath *path;
  GfxSubpath *subpath;
  double x[5], y[5];
  int i;

  path = state->getPath();
  if (path->getNumSubpaths() != 1) {
    return;
  }
  subpath = path->getSubpath(0);

  // 2-point open path: a stroked line
  if (subpath->getNumPoints() == 2) {
    state->transform(subpath->getX(0), subpath->getY(0), &x[0], &y[0]);
    state->transform(subpath->getX(1), subpath->getY(1), &x[1], &y[1]);
    if (y[0] == y[1] && x[0] != x[1]) {
      addHSegment(x[0], x[1], y[0]);
    } else if (x[0] == x[1] && y[0] != y[1]) {
      addVSegment(y[0], y[1], x[0]);
    }
    return;
  }

  // 5-point closed path: a filled rectangle
  if (subpath->getNumPoints() != 5) {
    return;
  }
  for (i = 0; i < 5; ++i) {
    if (subpath->getCurve(i)) {
      return;
    }
    state->transform(subpath->getX(i), subpath->getY(i), &x[i], &y[i]);
  }
  double rx0, ry0, rx1, ry1;
  if (x[0] == x[1] && y[1] == y[2] && x[2] == x[3] && y[3] == y[4] &&
      x[0] == x[4] && y[0] == y[4]) {
    rx0 = x[0]; ry0 = y[0]; rx1 = x[2]; ry1 = y[1];
  } else if (y[0] == y[1] && x[1] == x[2] && y[2] == y[3] && x[3] == x[4] &&
	     x[0] == x[4] && y[0] == y[4]) {
    rx0 = x[0]; ry0 = y[0]; rx1 = x[1]; ry1 = y[2];
  } else {
    return;
  }
  if (rx0 > rx1) { std::swap(rx0, rx1); }
  if (ry0 > ry1) { std::swap(ry0, ry1); }
  double w = rx1 - rx0, h = ry1 - ry0;
  if (h <= ruleThickness && w > h) {
    // wide, thin rectangle -> horizontal rule
    addHSegment(rx0, rx1, (ry0 + ry1) / 2);
  } else if (w <= ruleThickness && h > w) {
    // tall, thin rectangle -> vertical rule
    addVSegment(ry0, ry1, (rx0 + rx1) / 2);
  }
  // otherwise: a filled box too big to be a rule (e.g., shaded cell
  // background) -- ignored for now.
}

void TableOutputDev::stroke(GfxState *state) {
  captureRulingsFromPath(state);
}

void TableOutputDev::fill(GfxState *state) {
  captureRulingsFromPath(state);
}

void TableOutputDev::eoFill(GfxState *state) {
  captureRulingsFromPath(state);
}

// Cluster a set of coordinates into a sorted list of unique grid
// line positions, merging values within <tol> of each other.
std::vector<double> TableOutputDev::clusterCoords(std::vector<double> &coords,
						   double tol) {
  std::vector<double> out;
  if (coords.empty()) {
    return out;
  }
  std::sort(coords.begin(), coords.end());
  double sum = coords[0];
  int n = 1;
  for (size_t i = 1; i < coords.size(); ++i) {
    if (coords[i] - coords[i-1] <= tol) {
      sum += coords[i];
      ++n;
    } else {
      out.push_back(sum / n);
      sum = coords[i];
      n = 1;
    }
  }
  out.push_back(sum / n);
  return out;
}

// Find the left/right extent of the horizontal rule(s) bounding a row
// band, for use as a fallback single-cell width when no vertical rule
// crosses that row.
void TableOutputDev::rowXExtent(double rowY0, double rowY1,
				 double *xMin, double *xMax) {
  double lo = pageW, hi = 0;
  GBool found = gFalse;
  for (size_t i = 0; i < hLines.size(); ++i) {
    if (fabs(hLines[i].pos - rowY0) <= snapTolerance ||
	fabs(hLines[i].pos - rowY1) <= snapTolerance) {
      if (hLines[i].a0 < lo) { lo = hLines[i].a0; }
      if (hLines[i].a1 > hi) { hi = hLines[i].a1; }
      found = gTrue;
    }
  }
  if (found) {
    *xMin = lo;
    *xMax = hi;
  } else {
    *xMin = 0;
    *xMax = pageW;
  }
}

// Append a number the way the sample JSON does it: at most two
// decimals, with trailing zeros stripped except the last one, so 612
// prints as "612.0" and 200.25 as "200.25".
static void appendNum(GString *s, double v) {
  char buf[64];
  int len;

  snprintf(buf, sizeof(buf), "%.2f", v);
  len = (int)strlen(buf);
  while (len > 2 && buf[len-1] == '0' && buf[len-2] != '.') {
    --len;
  }
  s->append(buf, len);
}

GString *TableOutputDev::formatBBox(double xMin, double yMin,
				    double xMax, double yMax) {
  GString *s = new GString("[");

  appendNum(s, xMin);
  s->append(", ");
  appendNum(s, yMin);
  s->append(", ");
  appendNum(s, xMax);
  s->append(", ");
  appendNum(s, yMax);
  s->append("]");
  return s;
}

// Escape a byte string for use inside a JSON string literal.  The text
// is expected to be UTF-8 (pdftotext forces UTF-8 for -tablecells), so
// bytes >= 0x80 are passed through unchanged.
GString *TableOutputDev::escapeJSONString(const char *s, int len) {
  GString *out = new GString();
  char buf[8];
  int i;

  for (i = 0; i < len; ++i) {
    unsigned char c = (unsigned char)s[i];
    switch (c) {
    case '"':  out->append("\\\""); break;
    case '\\': out->append("\\\\"); break;
    case '\b': out->append("\\b");  break;
    case '\f': out->append("\\f");  break;
    case '\n': out->append("\\n");  break;
    case '\r': out->append("\\r");  break;
    case '\t': out->append("\\t");  break;
    default:
      if (c < 0x20) {
	snprintf(buf, sizeof(buf), "\\u%04x", c);
	out->append(buf);
      } else {
	out->append((char)c);
      }
      break;
    }
  }
  return out;
}

// Pull the text inside the given page rect (in reading order) and
// write it as a paragraph object of the given type.  Regions with no
// text produce nothing at all, so blank bands don't clutter the JSON.
void TableOutputDev::writeTextParagraph(TextPage *tp, const char *type,
					double xMin, double yMin,
					double xMax, double yMax) {
  GString *s, *esc, *bbox;
  int len;

  if (xMax <= xMin || yMax <= yMin) {
    return;
  }
  s = tp->getText(xMin, yMin, xMax, yMax);
  if (!s) {
    return;
  }
  // trim trailing whitespace/EOL so blank regions produce nothing
  len = s->getLength();
  while (len > 0 && (s->getChar(len-1) == '\n' || s->getChar(len-1) == '\r' ||
		     s->getChar(len-1) == ' ')) {
    --len;
  }
  if (len > 0) {
    if (needParagraphComma) {
      fprintf(outFile, ",\n");
    }
    needParagraphComma = gTrue;
    esc = escapeJSONString(s->getCString(), len);
    bbox = formatBBox(xMin, yMin, xMax, yMax);
    fprintf(outFile,
	    "      {\n"
	    "        \"type\": \"%s\",\n"
	    "        \"text\": \"%s\",\n"
	    "        \"bbox\": %s\n"
	    "      }",
	    type, esc->getCString(), bbox->getCString());
    delete esc;
    delete bbox;
  }
  delete s;
}

void TableOutputDev::beginTable() {
  tableRows = new GString();
  tableHasRows = gFalse;
}

// Close out the open table: its rows were buffered in tableRows so the
// table's own bbox could be written before them.
void TableOutputDev::endTable() {
  GString *bbox;

  if (!tableRows) {
    return;
  }
  if (tableHasRows) {
    if (needParagraphComma) {
      fprintf(outFile, ",\n");
    }
    needParagraphComma = gTrue;
    bbox = formatBBox(tblXMin, tblYMin, tblXMax, tblYMax);
    fprintf(outFile,
	    "      {\n"
	    "        \"type\": \"table\",\n"
	    "        \"bbox\": %s,\n"
	    "        \"rows\": [\n%s\n        ]\n"
	    "      }",
	    bbox->getCString(), tableRows->getCString());
    delete bbox;
  }
  delete tableRows;
  tableRows = NULL;
  tableHasRows = gFalse;
}

void TableOutputDev::beginRow(int rowNum, double xMin, double yMin,
			      double xMax, double yMax) {
  rowCells = new GString();
  rowHasCells = gFalse;
  curRowNum = rowNum;
  rowXMin = xMin;
  rowYMin = yMin;
  rowXMax = xMax;
  rowYMax = yMax;
}

void TableOutputDev::endRow() {
  GString *bbox;

  if (!rowCells) {
    return;
  }
  if (rowHasCells && tableRows) {
    if (tableHasRows) {
      tableRows->append(",\n");
    }
    tableHasRows = gTrue;
    bbox = formatBBox(rowXMin, rowYMin, rowXMax, rowYMax);
    tableRows->append("          {\n");
    tableRows->appendf("            \"type\": \"row\",\n"
		       "            \"row\": {0:d},\n"
		       "            \"bbox\": {1:t},\n"
		       "            \"cells\": [\n", curRowNum, bbox);
    tableRows->append(rowCells);
    tableRows->append("\n            ]\n          }");
    delete bbox;
  }
  delete rowCells;
  rowCells = NULL;
  rowHasCells = gFalse;
}

// Emit one table cell.  Unlike the non-table paragraphs, an empty cell
// is still emitted (with an empty "text") so that the column structure
// of the grid survives in the JSON.
void TableOutputDev::writeCell(TextPage *tp, int colNum,
			       double xMin, double yMin,
			       double xMax, double yMax) {
  GString *s, *esc, *bbox;
  int len;

  if (!rowCells || xMax <= xMin || yMax <= yMin) {
    return;
  }
  len = 0;
  s = tp->getText(xMin, yMin, xMax, yMax);
  if (s) {
    len = s->getLength();
    while (len > 0 && (s->getChar(len-1) == '\n' || s->getChar(len-1) == '\r' ||
		       s->getChar(len-1) == ' ')) {
      --len;
    }
  }
  if (rowHasCells) {
    rowCells->append(",\n");
  }
  rowHasCells = gTrue;
  esc = s ? escapeJSONString(s->getCString(), len) : new GString();
  bbox = formatBBox(xMin, yMin, xMax, yMax);
  rowCells->append("              {\n");
  rowCells->appendf("                \"type\": \"cell\",\n"
		    "                \"col\": {0:d},\n"
		    "                \"text\": \"{1:t}\",\n"
		    "                \"bbox\": {2:t}\n"
		    "              }", colNum, esc, bbox);
  delete esc;
  delete bbox;
  delete s;
}

void TableOutputDev::endPage() {
  TextPage *tp = takeText();

  if (havePages) {
    fprintf(outFile, ",\n");
  }
  havePages = gTrue;
  inPage = gTrue;
  needParagraphComma = gFalse;
  fprintf(outFile,
	  "  {\n"
	  "    \"page\": %d,\n",
	  curPageNum);
  if (pageW > 0 && pageH > 0) {
    GString *dims = new GString();
    dims->append("    \"width\": ");
    appendNum(dims, pageW);
    dims->append(",\n    \"height\": ");
    appendNum(dims, pageH);
    dims->append(",\n");
    fwrite(dims->getCString(), 1, dims->getLength(), outFile);
    delete dims;
  }
  fprintf(outFile, "    \"paragraphs\": [\n");

  // gather candidate grid line coordinates: a horizontal rule only
  // counts if it spans a reasonable width, likewise for vertical
  // Row boundaries are global (clustering every horizontal rule's y
  // position): a page-wide notion of "row" is fine even when several
  // independent tables are stacked on one page, since their row bands
  // don't overlap in y.
  std::vector<double> ys;
  for (size_t i = 0; i < hLines.size(); ++i) {
    ys.push_back(hLines[i].pos);
  }
  std::vector<double> rowBounds = clusterCoords(ys, snapTolerance);

  if (rowBounds.size() < 2) {
    // no usable grid on this page -- treat the whole page as one text
    // paragraph
    writeTextParagraph(tp, "text", 0, 0, pageW, pageH);
  } else {
    writeTextParagraph(tp, "header", 0, 0, pageW, rowBounds.front());

    int nBands = (int)rowBounds.size() - 1;
    int tableRow = 0; // current row number within the table currently
                       // open; 0 means no table is open, so the next
                       // grid row starts a fresh table at Row 1
    for (int band = 0; band < nBands; ++band) {
      double rowY0 = rowBounds[band], rowY1 = rowBounds[band+1];
      double rowH = rowY1 - rowY0;

      // Column boundaries are local to this row band: only vertical
      // rules that actually span (part of) this row can divide it.
      // This is what lets several independently-laid-out tables share
      // one page without their column grids bleeding into each other.
      // Requiring the rule to cover most of the band's height (not
      // just graze it) filters out a neighboring table's own border
      // bleeding a point or two into the gap between two tables.
      std::vector<double> xs;
      for (size_t i = 0; i < vLines.size(); ++i) {
	double ov0 = std::max(vLines[i].a0, rowY0);
	double ov1 = std::min(vLines[i].a1, rowY1);
	if (ov1 - ov0 >= 0.5 * rowH) {
	  xs.push_back(vLines[i].pos);
	}
      }
      std::vector<double> colBounds = clusterCoords(xs, snapTolerance);

      if (colBounds.size() < 2) {
	// No vertical rule substantially crosses this band, so it isn't
	// a ruled table row at all -- it's free text sitting between
	// (or around) tables, e.g. a caption introducing the next
	// table. Emit it as a plain text paragraph and close out the
	// current table, so the next real grid row starts a fresh table
	// numbered from row 1.
	if (tableRow > 0) {
	  endTable();
	}
	double xMin, xMax;
	rowXExtent(rowY0, rowY1, &xMin, &xMax);
	writeTextParagraph(tp, "text", xMin, rowY0, xMax, rowY1);
	tableRow = 0;
      } else {
	if (tableRow == 0) {
	  beginTable();
	  tblXMin = colBounds.front();
	  tblXMax = colBounds.back();
	  tblYMin = rowY0;
	  tblYMax = rowY1;
	} else {
	  tblXMin = std::min(tblXMin, colBounds.front());
	  tblXMax = std::max(tblXMax, colBounds.back());
	  tblYMin = std::min(tblYMin, rowY0);
	  tblYMax = std::max(tblYMax, rowY1);
	}
	++tableRow;
	beginRow(tableRow, colBounds.front(), rowY0, colBounds.back(), rowY1);
	int nCols = (int)colBounds.size() - 1;
	for (int c = 0; c < nCols; ++c) {
	  writeCell(tp, c + 1,
		    colBounds[c], rowY0,
		    colBounds[c+1], rowY1);
	}
	endRow();
      }
    }
    if (tableRow > 0) {
      endTable();
    }

    writeTextParagraph(tp, "footnotes", 0, rowBounds.back(), pageW, pageH);
  }

  fprintf(outFile, "\n    ]\n  }");
  inPage = gFalse;
  fflush(outFile);

  delete tp;
}

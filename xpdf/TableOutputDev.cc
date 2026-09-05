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
#include "gmem.h"
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
  tblOk = gTrue;
  curPageNum = 0;
  pageW = pageH = 0;
  if (fileName) {
    if (!(outFile = fopen(fileName, "wb"))) {
      tblOk = gFalse;
    }
  } else {
    outFile = stdout;
  }
}

TableOutputDev::~TableOutputDev() {
  if (outFile && outFile != stdout) {
    fclose(outFile);
  }
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

void TableOutputDev::emitRegion(TextPage *tp, const char *label,
				 double xMin, double yMin,
				 double xMax, double yMax) {
  if (xMax <= xMin || yMax <= yMin) {
    return;
  }
  GString *s = tp->getText(xMin, yMin, xMax, yMax);
  if (s) {
    // trim trailing whitespace/EOL so blank regions produce nothing
    int len = s->getLength();
    while (len > 0 && (s->getChar(len-1) == '\n' || s->getChar(len-1) == '\r' ||
			s->getChar(len-1) == ' ')) {
      --len;
    }
    if (len > 0) {
      fprintf(outFile, "%s ", label);
      fwrite(s->getCString(), 1, len, outFile);
      fprintf(outFile, "\n");
    }
    delete s;
  }
}

void TableOutputDev::endPage() {
  TextPage *tp = takeText();

  fprintf(outFile, "Page %d:\n", curPageNum);

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
    // no usable grid on this page -- treat the whole page as one cell
    emitRegion(tp, "Text:", 0, 0, pageW, pageH);
  } else {
    emitRegion(tp, "Header:", 0, 0, pageW, rowBounds.front());

    int nRows = (int)rowBounds.size() - 1;
    for (int r = 0; r < nRows; ++r) {
      double rowY0 = rowBounds[r], rowY1 = rowBounds[r+1];

      // Column boundaries are local to this row band: only vertical
      // rules that actually span (part of) this row can divide it.
      // This is what lets several independently-laid-out tables share
      // one page without their column grids bleeding into each other.
      std::vector<double> xs;
      for (size_t i = 0; i < vLines.size(); ++i) {
	if (vLines[i].a0 <= rowY1 + snapTolerance &&
	    vLines[i].a1 >= rowY0 - snapTolerance) {
	  xs.push_back(vLines[i].pos);
	}
      }
      std::vector<double> colBounds = clusterCoords(xs, snapTolerance);

      if (colBounds.size() < 2) {
	// no vertical rule crosses this row -- one full-width cell
	double xMin, xMax;
	rowXExtent(rowY0, rowY1, &xMin, &xMax);
	char label[64];
	snprintf(label, sizeof(label), "Row: %d Col: 1:", r + 1);
	emitRegion(tp, label, xMin, rowY0, xMax, rowY1);
      } else {
	int nCols = (int)colBounds.size() - 1;
	for (int c = 0; c < nCols; ++c) {
	  char label[64];
	  snprintf(label, sizeof(label), "Row: %d Col: %d:", r + 1, c + 1);
	  emitRegion(tp, label,
		     colBounds[c], rowY0,
		     colBounds[c+1], rowY1);
	}
      }
    }

    emitRegion(tp, "Footnotes:", 0, rowBounds.back(), pageW, pageH);
  }

  fprintf(outFile, "\n");
  fflush(outFile);

  delete tp;
}

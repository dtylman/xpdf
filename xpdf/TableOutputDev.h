//========================================================================
//
// TableOutputDev.h
//
// A TextOutputDev subclass that recovers table-cell structure from
// ruled tables (grid lines drawn as thin fills or strokes) and emits
// text grouped by "Row: r Col: c" instead of free-flowing reading
// order.  Text above the table is emitted as a page header, text below
// as footnotes.  Pages with no detected grid fall back to a single
// full-page "cell".
//
// This is part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#ifndef TABLEOUTPUTDEV_H
#define TABLEOUTPUTDEV_H

#include <aconf.h>

#ifdef USE_GCC_PRAGMAS
#pragma interface
#endif

#include <vector>
#include <cstdio>
#include "TextOutputDev.h"

class GfxState;

//------------------------------------------------------------------------
// TableOutputDev
//------------------------------------------------------------------------

class TableOutputDev: public TextOutputDev {
public:

  // Open a table-aware text output file.
  TableOutputDev(char *fileName, TextOutputControl *controlA);

  virtual ~TableOutputDev();

  virtual GBool isOk() { return tblOk; }

  //----- initialization and control
  virtual void startPage(int pageNum, GfxState *state);
  virtual void endPage();

  //----- path painting (grid-line capture)
  virtual void stroke(GfxState *state);
  virtual void fill(GfxState *state);
  virtual void eoFill(GfxState *state);

private:

  struct Segment {
    double a0, a1;  // extent along the line's own axis (x for hLines, y for vLines)
    double pos;     // position along the perpendicular axis (y for hLines, x for vLines)
  };

  void captureRulingsFromPath(GfxState *state);
  void addHSegment(double x0, double x1, double y);
  void addVSegment(double y0, double y1, double x);

  std::vector<double> clusterCoords(std::vector<double> &coords, double tol);
  void rowXExtent(double rowY0, double rowY1, double *xMin, double *xMax);
  void emitRegion(TextPage *tp, const char *label,
		   double xMin, double yMin, double xMax, double yMax);

  FILE *outFile;
  GBool tblOk;
  int curPageNum;
  double pageW, pageH;

  std::vector<Segment> hLines;  // horizontal ruling segments, current page
  std::vector<Segment> vLines;  // vertical ruling segments, current page
};

#endif

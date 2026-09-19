//========================================================================
//
// TableOutputDev.h
//
// A TextOutputDev subclass that recovers table-cell structure from
// ruled tables (grid lines drawn as thin fills or strokes) and emits
// JSON instead of free-flowing reading-order text: one object per
// page, holding a list of paragraphs of type "header", "text",
// "footnotes" or "table".  A "table" paragraph holds rows, and each
// row holds "cell" paragraphs.  Pages with no detected grid fall back
// to a single full-page "text" paragraph.
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

#include <string>
#include <vector>
#include <cstdio>
#include "TextOutputDev.h"

class GfxState;
class GlyphIndex;
class GlyphIndexLogger;

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

  //----- text drawing (glyph-index translation)

  // Look the glyph up in the glyph index (data/gylph_index.db); on a
  // hit, replace the (ToUnicode-garbled) Unicode from the PDF with the
  // corrected text via TextPage::addChar().  One glyph can map to
  // more than one character (ligatures).  On a miss, fall through to
  // the base class implementation.
  virtual void drawChar(GfxState *state, double x, double y,
			double dx, double dy,
			double originX, double originY,
			CharCode c, int nBytes, Unicode *u, int uLen);

private:

  struct Segment {
    double a0, a1;  // extent along the line's own axis (x for hLines, y for vLines)
    double pos;     // position along the perpendicular axis (y for hLines, x for vLines)
  };

  // One glyph-index-translated character drawn on this page: the
  // device-space position of its origin, plus the normalized font
  // name/style (the keys used in data/gylph_index.db).  Used to build
  // the per-paragraph/cell "fonts" arrays so a wrong character can be
  // traced back to the db rows to fix.
  struct FontHit {
    double x, y;
    std::string name;
    std::string style;
  };

  void captureRulingsFromPath(GfxState *state);
  void addHSegment(double x0, double x1, double y);
  void addVSegment(double y0, double y1, double x);

  std::vector<double> clusterCoords(std::vector<double> &coords, double tol);
  void rowXExtent(double rowY0, double rowY1, double *xMin, double *xMax);

  // Emit one non-table paragraph ("header", "text" or "footnotes"):
  // pull the text inside the given page rect in reading order and
  // write it as a JSON paragraph object.  Empty regions are skipped.
  void writeTextParagraph(TextPage *tp, const char *type,
			  double xMin, double yMin,
			  double xMax, double yMax);

  // Open/close a "table" paragraph, a row within it, and a "cell"
  // within that row.  Rows and cells are buffered in GStrings so the
  // enclosing objects' bboxes (unions of their children) can be
  // written before their contents.
  void beginTable();
  void endTable();
  void beginRow(int rowNum, double xMin, double yMin,
		double xMax, double yMax);
  void endRow();
  void writeCell(TextPage *tp, int colNum,
		 double xMin, double yMin, double xMax, double yMax);

  // JSON helpers.
  GString *escapeJSONString(const char *s, int len);
  GString *formatBBox(double xMin, double yMin, double xMax, double yMax);

  // Build the "fonts" JSON array for a region: the unique (name, style)
  // pairs of glyph-index-translated chars recorded inside the rect, in
  // first-appearance order ("[]" if there are none).
  GString *collectFontsJSON(double xMin, double yMin,
			    double xMax, double yMax);

  FILE *outFile;
  GBool tblOk;
  int curPageNum;
  double pageW, pageH;

  GBool havePages;		// at least one page object written
  GBool inPage;			// a page object is open but not yet closed
  GBool needParagraphComma;	// comma needed before next paragraph

  GString *tableRows;		// buffered row JSON for the open table
  GBool tableHasRows;
  double tblXMin, tblYMin, tblXMax, tblYMax;  // open table's bbox

  GString *rowCells;		// buffered cell JSON for the open row
  GBool rowHasCells;
  int curRowNum;
  double rowXMin, rowYMin, rowXMax, rowYMax;  // open row's bbox

  std::vector<Segment> hLines;  // horizontal ruling segments, current page
  std::vector<Segment> vLines;  // vertical ruling segments, current page

  std::vector<FontHit> fontHits;  // glyph-index-translated chars, current page

  // In-memory copy of the CID -> Unicode correction table
  // (data/gylph_index.db), used to translate extracted text GStrings
  // from ToUnicode-garbled to correct text.
  GlyphIndex *glyphIndex;

  // Per-line debug log (text / char codes / font names) of everything
  // handed to TextPage::addChar() after a glyph index lookup, written
  // next to the output file as <output>.log -- for hunting errors in
  // data/gylph_index.db.
  GlyphIndexLogger *glyphLogger;
};

#endif

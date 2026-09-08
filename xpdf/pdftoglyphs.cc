//========================================================================
//
// pdftoglyphs.cc
//
// Renders a document exactly as pdftoppm would, but instead of writing
// page images, captures one clean bitmap per unique (font, CID) glyph
// encountered -- input for hand-labelling a CID->Unicode correction
// table for fonts whose embedded ToUnicode CMap is wrong.
//
// Part of the Sicil-reader fork of xpdf; see README.md.
//
//========================================================================

#include <aconf.h>
#include <stdio.h>
#ifdef DEBUG_FP_LINUX
#  include <fenv.h>
#  include <fpu_control.h>
#endif
#include "parseargs.h"
#include "gmem.h"
#include "GString.h"
#include "GlobalParams.h"
#include "Object.h"
#include "PDFDoc.h"
#include "GlyphDbOutputDev.h"
#include "config.h"

static int firstPage = 1;
static int lastPage = 0;
static int resolution = 900;
static char enableFreeTypeStr[16] = "";
static char ownerPassword[33] = "";
static char userPassword[33] = "";
static GBool quiet = gFalse;
static char cfgFileName[256] = "";
static GBool printVersion = gFalse;
static GBool printHelp = gFalse;

static ArgDesc argDesc[] = {
  {"-f",      argInt,      &firstPage,     0,
   "first page to process"},
  {"-l",      argInt,      &lastPage,      0,
   "last page to process"},
  {"-r",      argInt,      &resolution,    0,
   "resolution, in DPI, used to rasterize glyphs (default is 150)"},
#if HAVE_FREETYPE_FREETYPE_H | HAVE_FREETYPE_H
  {"-freetype",   argString,      enableFreeTypeStr, sizeof(enableFreeTypeStr),
   "enable FreeType font rasterizer: yes, no"},
#endif
  {"-opw",    argString,   ownerPassword,  sizeof(ownerPassword),
   "owner password (for encrypted files)"},
  {"-upw",    argString,   userPassword,   sizeof(userPassword),
   "user password (for encrypted files)"},
  {"-q",      argFlag,     &quiet,         0,
   "don't print any messages or errors"},
  {"-cfg",        argString,      cfgFileName,    sizeof(cfgFileName),
   "configuration file to use in place of .xpdfrc"},
  {"-v",      argFlag,     &printVersion,  0,
   "print copyright and version info"},
  {"-h",      argFlag,     &printHelp,     0,
   "print usage information"},
  {"-help",   argFlag,     &printHelp,     0,
   "print usage information"},
  {"--help",  argFlag,     &printHelp,     0,
   "print usage information"},
  {"-?",      argFlag,     &printHelp,     0,
   "print usage information"},
  {NULL}
};

int main(int argc, char *argv[]) {
  PDFDoc *doc;
  GString *fileName;
  char *outDir;
  GString *ownerPW, *userPW;
  GlyphDbOutputDev *glyphOut;
  GBool ok;
  int exitCode;
  int pg;

#ifdef DEBUG_FP_LINUX
  feenableexcept(FE_DIVBYZERO);
  fpu_control_t cw;
  _FPU_GETCW(cw);
  cw = (cw & ~_FPU_EXTENDED) | _FPU_DOUBLE;
  _FPU_SETCW(cw);
#endif

  exitCode = 99;

  // parse args
  ok = parseArgs(argDesc, &argc, argv);
  if (!ok || argc != 3 || printVersion || printHelp) {
    fprintf(stderr, "pdftoglyphs version %s\n", xpdfVersion);
    fprintf(stderr, "%s\n", xpdfCopyright);
    if (!printVersion) {
      printUsage("pdftoglyphs", "<PDF-file> <output-dir>", argDesc);
    }
    goto err0;
  }
  fileName = new GString(argv[1]);
  outDir = argv[2];

  // read config file
  globalParams = new GlobalParams(cfgFileName);
  globalParams->setupBaseFonts(NULL);
  if (enableFreeTypeStr[0]) {
    if (!globalParams->setEnableFreeType(enableFreeTypeStr)) {
      fprintf(stderr, "Bad '-freetype' value on command line\n");
    }
  }
  if (quiet) {
    globalParams->setErrQuiet(quiet);
  }

  // open PDF file
  if (ownerPassword[0]) {
    ownerPW = new GString(ownerPassword);
  } else {
    ownerPW = NULL;
  }
  if (userPassword[0]) {
    userPW = new GString(userPassword);
  } else {
    userPW = NULL;
  }
  doc = new PDFDoc(fileName, ownerPW, userPW);
  if (userPW) {
    delete userPW;
  }
  if (ownerPW) {
    delete ownerPW;
  }
  if (!doc->isOk()) {
    exitCode = 1;
    goto err1;
  }

  // get page range
  if (firstPage < 1) {
    firstPage = 1;
  }
  if (lastPage < 1 || lastPage > doc->getNumPages()) {
    lastPage = doc->getNumPages();
  }

  // walk every page, capturing glyphs; unlike pdftoppm, no page image
  // is ever written out
  glyphOut = new GlyphDbOutputDev(outDir);
  glyphOut->startDoc(doc->getXRef());
  for (pg = firstPage; pg <= lastPage; ++pg) {
    doc->displayPage(glyphOut, pg, resolution, resolution, 0,
		      gFalse, gTrue, gFalse);
  }
  if (!quiet) {
    fprintf(stderr, "pdftoglyphs: captured %d unique glyphs\n",
	    glyphOut->getNumCaptured());
  }
  exitCode = glyphOut->getHadWriteError() ? 1 : 0;
  delete glyphOut;

  // clean up
 err1:
  delete doc;
  delete globalParams;
 err0:

  // check for memory leaks
  Object::memCheck(stderr);
  gMemReport(stderr);

  return exitCode;
}

#!/bin/bash


PATTERN=~/src/sijil/lib/ircica/*.pdf

for file in $PATTERN; do
    # xpdf/pdftoglyphs "$file" data/gylph_db/
    output_file="data/out/$(basename "$file" .pdf).json"
    xpdf/pdftotext -tablecells "$file" "$output_file"
done


# echo xpdf/pdftoglyphs ~/src/sijil/lib/ircica/01_Sicil_no.107.pdf data/gylph_db/

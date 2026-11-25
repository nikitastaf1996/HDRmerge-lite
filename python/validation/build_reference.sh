#!/bin/bash
# Build upstream processing code in an isolated harness, no Qt GUI/LibRaw IO.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEST=${1:?usage: build_reference.sh OUTPUT_DIRECTORY}
mkdir -p "$DEST"
DEST=$(CDPATH= cd -- "$DEST" && pwd)
curl -fsSL https://codeload.github.com/jcelaya/hdrmerge/tar.gz/2dbfd7d1e7d9060cff160663292b169f374010e1 | tar -xz -C "$DEST"
curl -fsSL https://codeload.github.com/hjkuijf/ALGLIB/tar.gz/96ce853fa15e282ea39fa482a8d57fd2f74e61bc | tar -xz -C "$DEST"
HDR="$DEST/hdrmerge-2dbfd7d1e7d9060cff160663292b169f374010e1/src"
ALG="$DEST/ALGLIB-96ce853fa15e282ea39fa482a8d57fd2f74e61bc/src"
mkdir -p "$DEST/core"
cp "$HDR"/{Image.cpp,Image.hpp,ImageStack.cpp,ImageStack.hpp,Array2D.hpp,BoxBlur.cpp,BoxBlur.hpp,Bitmap.cpp,Bitmap.hpp,Histogram.hpp,RawParameters.hpp,CFAPattern.hpp,Log.hpp,LoadSaveOptions.hpp} "$DEST/core/"
cp "$HERE"/{reference_main.cpp,QString,EditableMask.hpp} "$DEST/core/"
# The selected ALGLIB sources provide spline1dfitpenalized, as in upstream.
cd "$DEST/core"
g++ -O1 -ffunction-sections -fdata-sections -Wl,--gc-sections -std=c++11 -I. -I"$ALG" reference_main.cpp Image.cpp ImageStack.cpp Bitmap.cpp BoxBlur.cpp \
    "$ALG"/ap.cpp "$ALG"/alglibinternal.cpp "$ALG"/alglibmisc.cpp "$ALG"/linalg.cpp "$ALG"/solvers.cpp "$ALG"/optimization.cpp "$ALG"/interpolation.cpp "$ALG"/fasttransforms.cpp "$ALG"/specialfunctions.cpp "$ALG"/statistics.cpp -o "$DEST/hdrref"
echo "Reference core: $DEST/hdrref"

# HDRMerge Python — three-image default processing path

A focused Python implementation of the three-exposure Bayer DNG path in [HDRMerge](https://github.com/jcelaya/hdrmerge), based on commit `2dbfd7d1e7d9060cff160663292b169f374010e1`. This project uses the GPL-3.0-or-later license: see LICENSE.

## Install and run

Requires Python 3.10+, NumPy, SciPy, tifffile, imagecodecs and ALGLIB (`xalglib` 3.16). `xalglib` bundles native Linux x86-64 and Windows libraries; its platform support limits this package. In this directory:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
hdrmerge-python short.dng medium.dng long.dng -o merged.dng
pytest -q
```

Input order does not matter. The default replicates HDRMerge's automatic alignment, intersection crop, 3-pixel feathering, histogram-based saturation threshold, response estimation including ALGLIB's nonlinear fit and false-highlight adjustment. It writes an uncompressed 16-bit floating-point CFA DNG with the merged data in the cropped ActiveArea. Use `--bits 32` to retain the merge's float32 precision instead; this roughly doubles the file size and does not add information to the original exposures. `--no-align` skips alignment and cropping; `--radius 0` disables feathering. It rejects incompatible or unsupported inputs and refuses to overwrite an input file. It assumes RGB Bayer data, linear integer raw samples and matching camera metadata. Unsupported inputs include X-Trans, linearization tables, black-level deltas and OpcodeList1. Memory usage is several times the input size.

**Inspect alignment:** HDRMerge's own median-threshold alignment can fail badly for very dark or low-texture images. This Python path intentionally reproduces that behavior rather than substituting a different algorithm. For the supplied sample, default alignment finds a 128-pixel vertical shift and crops the active area to 4054×2944. That alignment is questionable; `--no-align` is provided as an alternative, but it can still ghost if the camera moved.

The output is a floating-point Bayer CFA DNG, not a demosaiced RGB LinearRaw DNG. Use a raw developer that supports floating-point DNG 1.4; some LibRaw/rawpy builds cannot open it. As with HDRMerge, peak normalization can make the initial rendering look dark, requiring positive exposure adjustment.

## Validation and differences

The default sample was compared to a small C++ harness compiled from upstream `Image.cpp`, `ImageStack.cpp`, `Bitmap.cpp`, `BoxBlur.cpp` and ALGLIB, with its camera parameters and pixel data supplied from the DNG bracket. It is **not** the full HDRMerge application: Qt GUI, LibRaw loading, Exiv2 transfer, DNG writing and rendering were not run in the harness. The harness and reproduction instructions are in `validation/`.

- Default alignment: both core implementations report saturation threshold 949 and the same shifts and active crop. After conversion to half-float, 11,934,972 of 11,934,976 active samples matched; mean absolute difference was 4.71×10⁻⁸ in sensor units, maximum 0.25. The four differences are around half-float rounding boundaries.
- Alignment disabled: all 12,582,912 half-float samples matched on this bracket.

The writer retains the core camera color matrix and white balance following HDRMerge's profile calculations, but is not a byte-identical port of its writer: this implementation puts the CFA in the primary TIFF IFD, writes uncompressed strips instead of HDRMerge's deflate/FP2-predicted tiles, omits its thumbnail and much of its EXIF/XMP/IPTC metadata, and does not transfer source opcode lists. The supplied source's opcode lists are in its primary IFD; HDRMerge's metadata transfer selectively copies them from a SubIFD. Adobe DNG SDK 1.4 dng_validate successfully decoded and rendered the supplied corrected float and integer sample DNGs (with warnings about CFA edge padding), but no full HDRMerge app or Lightroom Mobile test was available. These differences may affect downstream compatibility or rendered appearance. Other cameras, calibration layouts and exposure brackets are not validated for equivalence.

Adapted from HDRMerge by Javier Celaya and contributors; see LICENSE.

## Fixing previously generated files

Early versions accidentally omitted `NewSubFileType=0`; Adobe's DNG validator rejected those files as having no main image. The writer now sets the tag and uses uncompressed samples. To repackage an old file without changing its float pixels:

```sh
python compatibility.py old.dng fixed.dng
```

If a reader still rejects floating-point raw, `python compatibility.py --integer old.dng integer.dng` writes an uncompressed 16-bit integer CFA DNG. It maps the float black and white to 0 and 65535 and quantizes the values; it is a compatibility fallback, **not** an identical substitute for the floating-point original. It currently requires a uniform black level. Neither conversion adds a preview.

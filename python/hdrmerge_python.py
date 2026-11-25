"""A focused CFA/float DNG port of HDRMerge (GPL-3.0-or-later).

Based on Image.cpp, ImageStack.cpp, BoxBlur.cpp and DngFloatWriter.cpp in
HDRMerge, copyright 2012 Javier Celaya. See LICENSE and README for differences.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
import sys

import numpy as np
import tifffile
import hdrmerge_core as core


@dataclass
class Frame:
    path: Path
    pixels: np.ndarray
    tags: dict
    black: np.ndarray
    white: float
    shift: tuple[int, int] = (0, 0)
    scale: float = 1.0


def value(tags, code, default=None):
    return tags[code].value if code in tags else default


def rational_array(tag):
    a = np.asarray(tag.value, dtype=np.float64)
    if tag.dtype in (5, 10):
        a = a.reshape(-1, 2)
        if np.any(a[:, 1] == 0):
            raise ValueError(f"Invalid rational in {tag.name}")
        return a[:, 0] / a[:, 1]
    return a.reshape(-1)


def load(path):
    path = Path(path)
    with tifffile.TiffFile(path) as tif:
        root = tif.pages[0]
        pages = [root] + (list(root.pages) if root.pages else [])
        raw = [p for p in pages if int(p.photometric) == 32803 and p.samplesperpixel == 1]
        if len(raw) != 1:
            raise ValueError(f"{path}: expected exactly one single-channel CFA raw IFD")
        p = raw[0]
        tags = dict(root.tags.items())
        tags.update(dict(p.tags.items()))
        # Materialize lazily-read TIFF values before closing the file.
        for tag in tags.values():
            _ = tag.value
        if 50706 not in tags:
            raise ValueError(f"{path}: not a DNG")
        if any(k in tags for k in (50712, 50715, 50716, 51008)):
            raise ValueError(f"{path}: linearization table, black deltas or opcode list 1 are not supported")
        pattern = value(tags, 33421)
        if tuple(pattern or ()) != (2, 2) or 33422 not in tags:
            raise ValueError(f"{path}: only 2x2 Bayer CFA DNGs are supported")
        cfa = value(tags, 33422)
        plane = value(tags, 50710, b'\x00\x01\x02')
        try:
            colors = sorted(plane[index] for index in cfa)
        except (IndexError, TypeError):
            raise ValueError(f"{path}: invalid CFA pattern") from None
        if colors != [0, 1, 1, 2]:
            raise ValueError(f"{path}: only RGB Bayer CFA patterns are supported")
        if 50708 not in tags:
            raise ValueError(f"{path}: missing UniqueCameraModel")
        if int(value(tags, 50711, 1)) != 1:
            raise ValueError(f"{path}: only rectangular CFA layout is supported")
        repeat = tuple(value(tags, 50713, (1, 1)))
        if repeat not in ((1, 1), (2, 2)):
            raise ValueError(f"{path}: unsupported black level repeat dimensions {repeat}")
        black = rational_array(tags[50714]) if 50714 in tags else np.array([0.])
        if len(black) != repeat[0] * repeat[1]:
            raise ValueError(f"{path}: unsupported black level layout")
        black = black.reshape(repeat)
        white = rational_array(tags[50717]) if 50717 in tags else np.array([])
        if len(white) != 1 or white[0] <= np.max(black):
            raise ValueError(f"{path}: missing or invalid white level")
        pixels = p.asarray()
        if pixels.ndim != 2 or pixels.dtype.kind != 'u' or pixels.dtype.itemsize > 2:
            raise ValueError(f"{path}: expected integer mosaic data")
        return Frame(path, pixels, tags, black, float(white[0]))


def validate(frames):
    if len(frames) != 3:
        raise ValueError("exactly three DNG files are required")
    ref = frames[0]
    keys = (271, 272, 274, 33421, 33422, 50708, 50710, 50711, 50829,
            50719, 50720, 50721, 50722, 50723, 50724, 50727, 50728,
            50778, 50779, 50964, 50965, 51009, 51022)
    for f in frames[1:]:
        if f.pixels.shape != ref.pixels.shape or any(value(f.tags, k) != value(ref.tags, k) for k in keys):
            raise ValueError(f"{f.path}: camera, CFA, geometry or correction opcodes differ from the other inputs")
        if f.black.shape != ref.black.shape or not np.allclose(f.black, ref.black) or f.white != ref.white:
            raise ValueError(f"{f.path}: black/white levels differ from the other inputs")
    if not (50721 in ref.tags or 50722 in ref.tags) or 50728 not in ref.tags:
        raise ValueError("DNG must have a color matrix and AsShotNeutral")


def subtract_black(f):
    a = f.pixels.astype(np.float32)
    # BlackLevel is relative to ActiveArea, not the TIFF origin.
    top, left, _, _ = value(f.tags, 50829, (0, 0, *a.shape))
    for y in range(f.black.shape[0]):
        for x in range(f.black.shape[1]):
            a[(top + y) % f.black.shape[0]::f.black.shape[0],
              (left + x) % f.black.shape[1]::f.black.shape[1]] -= f.black[y, x]
    np.maximum(a, 0, out=a)
    return a


def extratag(tag):
    # tifffile accepts TIFF rational data as flattened numerator/denominator pairs.
    return (tag.code, int(tag.dtype), tag.count, tag.value, False)


def write_dng(path, data, ref, active_shape, bits=16):
    # Match the raw IFD's crop and primary color information in HDRMerge's writer.
    tags_in = ref.tags
    top, left, _, _ = value(tags_in, 50829, (0, 0, *data.shape))
    height, width = active_shape
    make, model = value(tags_in, 271, ''), value(tags_in, 272, '')
    copy = (270, 271, 272, 274, 306, 33421, 33422, 33432, 33434, 33437,
            34855, 36867, 37386, 37398, 50710, 50711)
    tags = [extratag(tags_in[k]) for k in copy if k in tags_in]
    matrix_tag = tags_in.get(50721) or tags_in.get(50722)
    matrix = rational_array(matrix_tag).reshape(3, 3)
    cal_tag = tags_in.get(50723) or tags_in.get(50724)
    calibration = rational_array(cal_tag).reshape(3, 3) if cal_tag else np.eye(3)
    xyz = np.ones(3)
    if 50729 in tags_in:
        xy = rational_array(tags_in[50729])
        xyz = np.array([xy[0], xy[1], 1-xy[0]-xy[1]]) / [0.950456, 1, 1.088754]
    matrix = (calibration @ matrix) * xyz
    scaled = np.copysign(np.floor(np.abs(matrix.flatten()*10000)+.5), matrix.flatten()).astype(int)
    matrix_rational = tuple(v for n in scaled for v in (int(n), 10000))
    neutral = rational_array(tags_in[50728])
    multipliers = 1/neutral
    multipliers /= multipliers.min()
    neutral = 1/multipliers
    neutral_rational = tuple(v for n in neutral for v in (int(np.floor(n*1000000+.5)), 1000000))
    black = np.tile(ref.black, (2//ref.black.shape[0], 2//ref.black.shape[1]))
    tags += [(50706, 'B', 4, (1, 4, 0, 0), False),
             (50707, 'B', 4, (1, 4, 0, 0), False),
             (50708, 's', 0, (str(make)+' '+str(model)).strip(), False),
             (50713, 'H', 2, (2, 2), False),
             (50714, 'H', 4, tuple(int(x) for x in black.flat), False),
             (50717, 'H', 1, int(ref.white), False),
             (50719, 'I', 2, (0, 0), False),
             (50720, 'I', 2, (width, height), False),
             (50829, 'I', 4, (top, left, top+height, left+width), False),
             (50721, '2i', 9, matrix_rational, False),
             (50727, '2I', 3, (1, 1, 1, 1, 1, 1), False),
             (50728, '2I', 3, neutral_rational, False),
             (50778, 'H', 1, 21, False)]
    # Explicit NewSubFileType=0 is necessary for Adobe's DNG parser to
    # recognize the main image. Uncompressed floats avoid older DNG SDK
    # bugs when decoding deflate-compressed 16-bit floating-point samples.
    if bits not in (16, 32):
        raise ValueError('floating-point output must be 16 or 32 bits')
    dtype = np.float16 if bits == 16 else np.float32
    tifffile.imwrite(path, data.astype(dtype), photometric=32803,
                     subfiletype=0, compression=None, rowsperstrip=128,
                     metadata=None, software='HDRMerge Python', extratags=tags)


def _report(progress, message, stderr=False):
    """Emit a status line to the caller's callback or to the console."""
    if progress is not None:
        progress(message)
    elif stderr:
        print(message, file=sys.stderr)
    else:
        print(message)


def run(paths, output, align=True, radius=3, bits=16, progress=None):
    if bits not in (16, 32):
        raise ValueError('floating-point output must be 16 or 32 bits')
    if radius < 0 or radius > 64:
        raise ValueError("radius must be between 0 and 64")
    if Path(output).resolve() in {Path(p).resolve() for p in paths}:
        raise ValueError("output must not overwrite an input")
    frames = [load(p) for p in paths]
    validate(frames)
    frames.sort(key=lambda f: float(np.mean(f.pixels)), reverse=True)
    ref = frames[-1]
    top, left, bottom, right = value(ref.tags, 50829, (0, 0, *ref.pixels.shape))
    h, w = ref.pixels.shape
    if (top < 0 or left < 0 or bottom > h or right > w or bottom <= top or right <= left
        or top % 2 or left % 2):
        raise ValueError('unsupported ActiveArea: must be nonempty, in bounds and Bayer-aligned')
    if np.any(ref.black != np.floor(ref.black)) or ref.white != int(ref.white) or ref.white > 65535:
        raise ValueError('only integer black/white levels up to 65535 are supported')
    images = [subtract_black(f)[top:bottom, left:right].astype(np.uint16) for f in frames]
    maxima = [int(f.pixels[top:bottom, left:right].max()) for f in frames]
    sat = core.saturation_level(images[0], ref.white, value(ref.tags, 33422))
    if sat <= 0 or sat >= ref.white:
        raise ValueError('invalid saturation threshold')
    shifts = core.align_stack(images, sat) if align else [(0, 0)] * 3
    if max(max(abs(y), abs(x)) for y, x in shifts) >= 64:
        _report(progress, 'Warning: HDRMerge alignment found a large displacement; '
                          'inspect for ghosting.', stderr=True)
    luts, slopes = core.responses(images, shifts, sat, ref.white, maxima)
    t, l, b, r = core.intersection(images[0].shape, shifts)
    cropped = [image[t-dy:b-dy, l-dx:r-dx] for image, (dy, dx) in zip(images, shifts)]
    neutral = rational_array(ref.tags[50728])
    if len(neutral) != 3 or np.any(neutral <= 0):
        raise ValueError('invalid AsShotNeutral')
    mult = 1/neutral
    mult /= mult.min()
    pattern = np.asarray(list(value(ref.tags, 33422))).reshape(2, 2)
    planes = np.asarray(list(value(ref.tags, 50710, b'\x00\x01\x02')))
    wb = mult[planes[pattern]]
    merged = core.compose(cropped, luts, sat, ref.white, wb, radius)
    peak = float(merged.max())
    if not np.isfinite(peak) or peak <= 0:
        raise ValueError('merged image contains no usable signal')
    merged *= (ref.white - float(ref.black.max())) / peak
    canvas = np.zeros(ref.pixels.shape, np.float32)
    canvas[top:top+b-t, left:left+r-l] = merged
    for y in range(ref.black.shape[0]):
        for x in range(ref.black.shape[1]):
            canvas[(top+y)%ref.black.shape[0]::ref.black.shape[0],
                   (left+x)%ref.black.shape[1]::ref.black.shape[1]] += ref.black[y, x]
    output = Path(output)
    fd, temporary = tempfile.mkstemp(prefix='.hdrmerge-', suffix='.dng', dir=output.parent)
    os.close(fd)
    try:
        write_dng(temporary, canvas, ref, merged.shape, bits=bits)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    _report(progress, f'White threshold: {sat}; active output: {r-l} x {b-t}')
    for f, shift, slope in zip(frames, shifts, slopes):
        _report(progress, f'{f.path}: shift={shift}, response={slope:.8f}')
    _report(progress, f'Wrote {output}')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Merge three Bayer DNG exposures into a floating-point CFA DNG.')
    parser.add_argument('inputs', nargs=3, metavar='DNG')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--no-align', action='store_true', help='skip Bayer-cell alignment (tripod brackets)')
    parser.add_argument('--radius', type=int, default=3, help='mask feather radius, default 3')
    parser.add_argument('--bits', type=int, choices=(16, 32), default=16,
                        help='floating-point output depth, default 16')
    args = parser.parse_args(argv)
    try:
        run(args.inputs, args.output, not args.no_align, args.radius, bits=args.bits)
    except (ValueError, OSError, tifffile.TiffFileError) as exc:
        print(f"hdrmerge-python: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

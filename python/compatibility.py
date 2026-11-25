"""Repackage this project's primary-IFD float CFA DNG for broader import.

The float option preserves the exact samples. The optional integer output
maps black to 0 and white to 65535, with quantization to 16-bit integer.
"""
import argparse
from pathlib import Path
import os
import tempfile

import numpy as np
import tifffile


def repackage(source, target, integer=False):
    if Path(source).resolve() == Path(target).resolve():
        raise ValueError('target must differ from source')
    with tifffile.TiffFile(source) as tif:
        p = tif.pages[0]
        if (p.photometric != 32803 or p.dtype.kind != 'f' or p.samplesperpixel != 1
                or 50706 not in p.tags or p.pages):
            raise ValueError('expected a primary-IFD floating-point CFA DNG from this tool')
        data = p.asarray()
        # Copy metadata only: never retain offsets, IFD pointers or digests.
        allowed = {270, 271, 272, 274, 306, 33421, 33422, 33432, 33434, 33437,
                   34855, 36867, 37386, 37398, 50706, 50707, 50708, 50710, 50711,
                   50713, 50714, 50717, 50718, 50719, 50720, 50721, 50722,
                   50723, 50724, 50725, 50726, 50727, 50728, 50729, 50730,
                   50731, 50778, 50779, 50829, 50931, 50932, 50933, 50934,
                   50935, 50936, 50937, 50938, 50939, 50940, 50941, 50964,
                   50965, 51009, 51022}
        tags = [(tag.code, int(tag.dtype), tag.count, tag.value, False)
                for tag in p.tags.values() if tag.code in allowed]
        if integer:
            from hdrmerge_python import rational_array
            black = rational_array(p.tags[50714]) if 50714 in p.tags else np.array([0.])
            white = rational_array(p.tags[50717]) if 50717 in p.tags else np.array([1.])
            if len(white) != 1 or not np.allclose(black, black[0]) or white[0] <= black[0]:
                raise ValueError('integer conversion requires one white and a uniform black level')
            # Float64 prevents early rounding during normalization. 16-bit
            # quantization loses precision compared with the float original.
            data = np.rint(np.clip((data.astype(np.float64) - black[0]) /
                                   (white[0] - black[0]), 0, 1) * 65535).astype(np.uint16)
            tags = [tag for tag in tags if tag[0] not in (50713, 50714, 50717)]
            tags += [(50713, 'H', 2, (1, 1), False),
                     (50714, 'H', 1, 0, False), (50717, 'I', 1, 65535, False)]
    target = Path(target)
    fd, name = tempfile.mkstemp(prefix='.dng-', suffix='.dng', dir=target.parent)
    os.close(fd)
    try:
        tifffile.imwrite(name, data, subfiletype=0, photometric=32803,
                         compression=None, rowsperstrip=128, metadata=None,
                         software='HDRMerge Python', extratags=tags)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--integer', action='store_true', help='convert to 16-bit integer (quantized)')
    args = parser.parse_args()
    repackage(args.source, args.target, args.integer)


if __name__ == '__main__':
    main()

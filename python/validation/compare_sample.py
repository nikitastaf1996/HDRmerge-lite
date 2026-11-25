"""Reproduce the C++ core comparison for the supplied RMX3871 bracket.

Usage: python compare_sample.py HDRREF BINARY_OUTPUT_DNG SHORT MEDIUM LONG
The reference harness's metadata constants are deliberately specific to this
bracket; do not use it as a general DNG reader or assume it validates metadata.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import tifffile


def main():
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    binary, output, *inputs = sys.argv[1:]
    with tempfile.TemporaryDirectory() as d:
        raws = []
        for index, name in enumerate(inputs):
            a = tifffile.imread(name)
            if a.shape != (3072, 4096) or a.dtype != np.uint16:
                raise ValueError('this harness is configured for the supplied 4096x3072 uint16 bracket')
            path = Path(d)/f'{index}.raw'
            a.astype('<u2').tofile(path)
            raws.append(str(path))
        ref = Path(d)/'reference.raw'
        subprocess.run([binary, '4096', '3072', *raws,
                        '1.13274336', '1', '2.46153855', str(ref)], check=True, env=os.environ.copy())
        expected = np.fromfile(ref, '<f4').reshape(3072, 4096).astype('f2')
        with tifffile.TiffFile(output) as f:
            page = f.pages[0]
            actual = page.asarray()
            t, l, b, r = page.tags[50829].value
        delta = np.abs(actual[t:b, l:r].astype('f4') - expected[t:b, l:r].astype('f4'))
        print(f'Active samples={delta.size}; different={np.count_nonzero(delta)}; '
              f'mean absolute difference={delta.mean():.9g}; max={delta.max():.9g}')


if __name__ == '__main__':
    main()

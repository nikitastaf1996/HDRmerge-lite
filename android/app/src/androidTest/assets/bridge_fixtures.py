"""Small synthetic DNG bracket used by the Android bridge instrumented test."""
from pathlib import Path

import numpy as np
import tifffile


def make_bridge_fixtures(directory):
    directory = Path(str(directory))
    rng = np.random.default_rng(7)
    scene = rng.integers(10, 70, (192, 192)).astype('float32')
    scene[70:110, 70:110] = 300
    tags = [
        (50706, 'B', 4, (1, 4, 0, 0), False),
        (50707, 'B', 4, (1, 1, 0, 0), False),
        (50708, 's', 0, 'Test camera', False),
        (33421, 'H', 2, (2, 2), False),
        (33422, 'B', 4, b'\x00\x01\x01\x02', False),
        (50710, 'B', 3, (0, 1, 2), False),
        (50711, 'H', 1, 1, False),
        (50713, 'H', 2, (1, 1), False),
        (50714, '2I', 1, (64, 1), False),
        (50717, 'I', 1, 1023, False),
        (50721, '2i', 9, (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1), False),
        (50728, '2I', 3, (1, 1, 1, 1, 1, 1), False),
        (50829, 'I', 4, (0, 0, *scene.shape), False),
    ]
    for index, scale in enumerate((1, 4, 16)):
        pixels = np.minimum(scene * scale + 64, 1023).astype('uint16')
        tifffile.imwrite(directory / f'{index}.dng', pixels, photometric=32803,
                         metadata=None, extratags=tags)


def verify_bridge_output(path):
    with tifffile.TiffFile(str(path)) as tif:
        page = tif.pages[0]
        pixels = page.asarray()
        return (pixels.shape == (192, 192) and pixels.dtype == np.float16 and
                np.isfinite(pixels).all() and pixels[90, 90] > pixels[20, 20] * 3)

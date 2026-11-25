import numpy as np
import pytest
import tifffile

from compatibility import repackage


def synthetic_float(path):
    pixels = np.array([[64, 64.5, 128, 1023], [65, 80, 500, 700]], np.float16)
    tags = [(50706, 'B', 4, (1, 4, 0, 0), False),
            (50707, 'B', 4, (1, 4, 0, 0), False),
            (50708, 's', 0, 'Test', False),
            (33421, 'H', 2, (2, 2), False),
            (33422, 'B', 4, (0, 1, 1, 2), False),
            (50713, 'H', 2, (2, 2), False),
            (50714, 'H', 4, (64, 64, 64, 64), False),
            (50717, 'H', 1, 1023, False)]
    tifffile.imwrite(path, pixels, photometric=32803, metadata=None, extratags=tags)
    return pixels


def test_repackage_float_retains_pixels_and_marks_main_image(tmp_path):
    src, out = tmp_path/'old.dng', tmp_path/'new.dng'
    original = synthetic_float(src)
    repackage(src, out)
    with tifffile.TiffFile(out) as tif:
        page = tif.pages[0]
        assert page.tags[254].value == 0
        assert page.dtype == np.dtype('float16')
        assert int(page.compression) == 1
        np.testing.assert_array_equal(page.asarray(), original)


def test_integer_fallback_scales_black_and_white(tmp_path):
    src, out = tmp_path/'float.dng', tmp_path/'int.dng'
    original = synthetic_float(src)
    repackage(src, out, integer=True)
    with tifffile.TiffFile(out) as tif:
        page = tif.pages[0]
        result = page.asarray()
        assert page.dtype == np.dtype('uint16')
        assert page.tags[50714].value == 0
        assert page.tags[50717].value == 65535
        assert page.tags[254].value == 0
        np.testing.assert_array_equal(result, np.rint((original.astype('float64')-64)/959*65535).astype('uint16'))
    with pytest.raises(ValueError, match='differ'):
        repackage(src, src)

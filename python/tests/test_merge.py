import numpy as np
import pytest
import tifffile

import hdrmerge_python as hm
import hdrmerge_core as core


def write_input(path, pixels, *, pattern=b'\x00\x01\x01\x02', black=(64, 1)):
    tags = [
        (50706, 'B', 4, (1, 4, 0, 0), False),
        (50707, 'B', 4, (1, 1, 0, 0), False),
        (50708, 's', 0, 'Test camera', False),
        (33421, 'H', 2, (2, 2), False),
        (33422, 'B', 4, pattern, False),
        (50710, 'B', 3, (0, 1, 2), False),
        (50711, 'H', 1, 1, False),
        (50713, 'H', 2, (1, 1), False),
        (50714, '2I', 1, black, False),
        (50717, 'I', 1, 1023, False),
        (50721, '2i', 9, (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1), False),
        (50728, '2I', 3, (1, 1, 1, 1, 1, 1), False),
        (50829, 'I', 4, (0, 0, *pixels.shape), False),
    ]
    tifffile.imwrite(path, pixels.astype('uint16'), photometric=32803,
                     metadata=None, extratags=tags)


def scene():
    rng = np.random.default_rng(7)
    a = rng.integers(10, 70, (192, 192)).astype('float32')
    # Large highlights are clipped in the longer exposures.
    a[70:110, 70:110] = 300
    return a



def test_response_fallback_and_highlight_selection():
    a = scene().astype('uint16')
    images = [np.minimum(a.astype('uint32')*16, 959).astype('uint16'),
              np.minimum(a.astype('uint32')*4, 959).astype('uint16'), a]
    shifts = [(0, 0)]*3
    sat = 949
    luts, slopes = core.responses(images, shifts, sat, 1023, [1023]*3)
    assert slopes == pytest.approx([64.06158/16, 64.06158/4, 64.06158], rel=.002)
    result = core.compose(images, luts, sat, 1023, np.ones((2, 2)), radius=0)
    assert result[90, 90] == pytest.approx(300*slopes[2], rel=.001)
    assert result[20, 20] == pytest.approx(a[20, 20]*slopes[2], rel=.001)


def test_hdrmerge_saturation_uses_brightest_histogram():
    img = np.full((200, 200), 200, dtype='uint16')
    img[:100, :100] = 500
    assert core.saturation_level(img, 1023, None) == 495


def test_crop_intersection_and_alignment():
    assert core.intersection((100, 200), [(-4, 6), (-2, 6), (0, 0)]) == (0, 6, 96, 200)
    # A featureless frame causes equal MTB scores. HDRMerge's strict first
    # candidate tie-breaking drives the displacement to the search limit.
    flat = np.full((256, 256), 100, dtype=np.uint16)
    assert core.align_pair(flat, flat, 1023) == (-126, -126)


def test_cli_round_trip(tmp_path):
    a = scene()
    paths = []
    for i, scale in enumerate((1, 4, 16)):
        path = tmp_path / f'{i}.dng'
        write_input(path, np.minimum(a*scale+64, 1023))
        paths.append(path)
    output = tmp_path/'merged.dng'
    hm.run(paths, output, align=False, radius=0)
    with tifffile.TiffFile(output) as tif:
        p = tif.pages[0]
        assert p.dtype == np.dtype('float16')
        assert int(p.photometric) == 32803
        assert p.tags[254].value == 0
        assert int(p.compression) == 1
        assert p.tags[50706].value == b'\x01\x04\x00\x00'
        assert p.tags[50714].value == (64, 64, 64, 64)
        assert p.tags[50717].value == 1023
        assert p.tags[33422].value == b'\x00\x01\x01\x02'
        assert p.tags[50721].value[0:2] == (10000, 10000)
        arr = p.asarray()
        assert arr.shape == a.shape
        assert np.isfinite(arr).all()
        assert arr.max() == pytest.approx(1023)
        assert arr[90, 90] > arr[20, 20] * 3


def test_float32_preserves_merge_precision(tmp_path):
    a = scene()
    paths = []
    for i, scale in enumerate((1, 4, 16)):
        path = tmp_path / f'{i}.dng'
        write_input(path, np.minimum(a * scale + 64, 1023))
        paths.append(path)
    half, full = tmp_path/'half.dng', tmp_path/'full.dng'
    hm.run(paths, half, align=False, radius=0)
    hm.run(paths, full, align=False, radius=0, bits=32)
    with tifffile.TiffFile(half) as h, tifffile.TiffFile(full) as f:
        assert f.pages[0].dtype == np.dtype('float32')
        assert f.pages[0].tags[254].value == 0
        assert int(f.pages[0].compression) == 1
        full_pixels = f.pages[0].asarray()
        half_pixels = h.pages[0].asarray()
        np.testing.assert_array_equal(full_pixels.astype('float16'), half_pixels)
        assert np.any(full_pixels != half_pixels.astype('float32'))
    with pytest.raises(ValueError, match='16 or 32'):
        hm.run(paths, full, align=False, bits=24)


def test_rejects_mismatched_cfa_and_input_overwrite(tmp_path):
    a = scene()+64
    paths = [tmp_path/f'{i}.dng' for i in range(3)]
    for path in paths:
        write_input(path, a)
    write_input(paths[1], a, pattern=b'\x02\x01\x01\x00')
    with pytest.raises(ValueError, match='CFA'):
        hm.run(paths, tmp_path/'out.dng', align=False)
    with pytest.raises(ValueError, match='overwrite'):
        hm.run(paths, paths[0], align=False)


def test_rejects_bad_exposure_overlap():
    with pytest.raises(ValueError, match='insufficient overlapping signal'):
        core.responses([np.zeros((192, 192), dtype='uint16')]*3, [(0, 0)]*3, 949, 1023, [1023]*3)


def test_nonlinear_fit_branch(monkeypatch):
    v = np.tile(np.arange(960, dtype=np.uint16), (128, 1))
    images = [v, (v // 2).astype('uint16'), (v // 4).astype('uint16')]
    calls = []
    original = core.xalglib.spline1dfitpenalized
    def spy(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(core.xalglib, 'spline1dfitpenalized', spy)
    luts, slopes = core.responses(images, [(0, 0)]*3, 949, 1023, [1023]*3)
    assert calls
    assert all(np.isfinite(s) and s > 0 for s in slopes)
    assert luts[0][400] > 0


def test_highlight_feather_correction_uses_white_balance():
    v = np.full((64, 64), 100, dtype=np.uint16)
    v[30:34, 30:34] = 970
    images = [v, np.full_like(v, 250), np.full_like(v, 125)]
    luts = [np.arange(65536, dtype=np.float64)]*3
    a = core.compose(images, luts, 949, 1023, np.ones((2, 2)), 3)
    b = core.compose(images, luts, 949, 1023, np.full((2, 2), 2.0), 3)
    assert np.any(a != b)
    assert np.isfinite(b).all()

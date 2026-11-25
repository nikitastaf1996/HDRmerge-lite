import numpy as np
import pytest

import alglib_compat
import hdrmerge_core as core


def _curve_values(mod, curve, xs):
    return np.array([mod.spline1dcalc(curve, x) for x in xs])


def test_compat_matches_alglib_when_available():
    try:
        from xalglib import xalglib as ref
    except ImportError:
        pytest.skip("xalglib not installed")

    rng = np.random.default_rng(11)
    for _ in range(20):
        x = np.sort(rng.choice(np.arange(0, 1100), 12, replace=False)).astype(float)
        t = np.linspace(0, 1, x.size)
        y = 40 * t + 15 * np.sin(7 * t) + rng.normal(0, 0.4, x.size)
        m, rho = 24, 3.0
        _, c_ref, _ = ref.spline1dfitpenalized(x.tolist(), y.tolist(), m, rho)
        _, c_new, _ = alglib_compat.spline1dfitpenalized(x, y, m, rho)
        xs = np.linspace(x[0] - 4, x[-1] + 4, 120)
        a = _curve_values(ref, c_ref, xs)
        b = _curve_values(alglib_compat, c_new, xs)
        assert np.allclose(a, b, rtol=1e-7, atol=1e-7)


def test_core_responses_use_compat_fallback(monkeypatch):
    """The response estimator must work when only the NumPy ALGLIB port exists."""
    v = np.tile(np.arange(960, dtype=np.uint16), (128, 1))
    images = [v, (v // 2).astype(np.uint16), (v // 4).astype(np.uint16)]
    monkeypatch.setattr(core, "xalglib", alglib_compat)
    luts, slopes = core.responses(images, [(0, 0)] * 3, 949, 1023, [1023] * 3)
    assert all(np.isfinite(s) and s > 0 for s in slopes)
    assert luts[0][400] > 0


def test_compat_rejects_length_mismatch():
    with pytest.raises(ValueError):
        alglib_compat.spline1dfitpenalized([0.0, 1.0], [0.0], 20, 3.0)

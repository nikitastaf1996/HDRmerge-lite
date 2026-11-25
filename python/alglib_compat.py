"""Pure-NumPy stand-in for the two ALGLIB functions used by ``hdrmerge_core``.

``hdrmerge_core`` needs exactly two routines from the ALGLIB numerical library:
``spline1dfitpenalized`` and ``spline1dcalc``. The ``xalglib`` wheel that
supplies them bundles only Linux x86-64 and Windows native libraries, so it
cannot run on Android (ARM). This module reimplements those two routines with
NumPy, ported directly from ALGLIB's ``interpolation.cpp`` (GPL-3.0-or-later),
so the HDRMerge Python core works everywhere NumPy works.

The public names and signatures match ``xalglib.xalglib``::

    info, curve, rep = spline1dfitpenalized(x, y, m, rho)
    y = spline1dcalc(curve, x)

Only the non-periodic, natural-boundary path used by the HDRMerge response
estimator is implemented; that is the only path ``spline1dfitpenalized`` takes
internally.
"""
from __future__ import annotations

import numpy as np

# ALGLIB's machine epsilon and the rho clamp bound: v = -log(eps)/log(10).
_EPS = float(np.finfo(np.float64).eps)
_RHO_LIMIT = -np.log(_EPS) / np.log(10.0)


class spline1dinterpolant:
    """Piecewise cubic Hermite spline (ALGLIB ``spline1dinterpolant``).

    ``nodes`` are strictly increasing breakpoints; ``vals`` are the function
    values and ``derivs`` the first derivatives at each node.
    """

    __slots__ = ("nodes", "vals", "derivs", "periodic", "k", "n")

    def __init__(self, nodes, vals, derivs):
        self.nodes = np.asarray(nodes, dtype=np.float64)
        self.vals = np.asarray(vals, dtype=np.float64)
        self.derivs = np.asarray(derivs, dtype=np.float64)
        self.periodic = False
        self.k = 3
        self.n = self.nodes.size


def _hermite_eval(nodes, vals, derivs, xq):
    """Evaluate the Hermite spline at ``xq`` (vectorised, endpoints clamped)."""
    n = nodes.size
    xq = np.asarray(xq, dtype=np.float64)
    idx = np.searchsorted(nodes, xq, side="right") - 1
    idx = np.clip(idx, 0, n - 2)
    h = nodes[idx + 1] - nodes[idx]
    t = (xq - nodes[idx]) / h
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return (h00 * vals[idx] + h10 * h * derivs[idx]
            + h01 * vals[idx + 1] + h11 * h * derivs[idx + 1])


def _natural_cubic_d1(x, y):
    """First derivatives at the nodes of the natural cubic spline through (x, y).

    Implements ALGLIB's ``spline1d_spline1dgriddiffcubicinternal`` for
    ``boundltype == boundrtype == 2`` (second derivative zero at both ends) via
    the tridiagonal "slopes" system solved with the Thomas algorithm.
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = x.size
    h = np.diff(x)
    # Right-hand side of the tridiagonal system.
    b = np.empty(n)
    b[0] = 3.0 * (y[1] - y[0]) / h[0]
    if n > 2:
        sl = np.diff(y) / h                       # slope of each interval
        b[1:-1] = 3.0 * (sl[:-1] * h[1:] + sl[1:] * h[:-1])
    b[-1] = 3.0 * (y[-1] - y[-2]) / h[-1]
    # Tridiagonal coefficients: a (sub), bb (diag), c (super).
    a = np.empty(n)
    bb = np.empty(n)
    c = np.empty(n)
    a[0], bb[0], c[0] = 0.0, 2.0, 1.0
    if n > 2:
        a[1:-1] = h[1:]
        bb[1:-1] = 2.0 * (h[1:] + h[:-1])
        c[1:-1] = h[:-1]
    a[-1], bb[-1], c[-1] = 1.0, 2.0, 0.0
    # Thomas algorithm (matches ALGLIB's spline1d_solvetridiagonal).
    cp = np.empty(n)
    dp = np.empty(n)
    cp[0] = c[0] / bb[0]
    dp[0] = b[0] / bb[0]
    for k in range(1, n):
        denom = bb[k] - a[k] * cp[k - 1]
        cp[k] = c[k] / denom
        dp[k] = (b[k] - a[k] * dp[k - 1]) / denom
    d = np.empty(n)
    d[-1] = dp[-1]
    for k in range(n - 2, -1, -1):
        d[k] = dp[k] - cp[k] * d[k + 1]
    return d


def _natural_cubic_d2(x, y, d1):
    """Second derivatives at the nodes, from the Hermite power coefficients."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    d1 = np.asarray(d1, dtype=np.float64)
    h = np.diff(x)
    s2 = (3.0 * np.diff(y) - 2.0 * d1[:-1] * h - d1[1:] * h) / (h * h)
    s3 = (2.0 * (y[:-1] - y[1:]) + d1[:-1] * h + d1[1:] * h) / (h * h * h)
    d2 = np.empty(x.size)
    d2[:-1] = 2.0 * s2
    d2[-1] = 2.0 * s2[-1] + 6.0 * s3[-1] * h[-1]
    return d2


class spline1dfitreport:
    """Minimal stand-in for ALGLIB's ``spline1dfitreport``."""

    __slots__ = ("rmserror", "avgerror", "avgrelerror", "maxerror")

    def __init__(self, rmserror=0.0, avgerror=0.0, avgrelerror=0.0, maxerror=0.0):
        self.rmserror = rmserror
        self.avgerror = avgerror
        self.avgrelerror = avgrelerror
        self.maxerror = maxerror


def spline1dfitpenalized(x, y, m, rho):
    """Discrete penalized (smoothing) cubic spline fit.

    Port of ALGLIB ``spline1dfitpenalized`` / ``spline1dfitpenalizedw`` with
    unit weights. Equidistant nodes on the scaled abscissa range build the
    basis; the fit minimizes ``sum (y - S(x))^2 + C*10^rho * integral S''^2``.
    Returns ``(info, curve, rep)`` exactly like the ALGLIB binding.
    """
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    n = x.size
    if n != y.size:
        raise ValueError("x and y must have the same length")
    if n < 1 or m < 4:
        return -1, spline1dinterpolant(np.zeros(2), np.zeros(2), np.zeros(2)), spline1dfitreport()

    rho = float(rho)
    rho = max(-_RHO_LIMIT, min(_RHO_LIMIT, rho))
    lambdav = 10.0 ** rho

    # Sort points by abscissa (ALGLIB sorts internally).
    order = np.argsort(x, kind="stable")
    x = x[order]
    y = y[order]
    xoriginal = x.copy()
    yoriginal = y.copy()

    # Scale X: [xa, xb] -> [-1, 1].
    xa, xb = float(x[0]), float(x[-1])
    if xa == xb:
        xa, xb = (-1.0, 1.0) if xa == 0.0 else ((0.5 * xa, xa) if xa > 0 else (xa, 0.5 * xa))
    x = 2.0 * (x - 0.5 * (xa + xb)) / (xb - xa)

    # Scale Y: [sa, sb] -> [0, 1].
    sa = float(np.mean(yoriginal))
    sb = float(np.sqrt(np.mean((yoriginal - sa) ** 2)) + sa)
    if sb == sa:
        sb = 2.0 * sa
    if sb == sa:
        sb = sa + 1.0
    y = (yoriginal - sa) / (sb - sa)

    # Equidistant nodes on [-1, 1].
    bx = (2.0 * np.arange(m) / (m - 1)) - 1.0

    # Basis functions: natural cubic splines with value 1 at one node, 0 elsewhere.
    fmatrix = np.empty((n, m))
    d2matrix = np.empty((m, m))
    fdmax = 0.0
    for b in range(m):
        by = np.zeros(m)
        by[b] = 1.0
        d1 = _natural_cubic_d1(bx, by)
        d2 = _natural_cubic_d2(bx, by, d1)
        d2matrix[b] = d2
        fcolumn = _hermite_eval(bx, by, d1, x)
        fmatrix[:, b] = fcolumn
        fdmax = max(fdmax, float(np.dot(fcolumn, fcolumn)))

    # Penalty matrix A[i][j] = integral(B_i'' * B_j'') over [-1, 1].
    amatrix = np.zeros((m, m))
    for k in range(m - 1):
        h = bx[k + 1] - bx[k]
        L = d2matrix[:, k]
        R = d2matrix[:, k + 1]
        d = R - L
        amatrix += h * (np.outer(L, L) + (np.outer(L, d) + np.outer(d, L)) / 2.0
                        + np.outer(d, d) / 3.0)
    admax = float(np.max(np.abs(np.diag(amatrix))))
    pdecay = lambdav * fdmax / admax
    tdecay = fdmax * (1.0 + pdecay) * 10.0 * _EPS

    # Normal equations: (F^T F + pdecay*A + tdecay*I) c = F^T y.
    nmatrix = fmatrix.T @ fmatrix + pdecay * amatrix
    np.fill_diagonal(nmatrix, nmatrix.diagonal() + tdecay)
    rightpart = fmatrix.T @ y
    try:
        c = np.linalg.solve(nmatrix, rightpart)
    except np.linalg.LinAlgError:
        return -4, spline1dinterpolant(np.zeros(2), np.zeros(2), np.zeros(2)), spline1dfitreport()

    # First derivatives of the fitted values at the nodes.
    bd1 = _natural_cubic_d1(bx, c)

    # Extend the spline outside [-1, 1] to force linearity beyond the fit.
    tx = np.empty(m + 2)
    ty = np.empty(m + 2)
    td = np.empty(m + 2)
    tx[1:m + 1] = bx
    ty[1:m + 1] = c
    td[1:m + 1] = bd1
    tx[0] = tx[1] - (tx[2] - tx[1])
    ty[0] = ty[1] - td[1] * (tx[2] - tx[1])
    td[0] = td[1]
    tx[m + 1] = tx[m] + (tx[m] - tx[m - 1])
    ty[m + 1] = ty[m] + td[m] * (tx[m] - tx[m - 1])
    td[m + 1] = td[m]

    curve = spline1dinterpolant(tx, ty, td)
    # Map back to the original X and Y scales.
    a = 2.0 / (xb - xa)
    b = -(xa + xb) / (xb - xa)
    curve.nodes = (curve.nodes - b) / a
    curve.derivs = a * curve.derivs
    curve.vals = (sb - sa) * curve.vals + sa
    curve.derivs = (sb - sa) * curve.derivs

    # Report (ALGLIB computes the same unweighted errors).
    v = _hermite_eval(curve.nodes, curve.vals, curve.derivs, xoriginal)
    err = v - yoriginal
    rep = spline1dfitreport(
        rmserror=float(np.sqrt(np.mean(err ** 2))),
        avgerror=float(np.mean(np.abs(err))),
        avgrelerror=float(np.mean(np.abs(err[yoriginal != 0]) / np.abs(yoriginal[yoriginal != 0])))
        if np.any(yoriginal != 0) else 0.0,
        maxerror=float(np.max(np.abs(err))),
    )
    return 1, curve, rep


def spline1dcalc(c, x):
    """Evaluate the spline interpolant ``c`` at ``x``."""
    return float(_hermite_eval(c.nodes, c.vals, c.derivs, np.asarray(x, dtype=np.float64).reshape(-1))[0])

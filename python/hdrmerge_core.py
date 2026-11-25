"""Three-frame Bayer processing, translated from HDRMerge 2dbfd7d.

Copyright 2012 Javier Celaya and HDRMerge contributors; GPL-3.0-or-later.
"""
import numpy as np
from scipy import ndimage

try:
    from xalglib import xalglib
except (ImportError, OSError):
    # The xalglib wheel only bundles Linux x86-64 and Windows natives, so it
    # cannot load on other platforms (notably Android ARM). Fall back to a
    # pure-NumPy port of the two routines the core uses.
    import alglib_compat as xalglib


def saturation_level(image, white, cfa):
    # HDRMerge splits the two greens into separate channels (LibRaw FC).
    histmax = []
    threshold = image.size // 10000
    for y in range(2):
        for x in range(2):
            hist = np.bincount(image[y::2, x::2].ravel().astype(np.int32), minlength=65536)
            eligible = np.flatnonzero(hist > threshold)
            histmax.append(int(eligible[-1]) if len(eligible) else 0)
    peak = max(histmax)
    return int(min(white, peak) * .99) if peak else int(white * .99)


def _percentile(a, frac):
    counts = np.bincount(a.ravel().astype(np.int32), minlength=65536)
    limit = int(a.size * frac)
    return int(np.searchsorted(np.cumsum(counts), limit, side='left')) if limit else 0


def _pyramid(a):
    out = []
    for _ in range(6):
        h, w = a.shape
        if min(h, w) < 2:
            raise ValueError('images must be at least 64 by 64 pixels for HDRMerge alignment')
        a = (a[:h//2*2:2, :w//2*2:2].astype(np.uint32) + a[1:h//2*2:2, :w//2*2:2] +
             a[:h//2*2:2, 1:w//2*2:2] + a[1:h//2*2:2, 1:w//2*2:2]) >> 2
        a = a.astype(np.uint16)
        out.append(a)
    return out


def _overlap(shape, dy, dx):
    h, w = shape
    return ((slice(max(dy, 0), min(h, h+dy)), slice(max(dx, 0), min(w, w+dx))),
            (slice(max(-dy, 0), min(h, h-dy)), slice(max(-dx, 0), min(w, w-dx))))


def align_pair(moving, reference, sat):
    """Image::alignWith: bitmaps and absolute mismatch count, ties in C++ order."""
    frac = np.count_nonzero(moving <= sat) / moving.size / 2
    mp, rp = _pyramid(moving), _pyramid(reference)
    dx = dy = 0
    for m, r in reversed(list(zip(mp, rp))):
        tm, tr = _percentile(m, frac), _percentile(r, frac)
        mt, rt = int(tm/16), int(tr/16)
        mb, rb = m > tm, r > tr
        me = (m <= tm-mt) | (m > tm+mt)
        re = (r <= tr-rt) | (r > tr+rt)
        minimum = m.size
        oldx, oldy = dx, dy
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                x, y = oldx+i, oldy+j
                if abs(y) >= m.shape[0] or abs(x) >= m.shape[1]:
                    continue
                rs, ms = _overlap(m.shape, y, x)
                error = np.count_nonzero((rb[rs] ^ mb[ms]) & re[rs] & me[ms])
                if error < minimum:
                    minimum, dx, dy = error, x, y
        dx *= 2
        dy *= 2
    return dy, dx


def align_stack(images, sat):
    # HDRMerge aligns each neighboring pair and then accumulates displacement.
    shifts = [(0, 0), (0, 0), (0, 0)]
    shifts[1] = align_pair(images[1], images[2], sat)
    a = align_pair(images[0], images[1], sat)
    shifts[0] = (a[0]+shifts[1][0], a[1]+shifts[1][1])
    return shifts


def intersection(shape, shifts):
    h, w = shape
    top, left = max(0, *(s[0] for s in shifts)), max(0, *(s[1] for s in shifts))
    bottom = min(h, *(h+s[0] for s in shifts))
    right = min(w, *(w+s[1] for s in shifts))
    if bottom <= top or right <= left:
        raise ValueError('aligned images have no common area')
    return top, left, bottom, right


def responses(images, shifts, sat, white, raw_maxima):
    # Response values in HDRMerge's internal units, shortest = 65535/white.
    luts = [None, None, np.arange(65536, dtype=np.float64) * (65535.0 / white)]
    slopes = [0., 0., 65535.0/white]
    for i in (1, 0):
        dy, dx = shifts[i][0]-shifts[i+1][0], shifts[i][1]-shifts[i+1][1]
        rs, ms = _overlap(images[0].shape, dy, dx)
        v, n = images[i][ms], images[i+1][rs]
        maxval = int(raw_maxima[i]); counts = np.zeros(maxval+1, np.int64)
        sums = np.zeros(maxval+1, np.float64)
        for y in range(0, v.shape[0], 128):
            vv, nn = v[y:y+128], n[y:y+128]
            good = (vv >= nn) & (vv < sat)
            vi = vv[good].astype(np.int32)
            counts += np.bincount(vi, minlength=maxval+1)
            sums += np.bincount(vi, weights=luts[i+1][nn[good]], minlength=maxval+1)
        values = np.arange(maxval-1, int(np.ceil(maxval*.75))-1, -1)
        values = values[counts[values] > 2]
        if 1+len(values) >= maxval//8:
            xs = [0.] + values.astype(float).tolist()
            ys = [0.] + (sums[values]/counts[values]).tolist()
            info, curve, _ = xalglib.spline1dfitpenalized(xs, ys, 200, 3)
            if info <= 0:
                raise ValueError('ALGLIB spline fit failed')
            threshold = int(.9*sat)
            slopes[i] = xalglib.spline1dcalc(curve, threshold)/threshold
            lut = np.arange(65536, dtype=np.float64)*slopes[i]
            # Input black-subtracted values never exceed the recorded raw maximum.
            for n in range(threshold+1, maxval+1):
                lut[n] = xalglib.spline1dcalc(curve, n)
            luts[i] = lut
        else:
            vv = np.arange(len(counts), dtype=np.float64)
            denom = np.dot(counts, vv*vv)
            if denom <= 0:
                raise ValueError('insufficient overlapping signal to estimate response')
            slopes[i] = np.dot(vv, sums)/denom
            luts[i] = np.arange(65536, dtype=np.float64)*slopes[i]
        if not np.isfinite(slopes[i]) or slopes[i] <= 0:
            raise ValueError('invalid exposure response')
    return luts, slopes


def compose(images, luts, sat, white, wb, radius=3):
    shape = images[0].shape
    mask = np.zeros(shape, np.uint8)
    neighbors = []
    for i in (0, 1):
        around = ndimage.maximum_filter(images[i], size=3, mode='nearest')
        neighbors.append(around)
        mask[(mask == i) & (around >= sat)] = i+1
    if radius:
        coords = np.arange(-radius, radius+1)
        yy, xx = np.meshgrid(coords, coords, indexing='ij')
        circ = np.sqrt(np.maximum(0, radius*radius - np.maximum(np.abs(xx)-.5, 0)**2)).astype(int)
        footprint = np.abs(yy) <= circ
        blend = ndimage.maximum_filter(mask, footprint=footprint, mode='nearest').astype(np.float32)
        half = int(np.floor(radius*.39+.5))
        for _ in range(3):
            blend = ndimage.uniform_filter(blend, size=2*half+1, mode='nearest')
    else:
        blend = mask.astype(np.float32)
    # Process rows in blocks, to avoid a large collection of full-size float arrays.
    out = np.empty(shape, dtype=np.float32)
    for start in range(0, shape[0], 128):
        end = min(start+128, shape[0]); sl = slice(start, end)
        p = np.maximum(blend[sl].astype(np.float64), 0)
        j = np.floor(p).astype(np.uint8); frac = p-j
        v = np.zeros(p.shape, np.float64); vv = np.zeros_like(v)
        wm = np.tile(wb, ((end-start+1)//2, (shape[1]+1)//2))[:end-start, :shape[1]]
        if start % 2: wm = np.tile(wb[::-1], ((end-start+1)//2, (shape[1]+1)//2))[:end-start, :shape[1]]
        original = mask[sl]
        for i in range(3):
            sel = j == i
            if not np.any(sel): continue
            x = luts[i][images[i][sl]]
            bad = sel & (i < original)
            x[bad] /= wm[bad]
            v[sel] = x[sel]
            if i < 2:
                k = np.minimum((neighbors[i][sl].astype(np.float64)-sat)/(white-sat), 1)
                update = bad & (frac > .0001)
                frac[update] += (1-frac[update])*k[update]
                nxt = luts[i+1][images[i+1][sl]]
                badnext = sel & (i+1 < original)
                nxt[badnext] /= wm[badnext]
                vv[sel] = nxt[sel]
        frac[(j >= 2) | (frac <= .0001)] = 0
        out[sl] = v - frac*(v-vv)
    return out

"""Android-facing entry point for the HDRMerge Python core.

The Android app (Chaquopy) calls :func:`run` on a background thread. It takes
real filesystem paths to three input DNGs and a path for the merged output,
runs the same processing as the ``hdrmerge-python`` console script, and
reports progress through an optional Java callback object exposing
``onProgress(String)``.

Keeping this glue here means the Android layer only has to manage files and
threads; all image processing stays in the validated Python core.
"""
from __future__ import annotations

from pathlib import Path

import hdrmerge_python as hm


def run(inputs, output, align=True, radius=3, bits=16, progress=None):
    """Merge three DNG exposures and write a floating-point CFA DNG.

    ``inputs`` is a sequence of three DNG paths; ``output`` the destination
    path. ``progress`` may be a Java object with ``onProgress(String)``.
    Returns a dict describing the result, or raises ``ValueError``/``OSError``
    on failure (the Android layer turns that into a user-visible message).
    """
    paths = [str(p) for p in inputs]
    if len(paths) != 3:
        raise ValueError("exactly three input DNG files are required")
    output = str(output)

    def emit(message):
        if progress is not None:
            try:
                progress.onProgress(message)
            except Exception:  # never let a UI callback break the merge
                print(message)
        else:
            print(message)

    emit("Loading and validating exposures...")
    hm.run(paths, output, align=bool(align), radius=int(radius), bits=int(bits),
           progress=emit)
    return {"output": output}

# HDRmerge-lite

An Android app that wraps a minimal, Python implementation of
[HDRMerge](https://github.com/jcelaya/hdrmerge)'s three-exposure Bayer DNG merge
pipeline. You pick three DNG exposures of the same scene, and the app merges
them into a single floating-point CFA DNG — the same processing path as the
`hdrmerge-python` console tool, running on-device.

## Repository layout

```
.
├── python/        HDRMerge Python package (the processing core + Android entry point)
│   ├── hdrmerge_python.py   CLI + DNG loading/writing, top-level run()
│   ├── hdrmerge_core.py     Alignment, response estimation, composition
│   ├── alglib_compat.py     Pure-NumPy ALGLIB replacement (see below)
│   ├── hdrmerge_app.py      Callable entry point used by the Android app
│   ├── compatibility.py     Repackage/quantize previously written DNGs
│   ├── pyproject.toml
│   └── tests/
└── android/       Android app (Gradle project, Chaquopy)
    ├── app/src/main/kotlin/com/hdrmerge/lite/
    │   ├── MainActivity.kt   UI: pick files, run merge, save output
    │   ├── HdrMergeEngine.kt Chaquopy bridge to the Python core
    │   └── DngFiles.kt       Storage Access Framework helpers
    └── app/src/main/res/
```

The Android build copies `python/*.py` into the APK at build time, so there is a
single source of truth for the processing code.

## The Python core

`python/` is a focused port of HDRMerge's three-exposure path (commit
`2dbfd7d`), GPL-3.0-or-later. It requires three DNGs of the same scene with a
single-channel 2×2 RGB Bayer CFA and integer raw samples, matching camera/CFA/
geometry/black-white/color metadata, and a color matrix with AsShotNeutral.

Run it directly:

```sh
cd python
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test,alglib]'
hdrmerge-python short.dng medium.dng long.dng -o merged.dng
pytest -q
```

Options: `--no-align` (skip alignment/crop), `--radius N` (feathering, default
3, `0` disables), `--bits 16|32` (float output depth, default 16).

### ALGLIB replacement

`hdrmerge_core` uses two ALGLIB routines (`spline1dfitpenalized` and
`spline1dcalc`) for the response-curve fit. The `xalglib` wheel that provides
them bundles only Linux x86-64 and Windows natives, so it cannot run on Android
(ARM). `alglib_compat.py` is a pure-NumPy port of those two routines (translated
from ALGLIB's `interpolation.cpp`, GPL-3.0-or-later). `hdrmerge_core` imports
`xalglib` when available and falls back to `alglib_compat` otherwise, so desktop
use is unchanged while Android works without any native ALGLIB build.

The fallback is validated against `xalglib`: across random and realistic
response data the fitted curves agree to ~1e-9 relative error, and an
end-to-end merge produces **byte-identical** float16 output to the `xalglib`
path. See `python/tests/test_alglib_compat.py`.

## The Android app

Built with [Chaquopy](https://chaquopy.com), which embeds CPython in the APK.

### Prerequisites

- Android Studio, JDK 17, Android SDK (compileSdk 34), and a local Python
  matching the app's interpreter version (3.11) available on the build machine
  (Chaquopy uses it to install/compile packages).
- Chaquopy downloads Android builds of NumPy, SciPy and tifffile from its
  package index. `xalglib` and `imagecodecs` are intentionally not installed:
  the former is replaced by `alglib_compat`, and the latter is only needed by
  tifffile for compressed TIFFs (the merge output here is uncompressed).

### Build and run

```sh
cd android
./gradlew :app:assembleDebug
```

Install the resulting APK, open **HDRMerge Lite**, pick three DNGs, press
**Merge**, then **Save output DNG…** to choose where the result is written.

### How it works

1. DNGs chosen through the Storage Access Framework are copied into the app's
   private `files/inputs` directory, because the Python core reads files by
   path.
2. **Merge** calls `HdrMergeEngine.merge`, which invokes
   `hdrmerge_app.run(...)` in the embedded interpreter on a background thread.
   Progress lines from the core are forwarded back to the UI.
3. The merged DNG is written to `files/output/merged.dng`; **Save output DNG…**
   lets the user pick a destination and copies it there.

## CI and releases

`.github/workflows/build-apk.yml` builds an APK for pull requests targeting
`main`, pushes to `main`, and manual `workflow_dispatch` runs. Only pushes to
`main` publish to the rolling **`latest`** prerelease. The stable download URL
therefore serves the latest successful main-branch build:

```
https://github.com/nikitastaf1996/HDRmerge-lite/releases/download/latest/hdrmerge-lite-latest.apk
```

The workflow:

- Runs on `ubuntu-24.04`, sets up JDK 17 (Temurin), Python 3.10 (Chaquopy's
  build interpreter, matching the app's runtime version), Android SDK 35 and
  NDK 27.1.12297006.
- Generates a fresh PKCS12 signing keystore on the runner (keystores are
  gitignored) and signs the release via the environment-driven `ciRelease`
  signing config in `app/build.gradle.kts`. The key and store passwords match,
  as required by keytool for PKCS12. Because the key changes on every run,
  Android will not accept a new build as an update to a previously installed
  build; uninstalling the old build also removes its app data.
  as required by keytool for PKCS12.
- Runs `./gradlew :app:assembleRelease --no-daemon --stacktrace` from
  `android/`, falling back to `assembleDebug` if the release build fails.
- Uploads the APK (`hdrmerge-apk`, 30-day retention) and the Gradle log
  (`build-log`, 7-day retention), including both attempts when falling back.
- Runs an Android emulator test which merges synthetic DNGs through the actual
  Kotlin-to-Python bridge; it uploads test results for seven days.
- Fails the run if no APK was produced, the upload fails, or the emulator test
  fails.
- Fails the run only if no APK was produced at all.
- Stages the APK as the stable filename `hdrmerge-lite-latest.apk` and publishes
  / updates the rolling `latest` prerelease with the commit SHA, push timestamp
  and run URL. The publish step runs only on pushes to `main` and needs
  `contents: write` at the job level.

The APK is not committed to the repository.

## Status and caveats

- The Python core and its ALGLIB fallback are tested (14 tests) and the merge
  path is validated against upstream HDRMerge on a realme RMX3871 bracket
  (see `python/README.md`).
- The Android app has **not** been built or run in this environment (no JDK /
  Android SDK available). The Gradle project is set up for Chaquopy 17.2.0 /
  AGP 8.5.2 and follows the current Chaquopy configuration; run `./gradlew` to
  build it on a machine with the toolchain above.
- The older NumPy and SciPy Android wheels used by Python 3.10 predate 16 KB
  page-size support and may fail to load on devices using 16 KB pages.
- Processing uses several times the input size in memory; check performance on
  the target device. Output is a floating-point Bayer CFA DNG, which needs a
  raw developer that supports DNG 1.4 float.

## License

GPL-3.0-or-later — see `LICENSE`. The Python core and the ALGLIB port are
adapted from HDRMerge by Javier Celaya and contributors, and from the ALGLIB
project respectively.

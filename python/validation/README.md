# Reference core comparison

This compiles the upstream C++ processing core at a pinned commit into a small CLI harness. It stubs Qt types needed by the core and hardcodes camera settings for the supplied realme RMX3871 DNG bracket; it is not a full HDRMerge executable. `compare_sample.py` decodes the sample DNGs with tifffile, supplies the raw mosaics to this core, and compares the half-float active pixels with a Python-produced DNG. Requires bash, curl, tar, g++, Python, NumPy and tifffile. Downloads are pinned by commit.

```sh
./validation/build_reference.sh /tmp/hdrmerge-reference
hdrmerge-python short.dng medium.dng long.dng -o out.dng
python validation/compare_sample.py /tmp/hdrmerge-reference/hdrref out.dng short.dng medium.dng long.dng
# Alternative without alignment, for both implementations:
hdrmerge-python --no-align short.dng medium.dng long.dng -o out-no-align.dng
NOALIGN=1 python validation/compare_sample.py /tmp/hdrmerge-reference/hdrref out-no-align.dng short.dng medium.dng long.dng
```

Metadata and raw loading are not compared: the harness sets white=1023, black=64, RGGB, and white-balance gains 1.13274336, 1, 2.46153855, exactly as observed for this bracket. A full independent application/render test is still needed.

# Logo redesign: "First Light"

Exploration and final renders for the HDRMerge Lite app logo (November 2026).

## The old logo

`ic_aperture.xml` (now removed) was a hand-authored aperture: a teal disc with
thin dark strokes. Problems, visible in `current_launcher.png` /
`current_launcher_48px.png`:

- the blade lines form an irregular tangle that reads as a scribble, not an
  iris (several tips overshoot the disc);
- strokes are ~3% of the icon width, so the glyph melts into a smear at the
  48 px launcher grid;
- nothing in it hints at HDR, exposure, or merging — the app's identity.

## Round 1 — literal (discarded)

- **A "three into one"** — three stacked photo frames, bright result frame.
- **B "refined aperture"** — hexagonal iris with a glowing opening.
- **C "exposure ramp"** — three ascending brightness steps in a viewfinder.

Rejected as *too literal*: they show what the app does but carry no story.

## Round 2 — story-driven

- **D "Totality"** (`concept_d_totality.png`) — a solar eclipse: the one
  moment the eye sees shadow and blazing light at once; HDR in nature.
- **E "First Light"** (`concept_e_first_light.png`) — **chosen.** A half-risen
  sun on a dark ridge: the scene every camera crushes to silhouette, and the
  promise that the merged frame should look the way you remember it.
- **F "Accumulated light"** (`concept_f_accumulated_light.png`) — star trails:
  many moments stacked into one frame of light.

## Final renders (from the shipped vector geometry)

| File | What it shows |
|---|---|
| `new_ic_logo_tile.png` | `ic_logo.xml` tile — in-app header + legacy (API 24–25) launcher icon |
| `new_adaptive_circle.png` | Adaptive icon under a circular mask |
| `new_adaptive_squircle.png` | Adaptive icon under a squircle mask |
| `new_48px_check.png` | Tile / circle / squircle at the 48 px launcher grid |
| `new_header_mock.png` | In-app header lockup |

Implementation: `android/app/src/main/res/drawable/ic_logo.xml` (tile),
`ic_launcher_foreground.xml` (adaptive foreground), `ic_launcher.xml`
(legacy), wired in `activity_main.xml`. Round-1 concept images were dropped
from the repo to keep it lean; this README preserves their one-line summaries.

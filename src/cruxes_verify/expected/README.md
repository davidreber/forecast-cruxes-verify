# Expected numbers

These are the numbers the paper prints, as the research code produced them
from the deduplicated pools: the headline set inclusion numbers (overlap,
permutation baseline and gap at every count of cruxes a side, for both
datasets at each of the three matching criteria) from the per question seeded
runs of 2026-09-24, and the March Madness coarser-cut sweep and within pool
split from the runs of 2026-09-23. `cruxes-verify compare` checks a rerun of
the package on the data release against them, within the tolerances of
`cruxes_verify/tolerances.py`; a rerun selects its own premises, so it is
expected to land within tolerance, not to reproduce these files exactly.

Written by `artifact_builder/build_expected.py` (authors only). Every file
here is a recorded gather converted to the package's names; `SOURCES.json`
names the recorded file behind each one with its SHA-256.

## Layout

- `runs.json`: the runs the paper prints, each a dataset, a matching
  criterion, the number of premises selected per side and the analyses
  checked on it.
- `<dataset>/<criterion>/<analysis>.json`: the paper's numbers for a run at
  25 premises a side. `<criterion>@50/` holds the run at 50 a side, which is
  where the within pool split to 25 a side comes from; its set inclusion
  file is a reference and is not checked.
- `<dataset>/dedupe.json`: how many repeated premise texts the package must
  report removing from the raw pools of the release, per pool, with the
  research code's per question counts.
- `noise/<dataset>/sample1|sample2/<criterion>/<analysis>.json`: two runs
  that differ only in an independent introspection sample. Every tolerance is
  1.5 times the largest difference between them (see `tolerances.py`).
  March Madness: the objects schema pool and its second sample, both as
  recorded before deduplication (the tolerance measures resampling, which
  deduplication does not change). Metaculus: the paper's introspected pool
  and a second one under the same protocol, both scored against the
  deduplicated extracted pool. Sample 1 is the constant seed run of
  2026-09-23 on the paper's pool; the expected numbers are the per question
  seeded run of 2026-09-24 on the same pool, which differs from it only in
  how the permutation baseline is drawn.

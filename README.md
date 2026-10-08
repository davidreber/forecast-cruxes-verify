# forecast-cruxes-verify

Verification repository for the paper "Can LLMs
Anticipate Their Cruxes?" (David Reber, James Reber, Ari Holtzman, Victor
Veitch; University of Chicago; arXiv preprint forthcoming). Companions:

- the package, https://github.com/davidreber/forecast-cruxes (`forecast-cruxes`,
  import name `cruxes`, v0.4.0, commands `cruxes-score` and `cruxes-report`);
- the data release, https://github.com/davidreber/forecast-cruxes-data.

`VERIFICATION.md` is the authors' run of this verifier on the release: the
reranker scores computed on their cluster (the GPU stage) and the reports,
comparison and verdict from this version of the verifier. Earlier runs are
kept in `verification_history/`.

**Verdict: PASSED, 109 of 109 gated checks.** Every overlap, baseline, gap, coarser-cut, split-half, repeat-count and raw-score check lands within tolerance, and the paper's permutation test (gate p < 0.01) passes in all twelve cells on the rerun and on the authors' recorded scores. The finer picture: on the recorded scores every cell has p < 1e-4; on the rerun eleven cells have p < 1e-4 and Metaculus at the broad level with 5 cruxes a side has p = 0.0019, which would fail a gate of p < 0.001. `VERIFICATION.md` has every row.

The recorded run used the authors' cluster, with torch and transformers from
the lab's conda environment (versions as recorded in `scripts/authors_cluster/`,
which names the environment but pins no versions). No run on independent
hardware or from a clean install has been made yet; the scripts and this
README are what a reader needs to make one. Paths inside `VERIFICATION.md`
are the authors' cluster paths.

**Scope.** The verifier checks the paper's headline analyses only: overlap,
permutation baseline and gap for both datasets at each of the three
strictness levels at 5 and 25 cruxes a side, the March Madness coarser-cut
(granularity) sweep, the March Madness within-pool (split-half) check at 50 a
side, the counts of removed repeats, and, with the recorded scores, raw
reranker score drift. The appendix experiments are not covered.

Check the paper from its data release, the way a reviewer would: with the
public package, on your own hardware, and nothing of the authors' but the
release.

The paper's claims rest on three parts, kept apart:

- **Inputs**, the data release: forecasts, introspected and extracted
  premises as the models produced them (repeats kept), outcomes, scouting
  reports, second introspection samples as noise references, matching
  criteria. No results. Specified in `docs/DATA_RELEASE_SPEC.md`.
- **The function**, the `forecast-cruxes` package: the method as code, generic
  (any forecaster, any forecasting question), with no data in it.
- **Results**, what the paper prints: the package run on the release.

This repository checks the third part. It runs the package on the release and
compares what comes out with the paper's numbers, which it carries itself
(`src/cruxes_verify/expected/`). It is paper specific on purpose: every piece
of knowledge about the paper's datasets, its numbers and how close a rerun
has to land lives here, and none of it in the package.

## Glossary

The verifier and the package use their own names; the paper uses these.

| here | in the paper |
|---|---|
| introspected premises | zero-shot cruxes (predicted in advance by the predictor) |
| extracted premises | many-shot cruxes (from the extractor over forecast pairs) |
| premise | crux |
| shared fraction | overlap |
| permutation null | permutation baseline |
| criteria `equivalence`, `resolution`, `debate` | strict, middle, broad matching levels |
| `contrasts_per_side`, k | cruxes a side |
| within pool split | split-half check |
| granularity sweep | coarser cuts |

## What "verified" means

Everything downstream of the recorded language model outputs is recomputed:
the removal of repeated premise texts, premise selection, the cross encoder
scores on a GPU, aggregation, clustering, the Venn decomposition, the
permutation null and the two baselines. The verdict passes only if every
gated check passes.

| check | where | tolerance | derived from |
|---|---|---|---|
| repeated premise texts the package reports removing, per pool: removed texts and questions with repeats | every run | exact | removal is deterministic; March Madness extracted 88 across 36 of 59 questions, Metaculus extracted 321 across 8 of 15, introspected none |
| shared fraction, permutation null and gap at 5 and 25 premises a side | every set inclusion run, March Madness | 0.0355 | 1.5 x 0.0237, the largest difference between two introspection samples of the objects schema pool (null at 5, debate criterion), over 18 numbers |
| the same | every set inclusion run, Metaculus | 0.1588 | 1.5 x 0.1059, the largest difference between two introspection samples under the paper's protocol, both scored on the deduplicated extracted pool (gap at 25, resolution criterion), over 18 numbers |
| the paper's test: the mean shared fraction over questions against the permutation distribution of that mean, every question's labels shuffled independently with per question seeds, 10,000 draws, p = (b + 1) / (n + 1) where b is the number of draws at or below the observed mean; observed below the null and p < 0.01, at 5 and 25 | every set inclusion run | none, must hold | the paper's stated level |
| granularity sweep: shared fraction and null at every resolution | March Madness, resolution | 0.0495 | 1.5 x 0.0330, the largest difference between the two samples' sweeps (null at resolution 0.1), over 20 numbers |
| within pool split: within introspected and within extracted overlap at 5, 12 and 25 | March Madness, resolution, 50 a side | 0.0978 | 1.5 x 0.0652, the largest difference between the two samples' splits (within introspected at 5), measured at 5 and 12, the counts both samples reach, and applied also at 25 |
| raw cross encoder scores, on premise pairs both runs scored | every run, only with `--recorded-scores` | 0.05 | 3 x the measured drift between two runs of the same pairs (0.016) |

Every tolerance on a printed number follows one rule: 1.5 times the largest
difference between two runs that differ only in an independent introspection
sample. The tolerances are computed at run time from the two samples shipped
in `src/cruxes_verify/expected/noise/`; a dataset without a second sample gets
no tolerance and the comparison stops with a message saying so. The
derivations are in `src/cruxes_verify/tolerances.py`, and the paper's test is
in `src/cruxes_verify/procedures/aggregate_null.py`.

Reported without a verdict: the set inclusion numbers of the run at 50 a side
(the paper prints that run only for its within pool split), any per question
difference in removed repeats, and, with `--recorded-scores`, the paper's
test on the authors' recorded scores (see "Reading VERIFICATION.md").

A rerun does not reproduce the paper exactly and is not expected to. The
package seeds its premise selection with its own labels and scores in fixed
batches, so it scores a different 25 of each pool on a different batch
layout. Bit exact replay of the authors' recorded matrices exists only as a
developer test, in the package for the pipeline and in `tests/` here for the
baselines.

## Requirements

- Python 3.10 or later.
- For the GPU stage (`score`), one A100-class GPU; the authors used A100 80GB
  and H200. It takes about 2.5 minutes per March Madness question at 25 a
  side and four times that at 50 a side: roughly 3 x 2.5 hours for the three
  March Madness runs at 25, about 10 hours for the run at 50, plus the
  Metaculus runs. Under `all` these run one after another; `--run` and the
  array options below split them across jobs.
- The first `score` downloads Qwen/Qwen3-Reranker-8B at the pinned revision
  `5fa94080caafeaa45a15d11f969d7978e087a3db`, about 16 GB.
- The CPU stages (`prepare`, `report`, `compare`) need no GPU and, besides the
  two packages, only numpy and scipy (matplotlib for the figures).

## Install

```
pip install 'forecast-cruxes[gpu] @ git+https://github.com/davidreber/forecast-cruxes@v0.4.0'
git clone https://github.com/davidreber/forecast-cruxes-verify && cd forecast-cruxes-verify && pip install -e .
pip install -e '.[figures]'               # to redraw the paper's figures
pip install -e '.[test]'                  # to run the tests
```

The package is not on PyPI; this repository pins the same tag as a
dependency, and the first line adds the GPU extras (torch, transformers).

## Data

```
git clone https://github.com/davidreber/forecast-cruxes-data RELEASE
```

About 50 MB. `cruxes-verify` takes the clone as it is: dot directories such
as `.git/` are ignored by the manifest check.

## Run

```
cruxes-verify check   --artifact RELEASE                    # manifest hashes only
cruxes-verify prepare --artifact RELEASE --work-dir WORK    # the package's input files
cruxes-verify score   --artifact RELEASE --work-dir WORK    # GPU, cruxes-score per run
cruxes-verify report  --artifact RELEASE --work-dir WORK    # CPU, cruxes-report and the baselines per run
cruxes-verify compare --artifact RELEASE --work-dir WORK --recorded-scores RELEASE/provenance/scores   # the verdict
cruxes-verify all     --artifact RELEASE --work-dir WORK    # everything, in order
python -m cruxes_verify.figures.render --work-dir WORK      # the paper's figures, rerun and paper side by side
```

`WORK` is an empty directory. `--recorded-scores RELEASE/provenance/scores`
(on `compare` or `all`) adds the raw score check against the authors'
recorded reranker scores, which ship in the data release under
`provenance/scores/`, and the paper's test on those recorded scores; without
it, both are skipped. `--n-permutations N` (on `compare` or `all`) sets the
number of draws of the paper's test (default 10,000).

The runs are the ones the paper prints, listed in
`src/cruxes_verify/expected/runs.json`: each dataset under each of the three
matching criteria at 25 premises a side, and March Madness under the
resolution criterion at 50 a side (named `march_madness/resolution@50`), which
is where the within pool split to 25 a side comes from. `--run NAME`
(repeatable) restricts score, report and compare to some runs. `--array-task-id
I --num-array-tasks N` makes score do every N-th question of each run starting
at I, so one large run can be split across GPU jobs:

```
cruxes-verify score --artifact RELEASE --work-dir WORK --run march_madness/resolution@50 --array-task-id 0 --num-array-tasks 4
```

The verdict is written to `WORK/verification/verification_<timestamp>.{md,json}`,
listing every tolerance with its derivation and every check with the paper's
value, the rerun's, their difference and the tolerance. The exit status is 0
only if every gated check passed. The figures go to `WORK/figures/`, with the
same figures drawn from the paper's numbers in `WORK/figures/paper/`.

**On the authors' cluster.** The Slurm jobs that produced `VERIFICATION.md`
are in `scripts/authors_cluster/` (its README lists them). They are the
record of that run, not a recipe: paths, partitions and the lab conda
environment are site specific, and each job sources `common.sh` by its
absolute cluster path, because `sbatch` runs a spooled copy of the script.

## Reading VERIFICATION.md

`VERIFICATION.md` is the verdict file of the recorded run, copied verbatim.
It lists every tolerance with its derivation, then, run by run, every gated
check with the paper's value, the rerun's, their difference and the
tolerance, and whether it passed. The verdict passes only if every gated
check does, which is also what the exit status of `compare` says (0 for
pass).

For the paper's test, the paper column states the claim (p < 0.01, observed
below the null) and, in parentheses, the p value of the same test on the
authors' recorded scores. The value marked "recorded scores, per question
seeds" is the one the paper prints; the one marked "earlier calibration with
constant seed 42" is kept for comparison only. The rerun column is the test
on the rerun's own scores, and that is what the gate checks. The values in
parentheses appear only when `compare` was given `--recorded-scores`.

## The expected numbers

`src/cruxes_verify/expected/` holds the numbers the paper prints: the
research code's runs on the deduplicated pools (the headline set inclusion
numbers from the per question seeded runs of 2026-09-24, which are the
numbers of the paper's matching-criteria table; the March Madness coarser-cut
sweep and within pool split from the runs of 2026-09-23), converted to the
package's names, with the two sample runs per dataset that set the
tolerances. They are package data of this repository, so a reviewer has them
with the verifier. Its README and `SOURCES.json` name the recorded file
behind each one.

## The data release

Layout and contents: `docs/DATA_RELEASE_SPEC.md`. The verifier reads only the
release directory and the expected numbers, and writes only the work
directory.

`artifact_builder/` holds the authors' tools, which read their internal runs
and cannot run elsewhere; they are kept so that readers can audit how the
release and the expected numbers were derived (see `artifact_builder/README.md`).
`cruxes-verify` never imports them, and a test asserts that no verifier module
mentions them or any internal path.

## Metaculus questions

The Metaculus dataset ships our premises and forecasts, each question's
Metaculus post id (`datasets/metaculus/metaculus_post_ids.json`) and our
recorded title, but not the Metaculus content itself. Metaculus content is
proprietary; its terms of use allow automated access only through the API
Metaculus provides and grant no license to redistribute it with attribution.
`datasets/metaculus/fetch_metaculus.py` (the canonical copy; this
repository's `scripts/fetch_metaculus.py` is the one the builder copies in)
reads from the API what your account token is shown:

```
export METACULUS_API_TOKEN=...      # free: your Metaculus account settings (or --env-file .env)
cd RELEASE/datasets/metaculus
python fetch_metaculus.py --dry-run --post-id 42119       # see what the API returns
python fetch_metaculus.py                                 # all questions, one request per 4 s
```

The API refuses anonymous requests, so a token is needed; the script reads it
from `--env-file` (a `KEY=VALUE` file), `METACULUS_API_TOKEN` or
`METACULUS_API_KEY`, and never prints it. An ordinary account token is shown
the titles, times and status of these questions but not, since they are all
resolved, their text or resolution, and no community forecast; each file
lists what the API withheld in `withheld_by_api`, and fuller access is by
request to Metaculus. The release therefore marks the question text and
resolution as pending written permission from Metaculus. Verification does
not need them, since it reads the premises.

The script writes one file per question, named by the release's
`question_id`, plus `fetch_log.json`, into `metaculus_fetched/` next to the
ids file unless `--out` says otherwise, and records whether each post's title
still matches the question id. `cruxes-verify check` ignores
`datasets/*/metaculus_fetched/`, so fetching inside the release does not break
the check. `--snapshot-dir` reads a frozen copy instead of the network, for
the case where Metaculus has given written permission to ship one
(`datasets/metaculus/metaculus_snapshot/`, empty otherwise). Details:
`docs/DATA_RELEASE_SPEC.md`, section "Metaculus ids and the fetch step".

## Tests

```
pip install -e '.[test]'     # after the package (see Install)
pytest tests                 # CPU only: a synthetic release and synthetic expected numbers, no model, no network
```

The suite also reads the shipped expected numbers and checks that the
tolerances computed from them are the measured ones.

## Licence

MIT, see `LICENSE`.

## Citation

```bibtex
@misc{reber2026cruxes,
  title  = {Can {LLMs} Anticipate Their Cruxes?},
  author = {Reber, David and Reber, James and Holtzman, Ari and Veitch, Victor},
  year   = {2026},
  note   = {arXiv preprint forthcoming}
}
```

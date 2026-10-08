"""Write the paper's expected numbers into the verifier's package data.

AUTHORS ONLY. Like ``build_release.py`` this reads our internal runs, read
only, and ``verify`` never imports it.

    python artifact_builder/build_expected.py

writes ``src/cruxes_verify/expected/`` (or ``--out DIR``), which must not
exist yet. Its contents are the numbers the paper prints, as the research code
produced them from the deduplicated pools (the headline set inclusion numbers
from the per question seeded runs of 2026-09-24, the March Madness coarser-cut
sweep and within pool split from the runs of 2026-09-23), converted to the
package's names, plus the two sample runs every tolerance is measured from.
The files are small (the research code's gathers, not score matrices) and are
committed to this repository, so a reviewer has them with the verifier and
never needs anything of ours beyond the data release.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from legacy import convert_gather, sha256

PROJECT = Path("/net/projects/veitch/forecast-cruxes")
RUNS = PROJECT / "Data" / "runs"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "cruxes_verify" / "expected"

MM_DEDUP = RUNS / "march_madness_objects59_dedup"
META_DEDUP = RUNS / "02_28_26_gpt-5-nano_OpenAI-search_dedup"
#: The per question seeded runs of 2026-09-24 on the same deduplicated pools: the
#: headline numbers the paper prints (its matching criteria table).
MM_SEEDED = RUNS / "march_madness_objects59_dedup_seedcheck"
META_SEEDED = RUNS / "02_28_26_gpt-5-nano_OpenAI-search_dedup_seedcheck"
MM_SAMPLE1 = RUNS / "march_madness_objects59" / "apriori"
MM_SAMPLE2 = RUNS / "march_madness_objects59_rep2" / "apriori"
META_SAMPLE2 = RUNS / "02_28_26_gpt-5-nano_OpenAI-search_rep2" / "apriori"

#: The runs the paper prints. The count is the package's max_contrasts_per_side.
RUNS_THE_PAPER_PRINTS = [
    {"dataset": "march_madness", "criterion": "resolution", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion", "granularity_sweep"]},
    {"dataset": "march_madness", "criterion": "resolution", "max_contrasts_per_side": 50,
     "analyses": ["within_pool_split"]},
    {"dataset": "march_madness", "criterion": "equivalence", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
    {"dataset": "march_madness", "criterion": "debate", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
    {"dataset": "metaculus", "criterion": "resolution", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
    {"dataset": "metaculus", "criterion": "equivalence", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
    {"dataset": "metaculus", "criterion": "debate", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
]

_MM = MM_DEDUP / "apriori"
_META = META_DEDUP / "apriori"
_MM_SEEDED = MM_SEEDED / "apriori"
_META_SEEDED = META_SEEDED / "apriori"
META_SAMPLE1_FILES = {
    "resolution": _META / "set_inclusion_all_p1_pos_only_2026-09-23T16-50-14.json",
    "equivalence": _META / "set_inclusion_all_p0_pos_only_2026-09-23T16-52-02.json",
    "debate": _META / "set_inclusion_all_p9_pos_only_2026-09-23T16-50-42.json",
}

#: Path inside expected/ -> the recorded gather it is converted from.
EXPECTED_FILES = {
    "march_madness/resolution/set_inclusion.json": _MM_SEEDED / "set_inclusion_resolved_p1_pos_only_seed-per_question_2026-09-24T11-33-02.json",
    "march_madness/resolution/granularity_sweep.json": _MM / "granularity_sweep_resolved_p1_pos_only_2026-09-23T17-35-08.json",
    "march_madness/resolution@50/within_pool_split.json": _MM / "within_set_baseline_resolved_p1_pos_only_2026-09-23T20-11-45.json",
    "march_madness/resolution@50/set_inclusion.json": _MM / "set_inclusion_resolved_p1_pos_only_2026-09-23T20-11-45.json",
    "march_madness/equivalence/set_inclusion.json": _MM_SEEDED / "set_inclusion_resolved_p0_pos_only_seed-per_question_2026-09-24T11-32-38.json",
    "march_madness/debate/set_inclusion.json": _MM_SEEDED / "set_inclusion_resolved_p9_pos_only_seed-per_question_2026-09-24T11-32-34.json",
    "metaculus/resolution/set_inclusion.json": _META_SEEDED / "set_inclusion_all_p1_pos_only_seed-per_question_2026-09-24T11-21-11.json",
    "metaculus/equivalence/set_inclusion.json": _META_SEEDED / "set_inclusion_all_p0_pos_only_seed-per_question_2026-09-24T11-21-12.json",
    "metaculus/debate/set_inclusion.json": _META_SEEDED / "set_inclusion_all_p9_pos_only_seed-per_question_2026-09-24T11-21-45.json",
}

#: The two sample runs each tolerance is measured from (tolerances.py).
NOISE_FILES = {
    "noise/march_madness/sample1/resolution/set_inclusion.json": MM_SAMPLE1 / "set_inclusion_resolved_p1_pos_only_2026-09-21T23-05-20.json",
    "noise/march_madness/sample1/equivalence/set_inclusion.json": MM_SAMPLE1 / "set_inclusion_resolved_p0_pos_only_2026-09-21T23-22-50.json",
    "noise/march_madness/sample1/debate/set_inclusion.json": MM_SAMPLE1 / "set_inclusion_resolved_p9_pos_only_2026-09-21T23-29-42.json",
    "noise/march_madness/sample1/resolution/granularity_sweep.json": MM_SAMPLE1 / "granularity_sweep_resolved_p1_pos_only_2026-09-21T23-05-20.json",
    "noise/march_madness/sample1/resolution/within_pool_split.json": MM_SAMPLE1 / "within_set_baseline_resolved_p1_pos_only_2026-09-21T23-05-20.json",
    "noise/march_madness/sample2/resolution/set_inclusion.json": MM_SAMPLE2 / "set_inclusion_resolved_p1_pos_only_2026-09-22T14-17-32.json",
    "noise/march_madness/sample2/equivalence/set_inclusion.json": MM_SAMPLE2 / "set_inclusion_resolved_p0_pos_only_2026-09-22T14-27-11.json",
    "noise/march_madness/sample2/debate/set_inclusion.json": MM_SAMPLE2 / "set_inclusion_resolved_p9_pos_only_2026-09-22T14-38-08.json",
    "noise/march_madness/sample2/resolution/granularity_sweep.json": MM_SAMPLE2 / "granularity_sweep_resolved_p1_pos_only_2026-09-22T14-17-33.json",
    "noise/march_madness/sample2/resolution/within_pool_split.json": MM_SAMPLE2 / "within_set_baseline_resolved_p1_pos_only_2026-09-22T14-17-33.json",
    **{f"noise/metaculus/sample1/{c}/set_inclusion.json": p for c, p in META_SAMPLE1_FILES.items()},
    "noise/metaculus/sample2/resolution/set_inclusion.json": META_SAMPLE2 / "set_inclusion_all_p1_pos_only_2026-09-23T18-22-49.json",
    "noise/metaculus/sample2/equivalence/set_inclusion.json": META_SAMPLE2 / "set_inclusion_all_p0_pos_only_2026-09-23T18-12-26.json",
    "noise/metaculus/sample2/debate/set_inclusion.json": META_SAMPLE2 / "set_inclusion_all_p9_pos_only_2026-09-23T18-12-26.json",
}

#: The research code's record of the repeats it removed, per dataset.
DEDUPE_MANIFESTS = {
    "march_madness": MM_DEDUP / "dedup_manifest.json",
    "metaculus": META_DEDUP / "dedup_manifest.json",
}

#: The removed-repeat counts the paper reports. The manifests must agree.
RULED_DEDUPE_COUNTS = {
    "march_madness": {"removed": {"introspected": 0, "extracted": 88},
                      "questions_with_repeats": {"introspected": 0, "extracted": 36}},
    "metaculus": {"removed": {"introspected": 0, "extracted": 321},
                  "questions_with_repeats": {"introspected": 0, "extracted": 8}},
}

#: Above this total the noise files lose their per question records; the
#: tolerances need only the summaries.
SIZE_LIMIT_BYTES = 25_000_000

POOLS = ("introspected", "extracted")

README = """# Expected numbers

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
{size_note}"""


def load(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def dedupe_expectation(manifest: dict, source: Path) -> dict:
    """The research code's dedup manifest in the package's report vocabulary."""
    summary = manifest["summary"]
    per_question = {}
    for question_id, pools in sorted(manifest["per_question"].items()):
        per_question[question_id] = {
            pool: {
                "given": pools[pool]["pool_size"],
                "kept": pools[pool]["distinct"],
                "removed": pools[pool]["removed"],
            }
            for pool in POOLS
        }
    return {
        "rule": manifest["rule"],
        "removed": {pool: summary[pool]["removed_total"] for pool in POOLS},
        "questions_with_repeats": {pool: summary[pool]["questions_with_repeats"] for pool in POOLS},
        "per_question": per_question,
        "source": {"path": str(source), "sha256": sha256(source)},
    }


def check_ruled_counts(dataset: str, expectation: dict) -> None:
    ruled = RULED_DEDUPE_COUNTS[dataset]
    found = {k: expectation[k] for k in ruled}
    if found != ruled:
        raise ValueError(f"{dataset}: the dedup manifest says {found}, the ruling says {ruled}")


def without_per_question(result: dict) -> dict:
    """A copy with every per question record removed, summaries kept."""
    if isinstance(result, dict):
        return {k: without_per_question(v) for k, v in result.items() if k != "per_question"}
    if isinstance(result, list):
        return [without_per_question(v) for v in result]
    return result


def serialize(payload) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def build(out: Path) -> dict:
    """Write everything into ``out``, which must not exist. Returns SOURCES."""
    if out.exists():
        raise FileExistsError(f"{out} exists; remove it (git rm) before rebuilding")

    texts, sources = {}, {}
    for relative, path in {**EXPECTED_FILES, **NOISE_FILES}.items():
        texts[relative] = convert_gather(load(path), path)
        sources[relative] = {"path": str(path), "sha256": sha256(path)}
    for dataset, path in DEDUPE_MANIFESTS.items():
        expectation = dedupe_expectation(load(path), path)
        check_ruled_counts(dataset, expectation)
        texts[f"{dataset}/dedupe.json"] = expectation
        sources[f"{dataset}/dedupe.json"] = {"path": str(path), "sha256": sha256(path)}
    texts["runs.json"] = RUNS_THE_PAPER_PRINTS
    sources["runs.json"] = {"path": "artifact_builder/build_expected.py", "sha256": None}

    serialized = {k: serialize(v) for k, v in texts.items()}
    total = sum(len(s.encode("utf-8")) for s in serialized.values())
    size_note = ""
    if total > SIZE_LIMIT_BYTES:
        for relative in NOISE_FILES:
            serialized[relative] = serialize(without_per_question(texts[relative]))
        size_note = (
            "\nThe noise files carry summaries only: with their per question records "
            f"the directory was {total / 1e6:.1f} MB, above the {SIZE_LIMIT_BYTES / 1e6:.0f} MB "
            "limit, and the tolerances need only the summaries.\n"
        )

    out.mkdir(parents=True)
    for relative, text in sorted(serialized.items()):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    with open(out / "SOURCES.json", "x", encoding="utf-8") as handle:
        handle.write(serialize(sources))
    with open(out / "README.md", "x", encoding="utf-8") as handle:
        handle.write(README.format(size_note=size_note))
    written = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"wrote {len(serialized) + 2} files, {written / 1e6:.2f} MB, into {out}")
    return sources


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        build(args.out)
    except (FileExistsError, ValueError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The reviewer's rerun: the data release in, the package's own outputs out.

Three steps, each a thin call into the ``forecast-cruxes`` package exactly as
its README tells a stranger to use it:

prepare
    The adapter. Turn each dataset's premise pools, as produced and with their
    repeats, into the package's premise file, and each matching criterion into
    the package's criterion file. The package removes repeated premise texts
    itself and reports how many it removed. No March Madness or Metaculus
    knowledge is needed for this; a dataset is a directory of fixed files.
score (GPU)
    ``cruxes-score`` for every run the paper prints (``expected.runs()``),
    optionally one slice of the questions per call, so a large run can be
    split across GPU jobs.
report (CPU)
    ``cruxes-report`` for the same runs; then each further analysis the run
    lists, which are procedures composed from the package's primitives in
    ``procedures/`` rather than package code.

Everything is written under the work directory. The release is read only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cruxes.runplan import add_shared_arguments, plan, settings_from_args

from .artifact import Artifact
from .expected import Expected, Run

__all__ = ["WorkDir", "prepare", "score", "report", "select_runs", "planned"]


class WorkDir:
    """Where the rerun writes. Paths only; nothing here computes."""

    def __init__(self, root):
        self.root = Path(root)

    def premises(self, dataset: str) -> Path:
        return self.root / "premises" / f"{dataset}.json"

    def criterion(self, name: str) -> Path:
        return self.root / "criteria" / f"{name}.json"

    @property
    def caches(self) -> Path:
        # One directory for every run: the cache key carries the instruction
        # texts and the premises, so nothing can collide.
        return self.root / "caches"

    def reports(self, run: Run) -> Path:
        return self.root / "reports" / run.name

    def latest_report(self, run: Run, analysis: str = "set_inclusion"):
        found = sorted(self.reports(run).glob(f"{analysis}_*.json"))
        return found[-1] if found else None


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise FileExistsError(f"{path} exists with different content; use a new work directory")
        return
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)


def select_runs(expected: Expected, artifact: Artifact, only=None) -> list:
    """The runs to do, all of them unless ``only`` names some.

    Every run must be computable from the release: its dataset a dataset of
    the release, its criterion one of the release's criteria.
    """
    runs = expected.runs()
    if only:
        wanted = set(only)
        runs = [r for r in runs if r.name in wanted]
        unknown = wanted - {r.name for r in runs}
        if unknown:
            raise ValueError(f"not a run of the expected numbers: {sorted(unknown)}")
    datasets, criteria = set(artifact.datasets()), set(artifact.criteria())
    for run in runs:
        if run.dataset not in datasets or run.criterion not in criteria:
            raise ValueError(
                f"the expected numbers call for {run.name}, but the release holds datasets "
                f"{sorted(datasets)} and criteria {sorted(criteria)}"
            )
    return runs


def prepare(artifact: Artifact, work: WorkDir) -> list:
    """Write the package's input files for every dataset and criterion."""
    written = []
    for dataset in artifact.datasets():
        question_ids = artifact.dataset(dataset)["question_ids"]
        introspected, extracted = artifact.pools(dataset)
        questions = [
            {
                "question_id": q,
                "introspected": introspected[q],
                "extracted": extracted[q],
            }
            for q in question_ids
        ]
        _write(work.premises(dataset), {"dataset": dataset, "questions": questions})
        written.append(work.premises(dataset))
    for name, criterion in artifact.criteria().items():
        _write(
            work.criterion(name),
            {
                "name": name,
                "positive_instruction": criterion["positive_instruction"],
                "negative_instruction": criterion["negative_instruction"],
            },
        )
        written.append(work.criterion(name))
    return written


def _shared_args(run: Run, work: WorkDir) -> list:
    return [
        "--premises", str(work.premises(run.dataset)),
        "--cache-dir", str(work.caches),
        "--matching-criterion", str(work.criterion(run.criterion)),
        "--max-contrasts-per-side", str(run.max_contrasts_per_side),
    ]


def planned(run: Run, work: WorkDir) -> list:
    """The package's own plan of a run: every question, its selection's key, its repeats."""
    parser = argparse.ArgumentParser()
    add_shared_arguments(parser)
    args = parser.parse_args(_shared_args(run, work))
    return plan(args.premises, settings_from_args(args))


def score(
    runs: list,
    work: WorkDir,
    dry_run: bool = False,
    array_task_id: int | None = None,
    num_array_tasks: int | None = None,
) -> int:
    """The package's GPU command, once per run. Returns the first failing status.

    With ``array_task_id`` and ``num_array_tasks`` each call scores every
    ``num_array_tasks``-th question starting at ``array_task_id``, which is
    how one large run is split across GPU jobs.
    """
    from cruxes.reranker.score import main as score_main

    if (array_task_id is None) != (num_array_tasks is None):
        raise ValueError("--array-task-id and --num-array-tasks go together")
    extra = ["--dry-run"] if dry_run else []
    if array_task_id is not None:
        extra += ["--array-task-id", str(array_task_id), "--num-array-tasks", str(num_array_tasks)]
    for run in runs:
        print(f"== score {run.name}", flush=True)
        status = score_main(_shared_args(run, work) + extra)
        if status:
            return status
    return 0


def report(runs: list, work: WorkDir) -> int:
    """The package's CPU command, once per run, then the run's further analyses."""
    from cruxes.report import main as report_main

    from .procedures.paper_baselines import ANALYSES

    for run in runs:
        print(f"== report {run.name}", flush=True)
        status = report_main(_shared_args(run, work) + ["--out-dir", str(work.reports(run))])
        if status:
            return status
        for analysis in run.analyses:
            if analysis == "set_inclusion":
                continue
            print(f"== {analysis} {run.name}", flush=True)
            ANALYSES[analysis](
                planned(run, work), work.caches, work.latest_report(run), work.reports(run)
            )
    return 0

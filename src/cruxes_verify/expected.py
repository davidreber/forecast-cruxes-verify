"""The paper's numbers, shipped with the verifier as package data.

The data release holds inputs only. What the paper prints is a result of
running the package on those inputs, so the numbers a rerun is checked
against live here, in ``cruxes_verify/expected/``, beside the code that checks
them. The directory's README says where they come from; this module only
reads them.

Layout, relative to the directory:

``runs.json``
    The runs the paper prints: dataset, matching criterion, premises selected
    per side, and the analyses checked on each.
``<run name>/<analysis>.json``
    The paper's numbers for one run, in the package's report format. A run's
    name is ``dataset/criterion``, with ``@<count>`` appended when it selects
    other than the paper's headline count of premises per side.
``<dataset>/dedupe.json``
    How many repeated premise texts the package must report removing.
``noise/<dataset>/<sample>/<criterion>/<analysis>.json``
    Two runs differing only in an independent introspection sample, from
    which ``tolerances.py`` derives every tolerance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

__all__ = ["Expected", "ExpectedError", "Run", "HEADLINE_COUNT", "NOISE_SAMPLES"]

#: The number of premises per side the paper's headline runs select.
HEADLINE_COUNT = 25

#: The two samples every tolerance compares.
NOISE_SAMPLES = ("sample1", "sample2")


class ExpectedError(ValueError):
    """An expected file is missing or malformed."""


@dataclass(frozen=True)
class Run:
    """One run the paper prints: a dataset under a criterion at a selection size."""

    dataset: str
    criterion: str
    max_contrasts_per_side: int
    analyses: tuple

    @property
    def name(self) -> str:
        base = f"{self.dataset}/{self.criterion}"
        if self.max_contrasts_per_side == HEADLINE_COUNT:
            return base
        return f"{base}@{self.max_contrasts_per_side}"


class Expected:
    """Read the expected numbers. ``root`` overrides the shipped directory (tests)."""

    def __init__(self, root=None):
        self.root = Path(root) if root is not None else files("cruxes_verify") / "expected"
        if not (self.root / "runs.json").is_file():
            raise ExpectedError(f"{self.root} has no runs.json; is it an expected numbers directory?")

    def __str__(self) -> str:
        return str(self.root)

    def _load(self, relative: str):
        path = self.root / relative
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def runs(self) -> list:
        """Every run the paper prints, in the order of ``runs.json``."""
        runs = []
        for record in self._load("runs.json"):
            runs.append(
                Run(
                    dataset=record["dataset"],
                    criterion=record["criterion"],
                    max_contrasts_per_side=int(record["max_contrasts_per_side"]),
                    analyses=tuple(record["analyses"]),
                )
            )
        names = [r.name for r in runs]
        if len(set(names)) != len(names):
            raise ExpectedError(f"runs.json names a run twice: {names}")
        return runs

    def run(self, name: str) -> Run:
        for run in self.runs():
            if run.name == name:
                return run
        raise ExpectedError(f"not a run of the expected numbers: {name}")

    def result(self, run, analysis: str = "set_inclusion") -> dict:
        """The paper's numbers for one analysis of one run. Raises when absent."""
        name = run.name if isinstance(run, Run) else str(run)
        result = self._load(f"{name}/{analysis}.json")
        if result is None:
            raise ExpectedError(f"no expected {analysis} for {name} under {self.root}")
        return result

    def noise(self, dataset: str, sample: str, criterion: str, analysis: str = "set_inclusion"):
        """One noise sample's numbers, or ``None`` when that sample was not shipped."""
        return self._load(f"noise/{dataset}/{sample}/{criterion}/{analysis}.json")

    def noise_criteria(self, dataset: str, analysis: str = "set_inclusion") -> list:
        """The criteria for which the first noise sample carries this analysis."""
        base = self.root / "noise" / dataset / NOISE_SAMPLES[0]
        if not base.is_dir():
            return []
        return sorted(
            entry.name for entry in base.iterdir() if (entry / f"{analysis}.json").is_file()
        )

    def dedupe_counts(self, dataset: str) -> dict:
        """``{"removed": {pool: n}, "questions_with_repeats": {pool: n}, ...}``."""
        counts = self._load(f"{dataset}/dedupe.json")
        if counts is None:
            raise ExpectedError(f"no expected dedupe counts for {dataset} under {self.root}")
        return counts

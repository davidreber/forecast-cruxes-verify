"""Run the paper's two baselines for one run of the verification, from its score caches.

Each baseline runs on its own, because the paper reports them from different
runs: the granularity sweep from the headline run at 25 premises a side, the
within pool split from a run at 50 a side, which is what a half split at 25
needs. Both read the caches the run's report read (found through the
package's own key computation), compose the baseline from the package's
primitives, and write ``granularity_sweep_{stamp}.json`` or
``within_pool_split_{stamp}.json`` beside the run's set inclusion report.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cruxes.scorecache import find_cached_scores, load_score_matrices

from .baselines import (
    granularity_sweep_for_question,
    summarize_granularity_sweep,
    summarize_within_pool_split,
    within_pool_curves_for_question,
)

__all__ = ["run_granularity_sweep", "run_within_pool_split", "ANALYSES"]


def _write_new(path: Path, payload: dict) -> None:
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, ensure_ascii=False)
    print(f"wrote {path}")


def _matrices(planned: list, cache_dir: Path):
    for entry in planned:
        question_id = entry.premise_set.question_id
        path = find_cached_scores(cache_dir, entry.key)
        if path is None:
            raise FileNotFoundError(f"no score cache for {question_id}")
        yield question_id, load_score_matrices(path, entry.pools)


def _metadata(set_inclusion_report: Path) -> tuple:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return stamp, {
        "generated": stamp,
        "set_inclusion_report": str(set_inclusion_report),
        "procedure": "cruxes_verify.procedures.baselines, composed from the package's primitives",
        "permutation_seeding": "hash of question id, count and analysis name",
    }


def run_granularity_sweep(planned: list, cache_dir: Path, set_inclusion_report: Path, out_dir: Path) -> Path:
    """The granularity sweep of every planned question's whole selection."""
    sweeps = {q: granularity_sweep_for_question(m, q) for q, m in _matrices(planned, cache_dir)}
    stamp, metadata = _metadata(set_inclusion_report)
    path = Path(out_dir) / f"granularity_sweep_{stamp}.json"
    _write_new(path, summarize_granularity_sweep(sweeps, metadata=metadata))
    return path


def run_within_pool_split(planned: list, cache_dir: Path, set_inclusion_report: Path, out_dir: Path) -> Path:
    """The within pool split of every planned question, beside the between pool numbers."""
    report = json.loads(Path(set_inclusion_report).read_text(encoding="utf-8"))
    curves = {}
    for count, entry in report["per_contrasts_per_side"].items():
        for question_id, record in entry["per_question"].items():
            curves.setdefault(question_id, {})[int(count)] = record
    within = {q: within_pool_curves_for_question(m, q) for q, m in _matrices(planned, cache_dir)}
    stamp, metadata = _metadata(set_inclusion_report)
    path = Path(out_dir) / f"within_pool_split_{stamp}.json"
    _write_new(path, summarize_within_pool_split(within, curves, metadata=metadata))
    return path


#: Analysis name, as ``runs.json`` lists it, to the procedure that computes it.
ANALYSES = {
    "granularity_sweep": run_granularity_sweep,
    "within_pool_split": run_within_pool_split,
}

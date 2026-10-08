"""Comparing the rerun with the paper's numbers, and the verdict.

The paper's numbers are the verifier's own package data (``expected.py``);
the rerun's are the reports the package wrote in the work directory. Every
gated check is reported with both numbers, their difference and the
tolerance, not only a verdict.

Gated, for every run the paper prints:

1. Removed repeats. The counts of repeated premise texts the package reports
   removing (the rerun report's ``metadata.deduplication``) equal the
   expected counts exactly: removed texts and questions with repeats, per
   pool.
2. Headline numbers, where the run's set inclusion is printed. Shared
   fraction, permutation null and gap at 5 and 25 a side, within the
   dataset's headline tolerance.
3. The paper's test, same runs. The mean shared fraction against the
   permutation distribution of that mean (``procedures/aggregate_null.py``,
   10,000 draws, p = (b + 1) / (n + 1)), observed below the null and p below
   ``CLAIM_ALPHA``, at 5 and 25 a side.
4. Granularity sweep, where printed. Shared fraction and null at every
   resolution, within the granularity tolerance.
5. Within pool split, where printed. Within introspected and within
   extracted overlap at 5, 12 and 25 a side, within the within pool
   tolerance.
6. Raw scores, only when the authors' recorded scores are given (they ship
   in the data release under ``provenance/scores/``). Wherever the rerun and the
   recorded run scored the same ordered pair of premises under the same
   criterion, the scores agree within ``RAW_SCORE_TOLERANCE``. Pairs are
   matched by premise text, because the two runs selected different premises.

Reported without a verdict: the set inclusion numbers of a run printed only
for another analysis (the run at 50 a side), and any per question difference
in the removed repeats.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from cruxes.premises import EXTRACTED, INTROSPECTED
from cruxes.scorecache import find_cached_scores, load_score_matrices, read_score_cache

from .expected import Expected, ExpectedError, Run
from .pipeline import WorkDir, planned
from .tolerances import (
    CHECKED_COUNTS,
    CLAIM_ALPHA,
    GRANULARITY_QUANTITIES,
    MEASURED_RAW_SCORE_DRIFT,
    RAW_SCORE_TOLERANCE,
    TOLERANCE_OF_ANALYSIS,
    WITHIN_POOL_CHECKED_COUNTS,
    WITHIN_POOL_QUANTITIES,
    headline_numbers,
    within_pool_rows,
)

__all__ = [
    "RecordedScores",
    "check_dedupe",
    "compare_headlines",
    "reference_headlines",
    "check_paper_test",
    "compare_granularity",
    "compare_within_pool",
    "compare_raw_scores",
    "check_claims",
    "derive_tolerances",
    "compare_all",
    "render_markdown",
    "write_verdict",
]

POOLS = (INTROSPECTED, EXTRACTED)


class RecordedScores:
    """The authors' recorded raw scores, keyed by premise text.

    Internal provenance, never part of the release:
    ``<root>/<dataset>/<criterion>/<question_id>.json``.
    """

    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"no recorded scores directory {self.root}")

    def get(self, dataset: str, criterion: str, question_id: str):
        path = self.root / dataset / criterion / f"{question_id}.json"
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)


def _within(paper, rerun, tolerance) -> dict:
    difference = rerun - paper
    return {
        "paper": paper,
        "rerun": rerun,
        "difference": difference,
        "tolerance": tolerance,
        "passed": bool(abs(difference) <= tolerance),
    }


def _missing(paper, note: str) -> dict:
    return {"paper": paper, "rerun": None, "difference": None, "tolerance": None, "passed": False, "note": note}


# 1. Removed repeats --------------------------------------------------------


def check_dedupe(expected_counts: dict, rerun_report: dict) -> tuple:
    """``(checks, reported)``: exact totals per pool, and per question differences."""
    recorded = rerun_report.get("metadata", {}).get("deduplication")
    if recorded is None:
        return {"deduplication": _missing("recorded", "the rerun report records no deduplication")}, {}
    checks = {}
    for field in ("removed", "questions_with_repeats"):
        for pool in POOLS:
            paper = expected_counts[field][pool]
            rerun = recorded.get(field, {}).get(pool)
            if rerun is None:
                checks[f"{field} {pool}"] = _missing(paper, "not in the rerun report")
            else:
                checks[f"{field} {pool}"] = _within(paper, rerun, 0)
    differing = {}
    expected_per_question = expected_counts.get("per_question", {})
    rerun_per_question = recorded.get("per_question", {})
    for question_id, pools in expected_per_question.items():
        for pool in POOLS:
            paper = pools[pool]["removed"]
            rerun = rerun_per_question.get(question_id, {}).get(pool, {}).get("removed")
            if rerun != paper:
                differing.setdefault(question_id, {})[pool] = {"paper": paper, "rerun": rerun}
    return checks, {"questions_whose_removed_count_differs": differing}


# 2. Headline numbers -------------------------------------------------------


def compare_headlines(paper: dict, rerun: dict, tolerance: float) -> dict:
    checks = {}
    for count in CHECKED_COUNTS:
        a, b = headline_numbers(paper, count), headline_numbers(rerun, count)
        for quantity in ("shared", "null", "gap"):
            checks[f"{quantity} at {count}"] = _within(a[quantity], b[quantity], tolerance)
        n_paper = paper["per_contrasts_per_side"][str(count)]["summary"]["n_questions"]
        n_rerun = rerun["per_contrasts_per_side"][str(count)]["summary"]["n_questions"]
        if n_paper != n_rerun:
            checks[f"questions at {count}"] = _within(n_paper, n_rerun, 0)
    return checks


def reference_headlines(paper: dict, rerun: dict) -> dict:
    """Shared, null and gap at every count both report among 5, 25 and the maximum; no verdict."""
    counts = sorted(
        {c for c in (*CHECKED_COUNTS, max(int(k) for k in paper["per_contrasts_per_side"]))
         if str(c) in paper["per_contrasts_per_side"] and str(c) in rerun["per_contrasts_per_side"]}
    )
    rows = {}
    for count in counts:
        a, b = headline_numbers(paper, count), headline_numbers(rerun, count)
        for quantity in ("shared", "null", "gap"):
            rows[f"{quantity} at {count}"] = {
                "paper": a[quantity], "rerun": b[quantity], "difference": b[quantity] - a[quantity],
            }
    return rows


# 3. The paper's test -------------------------------------------------------


def _rerun_matrices(run: Run, work: WorkDir) -> dict:
    out = {}
    for entry in planned(run, work):
        path = find_cached_scores(work.caches, entry.key)
        if path is None:
            raise FileNotFoundError(f"no rerun score cache for {run.name} {entry.premise_set.question_id}")
        out[entry.premise_set.question_id] = load_score_matrices(path, entry.pools)
    return out


def _recorded_matrices(recorded: RecordedScores, run: Run, question_ids: list) -> dict:
    from cruxes.scoring import ScoreMatrices

    out = {}
    for question_id in question_ids:
        scores = recorded.get(run.dataset, run.criterion, question_id)
        if scores is None:
            return {}
        out[question_id] = ScoreMatrices(
            n_introspected=len(scores["introspected"]),
            n_extracted=len(scores["extracted"]),
            **{k: scores[k] for k in ("pos_fwd", "pos_rev", "neg_fwd", "neg_rev")},
        )
    return out


def paper_test_verdict(test: dict) -> bool:
    return bool(test["observed_mean"] < test["null_mean"] and test["p_value"] < CLAIM_ALPHA)


def check_paper_test(rerun_matrices: dict, recorded_matrices: dict | None = None, n_permutations=None) -> dict:
    """The paper's aggregate permutation test on the rerun, at 5 and 25 a side.

    With the recorded matrices it is also computed on them as a calibration
    (reported, not gated), with the same per question seeding as the rerun;
    that value is what the paper prints. An earlier calibration seeded every
    question's null with the constant 42: with one seed the shuffles of every
    question come from one stream, so the draws of the mean are correlated
    across questions and the null of the mean is far wider than it should
    be. That construction is kept beside the corrected one under
    ``recorded_scores_constant_seed`` so the two can be compared.
    """
    from .procedures.aggregate_null import AGGREGATE_N_PERMUTATIONS, aggregate_permutation_test

    n = n_permutations or AGGREGATE_N_PERMUTATIONS
    out = {}
    for count in CHECKED_COUNTS:
        test = aggregate_permutation_test(rerun_matrices, count, n_permutations=n)
        calibration = (
            aggregate_permutation_test(recorded_matrices, count, n_permutations=n) if recorded_matrices else None
        )
        constant_seed = (
            aggregate_permutation_test(recorded_matrices, count, n_permutations=n, permutation_seed=lambda q, c: 42)
            if recorded_matrices else None
        )
        out[f"paper's test at {count}"] = {
            "paper": f"p < {CLAIM_ALPHA}, observed below the null",
            "rerun": test,
            "recorded_scores": calibration,
            "recorded_scores_constant_seed": constant_seed,
            "passed": paper_test_verdict(test),
        }
    return out


# 4. Granularity sweep ------------------------------------------------------


def compare_granularity(paper: dict, rerun: dict, tolerance: float) -> dict:
    rerun_rows = {round(r["resolution"], 6): r for r in rerun["per_resolution"]}
    checks = {}
    for row in paper["per_resolution"]:
        resolution = row["resolution"]
        other = rerun_rows.get(round(resolution, 6))
        for quantity in GRANULARITY_QUANTITIES:
            name = f"{quantity} at resolution {resolution}"
            if other is None:
                checks[name] = _missing(row[quantity], "the rerun sweep has no such resolution")
            else:
                checks[name] = _within(row[quantity], other[quantity], tolerance)
    return checks


# 5. Within pool split ------------------------------------------------------


def compare_within_pool(paper: dict, rerun: dict, tolerance: float) -> dict:
    paper_rows, rerun_rows = within_pool_rows(paper), within_pool_rows(rerun)
    checks = {}
    for count in WITHIN_POOL_CHECKED_COUNTS:
        for quantity in WITHIN_POOL_QUANTITIES:
            name = f"{quantity} at {count}"
            a = paper_rows.get(count, {}).get(quantity)
            b = rerun_rows.get(count, {}).get(quantity)
            if a is None:
                checks[name] = _missing(None, "the paper's numbers do not reach this count")
            elif b is None:
                checks[name] = _missing(a, "the rerun does not reach this count")
            else:
                checks[name] = _within(a, b, tolerance)
    return checks


# 6. Raw scores -------------------------------------------------------------


def _unique_index(texts: list) -> dict:
    counts = Counter(texts)
    return {t: i for i, t in enumerate(texts) if counts[t] == 1}


def compare_raw_scores(recorded: RecordedScores, run: Run, work: WorkDir) -> dict:
    """Every ordered pair both runs scored, both instructions, by premise text."""
    differences, questions_compared, questions_without_record = [], 0, 0
    per_question = {}
    for entry in planned(run, work):
        question_id = entry.premise_set.question_id
        scores = recorded.get(run.dataset, run.criterion, question_id)
        if scores is None:
            questions_without_record += 1
            continue
        path = find_cached_scores(work.caches, entry.key)
        if path is None:
            raise FileNotFoundError(f"no rerun score cache for {run.name} {question_id}")
        rerun = read_score_cache(path)
        ours = _unique_index(list(scores["introspected"]) + list(scores["extracted"]))
        theirs = _unique_index(list(rerun["key"].premises))
        common = sorted(set(ours) & set(theirs))
        local = []
        for name in ("pos_fwd", "neg_fwd"):
            a, b = np.asarray(scores[name]), np.asarray(rerun[name])
            for query in common:
                for document in common:
                    if query != document:
                        local.append(abs(a[ours[query], ours[document]] - b[theirs[query], theirs[document]]))
        per_question[question_id] = {
            "common_premises": len(common),
            "compared_scores": len(local),
            "max_abs_difference": max(local) if local else None,
        }
        differences += local
        questions_compared += 1
    values = np.asarray(differences, dtype=float)
    result = {
        "paper": "recorded scores",
        "tolerance": RAW_SCORE_TOLERANCE,
        "measured_reference_drift": MEASURED_RAW_SCORE_DRIFT,
        "questions_compared": questions_compared,
        "questions_without_recorded_scores": questions_without_record,
        "compared_scores": int(values.size),
        "per_question": per_question,
    }
    if values.size:
        largest = float(values.max())
        result.update(
            {
                "rerun": largest,
                "difference": largest,
                "max_abs_difference": largest,
                "median_abs_difference": float(np.median(values)),
                "p99_abs_difference": float(np.quantile(values, 0.99)),
                "passed": bool(largest <= RAW_SCORE_TOLERANCE),
            }
        )
    else:
        result.update(
            {"rerun": None, "difference": None, "passed": False,
             "note": "recorded scores were given but no premise pair was scored by both runs"}
        )
    return result


# All of it -----------------------------------------------------------------


def derive_tolerances(expected: Expected, runs: list) -> dict:
    """``{analysis: {dataset: tolerance}}`` for every analysis the runs check.

    Raises ``ToleranceError`` when a dataset has no noise sample for one of
    them: without a measured drift there is no tolerance to state.
    """
    tolerances = {}
    for run in runs:
        for analysis in run.analyses:
            per_dataset = tolerances.setdefault(analysis, {})
            if run.dataset not in per_dataset:
                per_dataset[run.dataset] = TOLERANCE_OF_ANALYSIS[analysis](expected, run.dataset)
    return tolerances


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _report(work: WorkDir, run: Run, analysis: str) -> tuple:
    path = work.latest_report(run, analysis)
    if path is None:
        raise FileNotFoundError(f"no {analysis} report for {run.name}; run `cruxes-verify report` first")
    return path, _load(path)


def compare_run(expected: Expected, run: Run, work: WorkDir, tolerances: dict, recorded=None, n_permutations=None) -> dict:
    report_path, rerun = _report(work, run, "set_inclusion")
    checks, reported = {}, {}
    checks["removed repeats"], reported["removed repeats"] = check_dedupe(
        expected.dedupe_counts(run.dataset), rerun
    )
    if "set_inclusion" in run.analyses:
        paper = expected.result(run, "set_inclusion")
        tolerance = tolerances["set_inclusion"][run.dataset]["tolerance"]
        checks["headline numbers"] = compare_headlines(paper, rerun, tolerance)
        recorded_matrices = None
        rerun_matrices = _rerun_matrices(run, work)
        if recorded is not None:
            recorded_matrices = _recorded_matrices(recorded, run, sorted(rerun_matrices))
        checks["the paper's test"] = check_paper_test(rerun_matrices, recorded_matrices, n_permutations)
    else:
        try:
            paper = expected.result(run, "set_inclusion")
        except ExpectedError:
            paper = None
        if paper is not None:
            reported["set inclusion, reference only"] = reference_headlines(paper, rerun)
    if "granularity_sweep" in run.analyses:
        path, sweep = _report(work, run, "granularity_sweep")
        tolerance = tolerances["granularity_sweep"][run.dataset]["tolerance"]
        checks["granularity sweep"] = compare_granularity(
            expected.result(run, "granularity_sweep"), sweep, tolerance
        )
    if "within_pool_split" in run.analyses:
        path, within = _report(work, run, "within_pool_split")
        tolerance = tolerances["within_pool_split"][run.dataset]["tolerance"]
        checks["within pool split"] = compare_within_pool(
            expected.result(run, "within_pool_split"), within, tolerance
        )
    if recorded is not None:
        checks["raw scores"] = {"max over shared premise pairs": compare_raw_scores(recorded, run, work)}
    return {"rerun_report": str(report_path), "checks": checks, "reported": reported}


def gated_results(verdict: dict) -> list:
    """Every gated check as (run, group, name, passed)."""
    out = []
    for run_name, result in verdict["runs"].items():
        for group, checks in result["checks"].items():
            for name, check in checks.items():
                out.append((run_name, group, name, check["passed"] is True))
    return out


def _package_versions() -> dict:
    """The package under test and this verifier, as installed."""
    import importlib.metadata

    versions = {}
    for distribution, module in (("forecast-cruxes", "cruxes"), ("forecast-cruxes-verify", "cruxes_verify")):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = getattr(__import__(module), "__version__", "not installed")
    return versions


def compare_all(expected: Expected, runs: list, work: WorkDir, recorded_scores=None, release=None, n_permutations=None) -> dict:
    recorded = RecordedScores(recorded_scores) if recorded_scores else None
    tolerances = derive_tolerances(expected, runs)
    verdict = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release": str(release.root) if release is not None else None,
        "release_status": release.manifest.get("release_status") if release is not None else None,
        "expected": str(expected.root),
        "recorded_scores": str(recorded.root) if recorded is not None else None,
        "versions": _package_versions(),
        "tolerances": tolerances,
        "runs": {},
    }
    for run in runs:
        verdict["runs"][run.name] = compare_run(expected, run, work, tolerances, recorded, n_permutations)
    gated = gated_results(verdict)
    verdict["gated_checks"] = len(gated)
    verdict["gated_checks_passed"] = sum(1 for g in gated if g[3])
    verdict["passed"] = bool(gated) and all(g[3] for g in gated)
    return verdict


# The verdict files ---------------------------------------------------------


def _number(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _signed(value) -> str:
    if value is None:
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:+d}"
    return f"{value:+.4f}"


def _tolerance_cell(value) -> str:
    if value is None:
        return ""
    if value == 0:
        return "exact"
    return f"{value:.4f}"


def _check_row(group: str, name: str, check: dict) -> str:
    verdict = "pass" if check["passed"] is True else "FAIL"
    if group == "the paper's test":
        rerun = check["rerun"]
        rerun_cell = (
            f"p {rerun['p_statement']}, observed {rerun['observed_mean']:.4f}, "
            f"null {rerun['null_mean']:.4f}"
        )
        calibration = check.get("recorded_scores")
        paper_cell = check["paper"]
        if calibration:
            paper_cell += f" (recorded scores, per question seeds: p {calibration['p_statement']}"
            constant = check.get("recorded_scores_constant_seed")
            if constant:
                paper_cell += f"; earlier calibration with constant seed 42: p {constant['p_statement']}"
            paper_cell += ")"
        return f"| {group} | {name} | {paper_cell} | {rerun_cell} | | none | {verdict} |"
    if group == "raw scores":
        if check.get("compared_scores"):
            rerun_cell = (
                f"max {check['max_abs_difference']:.5f}, median {check['median_abs_difference']:.5f}, "
                f"p99 {check['p99_abs_difference']:.5f} over {check['compared_scores']} scores, "
                f"{check['questions_compared']} questions"
            )
        else:
            rerun_cell = check.get("note", "")
        return f"| {group} | {name} | {check['paper']} | {rerun_cell} | | {check['tolerance']} | {verdict} |"
    note = f" ({check['note']})" if check.get("note") else ""
    return (
        f"| {group} | {name} | {_number(check['paper'])} | {_number(check['rerun'])}{note} | "
        f"{_signed(check['difference'])} | {_tolerance_cell(check['tolerance'])} | {verdict} |"
    )


def render_markdown(verdict: dict) -> str:
    lines = [
        "# Verification of the paper from the data release",
        "",
        f"Generated {verdict['generated']}.",
        "",
        f"- release: `{verdict['release']}` ({verdict['release_status']})",
        f"- expected numbers: `{verdict['expected']}`",
        "- recorded scores: "
        + (f"`{verdict['recorded_scores']}`" if verdict["recorded_scores"] else "not given, raw scores not checked"),
        "",
        f"**Overall: {'PASSED' if verdict['passed'] else 'FAILED'}** "
        f"({verdict['gated_checks_passed']} of {verdict['gated_checks']} gated checks passed).",
        "",
        "## Tolerances",
        "",
        "| check | dataset | tolerance | derivation |",
        "|---|---|---|---|",
    ]
    labels = {
        "set_inclusion": "headline numbers",
        "granularity_sweep": "granularity sweep",
        "within_pool_split": "within pool split",
    }
    for analysis, per_dataset in verdict["tolerances"].items():
        for dataset, t in per_dataset.items():
            lines.append(f"| {labels.get(analysis, analysis)} | {dataset} | {t['tolerance']:.4f} | {t['derivation']} |")
    lines += [
        "| removed repeats | every dataset | exact | removing repeated texts is deterministic |",
        f"| the paper's test | every dataset | none | observed below the null and p < {CLAIM_ALPHA} must hold (10,000 permutation draws of the mean, p = (b + 1) / (n + 1)) |",
        f"| raw scores | every dataset | {RAW_SCORE_TOLERANCE} | 3 x the measured drift between two runs of the same pairs ({MEASURED_RAW_SCORE_DRIFT}); only with recorded scores |",
        "",
    ]
    for name, result in verdict["runs"].items():
        lines += [f"## {name}", "", f"Rerun report `{result['rerun_report']}`.", ""]
        lines += [
            "| check | number | paper | rerun | difference | tolerance | |",
            "|---|---|---|---|---|---|---|",
        ]
        for group, checks in result["checks"].items():
            for check_name, check in checks.items():
                lines.append(_check_row(group, check_name, check))
        reported = result["reported"]
        differing = reported.get("removed repeats", {}).get("questions_whose_removed_count_differs")
        if differing:
            lines += ["", f"Questions whose removed count differs from the research code's: {len(differing)}."]
            for question_id, pools in sorted(differing.items()):
                lines.append(f"- {question_id}: {pools}")
        if "set inclusion, reference only" in reported:
            lines += [
                "",
                "Set inclusion of this run, reported without a verdict (the paper prints it only through the analyses above):",
                "",
                "| number | paper | rerun | difference |",
                "|---|---|---|---|",
            ]
            for key, row in reported["set inclusion, reference only"].items():
                lines.append(f"| {key} | {row['paper']:.4f} | {row['rerun']:.4f} | {row['difference']:+.4f} |")
        lines.append("")
    return "\n".join(lines)


def write_verdict(verdict: dict, work: WorkDir) -> tuple:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = work.root / "verification"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"verification_{stamp}.json"
    md_path = out / f"verification_{stamp}.md"
    with open(json_path, "x", encoding="utf-8") as handle:
        json.dump(verdict, handle, indent=1)
    with open(md_path, "x", encoding="utf-8") as handle:
        handle.write(render_markdown(verdict) + "\n")
    return json_path, md_path

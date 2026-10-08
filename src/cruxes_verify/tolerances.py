"""The tolerances, and the measurements they are derived from.

Verification is a reviewer's rerun on their own hardware, with the package's
own defaults. It cannot reproduce the paper's numbers exactly and is not meant
to: the package seeds each pool's selection with its own labels, so it scores
a different 25 of each pool than the research code did, and a GPU of another
kind or another batch composition moves every raw score slightly. A tolerance
says how far a correct rerun may land from the paper.

One rule sets every tolerance on a number the paper prints. Two runs that
differ only in an independent introspection sample are shipped with the
verifier (``expected/noise/``). Resampling which premises are used is exactly
what a new selection seed does, and a second introspection sample resamples
more than that, so the difference between the two runs is an upper reference
for the rerun's. The tolerance is 1.5 times the largest absolute difference
between the two samples over the quantities and counts the check covers. It
is computed at run time from the shipped files. A dataset or analysis without
a second sample gets no tolerance, and the comparison stops with a message
saying so.

Headline numbers (shared fraction, permutation null and the gap between them)
    At 5 and 25 premises a side (the two counts the paper's text cites),
    under all three matching criteria, so 18 compared numbers per dataset.
    March Madness: the objects schema pool (sample 1) against its second
    sample (sample 2), both as recorded before deduplication; largest
    difference 0.0237 (null at 5, debate criterion), tolerance 0.0356.
    Metaculus: the paper's introspected pool against a second one under the
    paper's protocol (gpt-5.4, prompts 0 to 10, 55 calls per question, OpenAI
    batch batch_6ab45598ade08190be679c8aac52dd14), both scored against the
    same deduplicated extracted pool; largest difference 0.1059 (gap at 25,
    resolution criterion), tolerance 0.1588. The paper's test below carries
    the verification where this tolerance is wide.

Granularity sweep
    The shared fraction and the permutation null at every resolution of the
    grid, resolution criterion, March Madness, 20 compared numbers. Largest
    difference 0.0330 (null at resolution 0.1), tolerance 0.0495.

Within pool split
    The within introspected and within extracted overlap at the checked
    counts both samples report. The checked counts are 5, 12 and 25; the two
    samples were run at 25 premises a side, so they report counts up to 12,
    and the tolerance is measured at 5 and 12 (4 compared numbers). Largest
    difference 0.0652 (within introspected at 5), tolerance 0.0978. It is
    applied at 25 as well, which only the deduplicated run at 50 a side
    reports.

Raw reranker scores (only when the authors' recorded scores are given)
    Two runs of the same pairs on the same pinned model, differing only in
    batch composition, differed by up to 0.01611 (median 0.01001; measured
    2026-09-19). The package's fixed batching against the recorded adaptive
    runs gave 0.01245 at most (an earlier build of the package). The
    tolerance is three times the larger measured drift, 0.05:
    wide enough for a different GPU, narrow enough that a wrong premise,
    prompt or revision, which moves scores by tenths, fails.

Counts of removed repeats
    Exact. Removing repeated premise texts is deterministic, so the package
    must report exactly the counts the research code found.

The paper's test
    Independent of any tolerance: at 5 and 25 a side the mean shared fraction
    must lie below the permutation distribution of the mean, one sided, with
    p below ``CLAIM_ALPHA``. The null of the mean is drawn 10,000 times with
    every question's labels shuffled independently (per question seeds), and
    p = (b + 1) / (n + 1) where b is the number of draws at or below the
    observed mean (``procedures/aggregate_null.py``).
"""

from __future__ import annotations

__all__ = [
    "MEASURED_RAW_SCORE_DRIFT",
    "RAW_SCORE_TOLERANCE",
    "TOLERANCE_MULTIPLIER",
    "CHECKED_COUNTS",
    "WITHIN_POOL_CHECKED_COUNTS",
    "WITHIN_POOL_QUANTITIES",
    "GRANULARITY_QUANTITIES",
    "CLAIM_ALPHA",
    "ToleranceError",
    "headline_numbers",
    "headline_tolerance",
    "granularity_tolerance",
    "within_pool_tolerance",
    "TOLERANCE_OF_ANALYSIS",
]

#: Largest difference between two runs of the same pairs, cache_comparison_p1.md.
MEASURED_RAW_SCORE_DRIFT = 0.01611

#: Three times the measured drift, rounded to 0.05.
RAW_SCORE_TOLERANCE = 0.05

#: Every tolerance on a printed number is this times the largest measured
#: difference between two introspection samples.
TOLERANCE_MULTIPLIER = 1.5

#: The contrast counts the paper's text cites for the headline numbers.
CHECKED_COUNTS = (5, 25)

#: The counts at which the within pool split is checked.
WITHIN_POOL_CHECKED_COUNTS = (5, 12, 25)

WITHIN_POOL_QUANTITIES = ("within_introspected_mean", "within_extracted_mean")
GRANULARITY_QUANTITIES = ("shared_frac_mean", "permutation_shared_mean")

#: The significance level the paper states for its permutation test.
CLAIM_ALPHA = 0.01


class ToleranceError(ValueError):
    """No second sample exists to derive a tolerance from."""


def headline_numbers(result: dict, count: int) -> dict:
    """Shared fraction, permutation null and gap of a set inclusion report at one count."""
    entry = result["per_contrasts_per_side"][str(count)]
    shared = entry["summary"]["shared_frac_mean"]
    null = entry["permutation"]["permutation_shared_mean"]
    return {"shared": shared, "null": null, "gap": null - shared}


def _criteria(expected, dataset: str, analysis: str) -> list:
    criteria = expected.noise_criteria(dataset, analysis)
    if not criteria:
        raise ToleranceError(
            f"{dataset} has no {analysis} noise sample under {expected.root}/noise/, so no "
            f"tolerance can be derived and its {analysis} numbers cannot be checked"
        )
    return criteria


def _samples(expected, dataset: str, criterion: str, analysis: str):
    first = expected.noise(dataset, "sample1", criterion, analysis)
    second = expected.noise(dataset, "sample2", criterion, analysis)
    if first is None or second is None:
        raise ToleranceError(
            f"{dataset}: the {analysis} noise reference under the {criterion} criterion "
            f"needs both samples under {expected.root}/noise/{dataset}/"
        )
    return first, second


def _tolerance(differences: list, what: str) -> dict:
    """``differences`` holds tuples (|difference|, quantity, where, criterion)."""
    largest, quantity, where, criterion = max(differences)
    return {
        "tolerance": TOLERANCE_MULTIPLIER * largest,
        "measured": largest,
        "compared": len(differences),
        "derivation": (
            f"{TOLERANCE_MULTIPLIER} x {largest:.4f}, the largest |sample 1 - sample 2| "
            f"between two introspection samples over {len(differences)} compared {what} "
            f"({quantity} at {where}, {criterion} criterion)"
        ),
    }


def headline_tolerance(expected, dataset: str) -> dict:
    """Shared, null and gap at 5 and 25 a side, under every criterion both samples carry."""
    differences = []
    for criterion in _criteria(expected, dataset, "set_inclusion"):
        first, second = _samples(expected, dataset, criterion, "set_inclusion")
        for count in CHECKED_COUNTS:
            a, b = headline_numbers(first, count), headline_numbers(second, count)
            for quantity in a:
                differences.append(
                    (abs(a[quantity] - b[quantity]), quantity, f"{count} a side", criterion)
                )
    return _tolerance(differences, "headline numbers")


def granularity_tolerance(expected, dataset: str) -> dict:
    """Shared fraction and permutation null at every resolution of the grid."""
    differences = []
    for criterion in _criteria(expected, dataset, "granularity_sweep"):
        first, second = _samples(expected, dataset, criterion, "granularity_sweep")
        rows_a, rows_b = first["per_resolution"], second["per_resolution"]
        if [r["resolution"] for r in rows_a] != [r["resolution"] for r in rows_b]:
            raise ToleranceError(f"{dataset}: the two granularity samples use different grids")
        for a, b in zip(rows_a, rows_b):
            for quantity in GRANULARITY_QUANTITIES:
                differences.append(
                    (
                        abs(a[quantity] - b[quantity]),
                        quantity,
                        f"resolution {a['resolution']}",
                        criterion,
                    )
                )
    return _tolerance(differences, "granularity sweep numbers")


def within_pool_rows(result: dict) -> dict:
    """``{count: row}`` of a within pool split report."""
    return {row["contrasts_per_side"]: row for row in result["per_contrasts_per_side"]}


def within_pool_tolerance(expected, dataset: str) -> dict:
    """Within pool overlap at the checked counts both samples report."""
    differences, measured_counts = [], set()
    for criterion in _criteria(expected, dataset, "within_pool_split"):
        first, second = _samples(expected, dataset, criterion, "within_pool_split")
        rows_a, rows_b = within_pool_rows(first), within_pool_rows(second)
        for count in WITHIN_POOL_CHECKED_COUNTS:
            if count not in rows_a or count not in rows_b:
                continue
            for quantity in WITHIN_POOL_QUANTITIES:
                a, b = rows_a[count][quantity], rows_b[count][quantity]
                if a is None or b is None:
                    continue
                measured_counts.add(count)
                differences.append((abs(a - b), quantity, f"{count} a side", criterion))
    if not differences:
        raise ToleranceError(
            f"{dataset}: the within pool noise samples report none of the checked counts "
            f"{list(WITHIN_POOL_CHECKED_COUNTS)}"
        )
    tolerance = _tolerance(differences, "within pool numbers")
    tolerance["measured_at_counts"] = sorted(measured_counts)
    unmeasured = [c for c in WITHIN_POOL_CHECKED_COUNTS if c not in measured_counts]
    if unmeasured:
        tolerance["derivation"] += (
            f"; measured at {sorted(measured_counts)} a side, the checked counts both "
            f"samples report, and applied also at {unmeasured}, which the samples (run at "
            "25 a side) do not reach and only the deduplicated run at 50 a side reports"
        )
    return tolerance


#: Which tolerance applies to which analysis of a run.
TOLERANCE_OF_ANALYSIS = {
    "set_inclusion": headline_tolerance,
    "granularity_sweep": granularity_tolerance,
    "within_pool_split": within_pool_tolerance,
}

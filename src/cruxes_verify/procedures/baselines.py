"""Two baselines that separate a real difference between the pools from an artefact.

A procedure composed from the package's primitives (linkage, cut at a given
count, consensus clustering, Venn decomposition, permutation null), kept here
and not in the package: the package is primitives plus one pipeline, and
these are the paper's supporting procedures (user principle, 2026-09-23).
Both reuse the score matrices of the main measurement, so neither needs any
model inference.

The granularity sweep answers the objection that the two pools might be
talking about the same things at different levels of detail. It cuts the same
dendrogram at a range of cluster counts, from a handful of broad categories to
near singletons, and reports the overlap at each. Overlap that climbs to the
null as the categories coarsen means the mismatch was granularity. A gap that
survives at coarse resolution means the two processes really did talk about
different things.

The within pool split answers the objection that any two samples of anything
would fail to overlap at this sample size. It splits one pool in half,
clusters the halves together, and measures their overlap. That is the ceiling
sampling noise alone can explain. Overlap between the pools far below it is a
real difference.
"""

from __future__ import annotations

import numpy as np

from cruxes.clustering import clusters_at_resolution, consensus_clustering, linkage_from_similarity
from cruxes.permutation import DEFAULT_N_PERMUTATIONS, permutation_null
from cruxes.premises import DEFAULT_SEED, EXTRACTED, INTROSPECTED
from cruxes.scoring import aggregate_scores
from cruxes.selection import derive_seed
from cruxes.stats import mean_and_error
from cruxes.venn import introspected_ids, venn_decomposition

__all__ = [
    "baseline_permutation_seed",
    "DEFAULT_RESOLUTION_GRID",
    "GRANULARITY_SWEEP",
    "WITHIN_POOL",
    "granularity_sweep",
    "granularity_sweep_for_question",
    "summarize_granularity_sweep",
    "within_pool_split",
    "within_pool_curves_for_question",
    "summarize_within_pool_split",
]

#: Cluster counts as a fraction of the item count, coarse first. A value of
#: 0.1 means one cluster per ten items, 1.0 means all singletons.
DEFAULT_RESOLUTION_GRID = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

#: Analysis names hashed into the permutation seeds.
GRANULARITY_SWEEP = "granularity_sweep"
WITHIN_POOL = "within_pool"


def baseline_permutation_seed(question_id: str, count: int, analysis: str) -> int:
    """Seeds for the baselines' nulls: the pipeline's hash plus the analysis name,
    so no baseline null shares a stream with the main measurement's."""
    return derive_seed(DEFAULT_SEED, question_id, count, analysis)


def granularity_sweep(
    similarity,
    ids,
    introspected: set,
    question_id: str,
    resolution_grid=DEFAULT_RESOLUTION_GRID,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    permutation_seed=baseline_permutation_seed,
) -> list:
    """Venn decomposition of the same pooled premises at several resolutions.

    Builds the dendrogram once and cuts it at each resolution in the grid.
    Returns one record per resolution in grid order, so records from different
    questions align by index and can be averaged. Below two items the sweep is
    empty. The null is drawn per resolution, because the number of clusters is
    what the null depends on most.
    """
    n_items = len(ids)
    if n_items < 2:
        return []

    _, linkage = linkage_from_similarity(np.asarray(similarity), ids)

    records = []
    for resolution in resolution_grid:
        n_clusters = max(1, min(n_items, round(resolution * n_items)))
        clusters = clusters_at_resolution(linkage, ids, n_clusters)
        records.append(
            {
                "resolution": float(resolution),
                "n_clusters": int(n_clusters),
                **venn_decomposition(clusters, introspected),
                "permutation": permutation_null(
                    clusters,
                    introspected,
                    seed=permutation_seed(question_id, n_clusters, GRANULARITY_SWEEP),
                    n_permutations=n_permutations,
                ),
            }
        )
    return records


def within_pool_split(
    block_similarity,
    block_ids,
    contrasts_per_side: int,
    question_id: str,
    pool: str,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    permutation_seed=baseline_permutation_seed,
) -> dict:
    """Overlap between two halves of one pool, averaged over random halvings.

    ``block_similarity`` is the pool's own block of the aggregated similarity
    matrix, so nothing is rescored. The first ``2 * contrasts_per_side`` items
    are clustered together and then split evenly at random many times. Because
    the clustering does not see the labels, averaging over random halvings is
    exactly the label shuffling null on that clustering, which is why this
    delegates to :func:`permutation_null`.

    Raises when the block holds fewer than ``2 * contrasts_per_side`` items,
    rather than truncating, because a truncated half split would be compared
    with a number between the pools at a different size.
    """
    needed = 2 * contrasts_per_side
    if needed > len(block_ids):
        raise ValueError(
            f"within_pool_split needs {needed} items but the block holds {len(block_ids)}"
        )

    sub_ids = list(block_ids[:needed])
    clusters, _ = consensus_clustering(np.asarray(block_similarity)[:needed, :needed], sub_ids)

    # Which half is labelled first is arbitrary: the null shuffles all ids and
    # takes the first half, so any labelled set of the right size is the same.
    null = permutation_null(
        clusters,
        set(sub_ids[:contrasts_per_side]),
        seed=permutation_seed(question_id, contrasts_per_side, f"{WITHIN_POOL}:{pool}"),
        n_permutations=n_permutations,
    )
    return {
        "contrasts_per_side": int(contrasts_per_side),
        "n_items": needed,
        "n_clusters": len(clusters),
        "within_shared_frac_mean": null["permutation_shared_mean"],
        "within_shared_frac_std": null["permutation_shared_std"],
    }


def granularity_sweep_for_question(
    matrices,
    question_id: str,
    aggregate=aggregate_scores,
    resolution_grid=DEFAULT_RESOLUTION_GRID,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    permutation_seed=baseline_permutation_seed,
) -> list:
    """Sweep one question's whole pooled selection.

    Uses every item that was scored, not the prefix at a given count, because
    the question it answers is about categories rather than sample size.
    """
    ids = matrices.item_ids
    return granularity_sweep(
        aggregate(matrices),
        ids,
        introspected_ids(ids),
        question_id,
        resolution_grid=resolution_grid,
        n_permutations=n_permutations,
        permutation_seed=permutation_seed,
    )


def within_pool_curves_for_question(
    matrices,
    question_id: str,
    aggregate=aggregate_scores,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    permutation_seed=baseline_permutation_seed,
) -> dict:
    """Half split curves for both pools of one question.

    Each pool is taken from its own diagonal block of the aggregated similarity
    matrix. The curve runs to half the items available in that pool, since a
    half split at a given count needs twice that many items.
    """
    similarity = np.asarray(aggregate(matrices), dtype=float)
    n_introspected = matrices.n_introspected
    ids = matrices.item_ids
    blocks = {
        INTROSPECTED: (similarity[:n_introspected, :n_introspected], ids[:n_introspected]),
        EXTRACTED: (similarity[n_introspected:, n_introspected:], ids[n_introspected:]),
    }
    return {
        pool: [
            within_pool_split(
                block,
                block_ids,
                count,
                question_id,
                pool,
                n_permutations=n_permutations,
                permutation_seed=permutation_seed,
            )
            for count in range(1, len(block_ids) // 2 + 1)
        ]
        for pool, (block, block_ids) in blocks.items()
    }


def summarize_granularity_sweep(
    per_question: dict, resolution_grid=DEFAULT_RESOLUTION_GRID, metadata: dict | None = None
) -> dict:
    """Average per question sweeps by grid position.

    A question whose sweep has a different length than the grid is dropped
    rather than aligned by value, because averaging records that do not share a
    resolution would mix granularities.
    """
    grid = list(resolution_grid)
    sweeps = [s for s in per_question.values() if len(s) == len(grid)]

    per_resolution = []
    for position, resolution in enumerate(grid):
        shared_mean, _, shared_se, n = mean_and_error([s[position]["shared_frac"] for s in sweeps])
        intro_mean, _, _, _ = mean_and_error(
            [s[position]["introspected_only_frac"] for s in sweeps]
        )
        extr_mean, _, _, _ = mean_and_error([s[position]["extracted_only_frac"] for s in sweeps])
        null_mean, _, null_se, _ = mean_and_error(
            [s[position]["permutation"]["permutation_shared_mean"] for s in sweeps]
        )
        clusters_mean, _, _, _ = mean_and_error([s[position]["n_clusters"] for s in sweeps])
        per_resolution.append(
            {
                "resolution": resolution,
                "n_clusters_mean": clusters_mean,
                "shared_frac_mean": shared_mean,
                "shared_frac_se": shared_se,
                "introspected_only_frac_mean": intro_mean,
                "extracted_only_frac_mean": extr_mean,
                "permutation_shared_mean": null_mean,
                "permutation_shared_se": null_se,
                "n_questions": n,
            }
        )

    combined = dict(metadata or {})
    combined.setdefault("analysis", GRANULARITY_SWEEP)
    combined["n_questions"] = len(sweeps)
    combined["resolution_grid"] = grid
    return {"metadata": combined, "per_resolution": per_resolution, "per_question": per_question}


def summarize_within_pool_split(
    per_question_within: dict,
    per_question_curves: dict,
    metadata: dict | None = None,
    with_permutation: bool = True,
) -> dict:
    """Put the within pool ceilings beside the between pool observation at each count.

    ``per_question_within`` holds :func:`within_pool_curves_for_question` per
    question and ``per_question_curves`` the ``set_inclusion_curve`` output per
    question, which is where the between pool observation and its null come
    from.
    """

    def value_at(curve, count):
        for record in curve:
            if record["contrasts_per_side"] == count:
                return record["within_shared_frac_mean"]
        return None

    longest = max((len(w[INTROSPECTED]) for w in per_question_within.values()), default=0)

    per_count = []
    for count in range(1, longest + 1):
        row = {"contrasts_per_side": count}
        for pool in (INTROSPECTED, EXTRACTED):
            mean, _, se, _ = mean_and_error(
                [value_at(w[pool], count) for w in per_question_within.values()]
            )
            row[f"within_{pool}_mean"] = mean
            row[f"within_{pool}_se"] = se
        observed = [
            per_question_curves.get(q, {}).get(count, {}).get("shared_frac")
            for q in per_question_within
        ]
        row["between_pools_observed_mean"], _, row["between_pools_observed_se"], n = (
            mean_and_error(observed)
        )
        if with_permutation:
            row["between_pools_permutation_mean"] = mean_and_error(
                [
                    per_question_curves.get(q, {})
                    .get(count, {})
                    .get("permutation", {})
                    .get("permutation_shared_mean")
                    for q in per_question_within
                ]
            )[0]
        else:
            row["between_pools_permutation_mean"] = None
        row["n_questions"] = n
        per_count.append(row)

    combined = dict(metadata or {})
    combined.setdefault("analysis", WITHIN_POOL)
    combined["n_questions"] = len(per_question_within)
    return {
        "metadata": combined,
        "per_contrasts_per_side": per_count,
        "per_question": per_question_within,
    }

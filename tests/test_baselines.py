"""Baseline tests: the granularity sweep and the within pool split.

Moved from the package with the procedures themselves (user principle,
2026-09-23: the package is primitives plus one pipeline).

All synthetic, no model inference, no file access. Updated for the
introspected/extracted vocabulary, the "resolution" record key (was "rho"),
and the required question_id and pool arguments the permutation seeding needs.
"""

import numpy as np
import pytest

from cruxes_verify.procedures.baselines import (
    DEFAULT_RESOLUTION_GRID,
    baseline_permutation_seed,
    WITHIN_POOL,
    granularity_sweep,
    summarize_granularity_sweep,
    summarize_within_pool_split,
    within_pool_curves_for_question,
    within_pool_split,
)
from cruxes.clustering import consensus_clustering
from cruxes.permutation import permutation_null


@pytest.fixture()
def cross_pool_matrix():
    """Four item union with two cross pool pairs, introspected:0 with extracted:0
    and introspected:1 with extracted:1."""
    similarity = np.array(
        [
            [1.00, 0.05, 0.90, 0.05],
            [0.05, 1.00, 0.05, 0.90],
            [0.90, 0.05, 1.00, 0.05],
            [0.05, 0.90, 0.05, 1.00],
        ]
    )
    ids = ["introspected:0", "introspected:1", "extracted:0", "extracted:1"]
    return similarity, ids, {"introspected:0", "introspected:1"}


@pytest.fixture()
def two_block_matrix():
    """Four items from one pool forming two well separated pairs."""
    similarity = np.array(
        [
            [1.00, 0.90, 0.05, 0.05],
            [0.90, 1.00, 0.05, 0.05],
            [0.05, 0.05, 1.00, 0.90],
            [0.05, 0.05, 0.90, 1.00],
        ]
    )
    return similarity, ["introspected:0", "introspected:1", "introspected:2", "introspected:3"]


# -- granularity sweep ---------------------------------------------------


def test_granularity_sweep_below_two_items_is_empty():
    assert granularity_sweep(np.array([[1.0]]), ["introspected:0"], {"introspected:0"}, "q") == []


def test_granularity_sweep_finest_shares_nothing(cross_pool_matrix):
    """At all singletons no cluster can hold both pools."""
    similarity, ids, introspected = cross_pool_matrix
    sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=200)
    finest = [e for e in sweep if e["n_clusters"] == len(ids)]
    assert finest
    assert finest[0]["shared_frac"] == pytest.approx(0.0)


def test_granularity_sweep_coarsest_shares_everything(cross_pool_matrix):
    """At one cluster both pools necessarily co-occur."""
    similarity, ids, introspected = cross_pool_matrix
    sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=200)
    coarsest = [e for e in sweep if e["n_clusters"] == 1]
    assert coarsest
    assert coarsest[0]["shared_frac"] == pytest.approx(1.0)


def test_granularity_sweep_endpoints_and_nulls(cross_pool_matrix):
    """Coarse overlap is at least fine overlap, and a null is attached to each."""
    similarity, ids, introspected = cross_pool_matrix
    sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=200)
    assert sweep[0]["shared_frac"] >= sweep[-1]["shared_frac"]
    for entry in sweep:
        assert "permutation_shared_mean" in entry["permutation"]


def test_granularity_sweep_records_align_with_the_grid(cross_pool_matrix):
    """One record per resolution, in grid order, so records average by index."""
    similarity, ids, introspected = cross_pool_matrix
    sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=50)
    assert [e["resolution"] for e in sweep] == list(DEFAULT_RESOLUTION_GRID)


def test_granularity_sweep_uses_the_given_permutation_seed(cross_pool_matrix):
    """A custom permutation_seed callable is used and changes the null."""
    similarity, ids, introspected = cross_pool_matrix
    default_sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=100)

    def other_seed(question_id, count, analysis):
        return baseline_permutation_seed(question_id, count, analysis) + 1

    other_sweep = granularity_sweep(
        similarity, ids, introspected, "q", n_permutations=100, permutation_seed=other_seed
    )
    assert any(
        a["permutation"]["permutation_shared_mean"] != b["permutation"]["permutation_shared_mean"]
        for a, b in zip(default_sweep, other_sweep)
    )


# -- within pool split -----------------------------------------------------


def test_within_pool_split_is_the_permutation_null_on_the_block(two_block_matrix):
    """The half split average is exactly the label shuffling null."""
    similarity, ids = two_block_matrix
    result = within_pool_split(
        similarity, ids, contrasts_per_side=2, question_id="q", pool="introspected", n_permutations=1000
    )
    clusters, _ = consensus_clustering(similarity[:4, :4], ids[:4])
    direct = permutation_null(
        clusters,
        set(ids[:2]),
        seed=baseline_permutation_seed("q", 2, f"{WITHIN_POOL}:introspected"),
        n_permutations=1000,
    )
    assert result["within_shared_frac_mean"] == pytest.approx(direct["permutation_shared_mean"])


def test_within_pool_split_known_value(two_block_matrix):
    """Two separated pairs split evenly give an expected overlap of two thirds.

    Of the six ways to choose two of four items, four leave both clusters mixed
    and two leave neither mixed.
    """
    similarity, ids = two_block_matrix
    result = within_pool_split(
        similarity, ids, contrasts_per_side=2, question_id="q", pool="introspected", n_permutations=2000
    )
    assert result["within_shared_frac_mean"] == pytest.approx(2 / 3, abs=0.05)
    assert result["contrasts_per_side"] == 2
    assert result["n_items"] == 4


def test_within_pool_split_raises_rather_than_truncating(two_block_matrix):
    """Asking for more items than the block holds is an error, not a silent cut."""
    similarity, ids = two_block_matrix
    with pytest.raises(ValueError):
        within_pool_split(
            similarity, ids, contrasts_per_side=3, question_id="q", pool="introspected", n_permutations=10
        )


def test_within_pool_split_bounds(two_block_matrix):
    """The fraction stays in range and the spread is non negative."""
    similarity, ids = two_block_matrix
    result = within_pool_split(
        similarity, ids, contrasts_per_side=2, question_id="q", pool="introspected", n_permutations=500
    )
    assert 0.0 <= result["within_shared_frac_mean"] <= 1.0
    assert result["within_shared_frac_std"] >= 0.0


def test_within_pool_curves_for_question_returns_both_pools():
    from cruxes.scoring import ScoreMatrices

    n = 6
    rng = np.random.default_rng(0)
    raw = rng.uniform(0.1, 0.9, size=(n, n))
    raw = (raw + raw.T) / 2
    matrices = ScoreMatrices(
        pos_fwd=raw, pos_rev=raw.T, neg_fwd=1 - raw, neg_rev=(1 - raw).T,
        n_introspected=4, n_extracted=2,
    )
    curves = within_pool_curves_for_question(matrices, "q", n_permutations=50)
    assert set(curves) == {"introspected", "extracted"}
    assert len(curves["introspected"]) == 4 // 2
    assert len(curves["extracted"]) == 2 // 2


# -- summaries ---------------------------------------------------------------


def test_summarize_granularity_sweep_has_per_resolution_and_per_question(cross_pool_matrix):
    similarity, ids, introspected = cross_pool_matrix
    sweep = granularity_sweep(similarity, ids, introspected, "q", n_permutations=50)
    summary = summarize_granularity_sweep({"q": sweep})
    assert set(summary) == {"metadata", "per_resolution", "per_question"}
    assert len(summary["per_resolution"]) == len(DEFAULT_RESOLUTION_GRID)
    assert summary["per_resolution"][0]["n_questions"] == 1


def test_summarize_within_pool_split_has_the_expected_shape(two_block_matrix):
    similarity, ids = two_block_matrix
    curve = [
        within_pool_split(
            similarity, ids, contrasts_per_side=1, question_id="q", pool="introspected", n_permutations=50
        )
    ]
    within = {"q": {"introspected": curve, "extracted": curve}}
    curves = {"q": {1: {"shared_frac": 0.5, "permutation": {"permutation_shared_mean": 0.2}}}}
    summary = summarize_within_pool_split(within, curves)
    assert set(summary) == {"metadata", "per_contrasts_per_side", "per_question"}
    row = summary["per_contrasts_per_side"][0]
    assert "within_introspected_mean" in row
    assert "within_extracted_mean" in row
    assert row["between_pools_observed_mean"] == pytest.approx(0.5)

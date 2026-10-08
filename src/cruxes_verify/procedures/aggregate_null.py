"""The paper's significance test: the mean overlap against its permutation null.

The mean shared fraction over questions is compared with the distribution of
that mean when every question's pool labels are shuffled. This procedure
computes exactly that from the package's primitives. Each question's
clustering is the pipeline's; draw ``i`` of the null shuffles every question
once, with each question's own seeded stream, and averages the shuffled
shared fractions. One sided:

    p = (b + 1) / (n + 1)

where b is the number of the n draws whose mean is at or below the observed
mean. The correction keeps p above zero: with n = 10,000 draws the smallest
reportable p is about 1e-4, and "p < 0.01" needs at most 99 draws at or below
the observed mean.
"""

from __future__ import annotations

import numpy as np

from cruxes.clustering import consensus_clustering
from cruxes.permutation import default_permutation_seed
from cruxes.scoring import aggregate_scores
from cruxes.venn import introspected_ids, venn_counts

__all__ = ["AGGREGATE_N_PERMUTATIONS", "aggregate_permutation_test"]

#: Draws of the null distribution of the mean. More than the package's per
#: question null curve (1,000) because the gate is a p value: with n draws the
#: smallest p the estimator below can report is 1 / (n + 1).
AGGREGATE_N_PERMUTATIONS = 10_000


def _clusters_at(matrices, count: int):
    similarity = np.asarray(aggregate_scores(matrices), dtype=float)
    ids = matrices.item_ids
    n_i, n_e = matrices.n_introspected, matrices.n_extracted
    indices = list(range(min(count, n_i))) + list(range(n_i, n_i + min(count, n_e)))
    sub_ids = [ids[i] for i in indices]
    clusters, _ = consensus_clustering(similarity[np.ix_(indices, indices)], sub_ids)
    return clusters, introspected_ids(sub_ids)


def aggregate_permutation_test(
    matrices_by_question: dict,
    count: int,
    n_permutations: int = AGGREGATE_N_PERMUTATIONS,
    permutation_seed=default_permutation_seed,
) -> dict:
    """Observed mean shared fraction against the null distribution of the mean.

    One sided: the p value is the fraction of permuted means at or below the
    observed mean, with the Monte Carlo correction (b + 1) / (n + 1), so it is
    never below 1 / (n + 1) and never reported as zero.
    """
    observed, null_draws = [], []
    for question_id, matrices in matrices_by_question.items():
        clusters, introspected = _clusters_at(matrices, count)
        shared, a, b = venn_counts(clusters, introspected)
        total = shared + a + b
        observed.append(shared / total if total else 0.0)

        all_ids = [item for cluster in clusters for item in cluster]
        n_introspected = len(introspected & set(all_ids))
        rng = np.random.RandomState(permutation_seed(question_id, count))
        draws = np.empty(n_permutations)
        for i in range(n_permutations):
            shuffled = all_ids.copy()
            rng.shuffle(shuffled)
            s, x, y = venn_counts(clusters, set(shuffled[:n_introspected]))
            draws[i] = s / (s + x + y) if (s + x + y) else 0.0
        null_draws.append(draws)

    observed_mean = float(np.mean(observed))
    null_means = np.mean(np.vstack(null_draws), axis=0)
    at_or_below = int(np.sum(null_means <= observed_mean))
    return {
        "contrasts_per_side": count,
        "n_questions": len(observed),
        "observed_mean": observed_mean,
        "null_mean": float(null_means.mean()),
        "null_min": float(null_means.min()),
        "draws_at_or_below_observed": at_or_below,
        "n_permutations": n_permutations,
        "p_value": (at_or_below + 1) / (n_permutations + 1),
        "p_statement": f"{(at_or_below + 1) / (n_permutations + 1):.4g} ({at_or_below} of {n_permutations} draws at or below)",
    }

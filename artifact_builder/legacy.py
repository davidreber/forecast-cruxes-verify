"""Converting recorded research files to the package's names. Authors only.

The research code wrote ``per_k``, ``k``, ``per_matchup``, ``a_only`` and so on.
The package's names are primary (review verdict Q5), so every recorded file
that enters the artifact is converted into a copy with the package's names.
The recorded original is read, never written.

Also here: the selection the research code made, so recorded score caches,
which store item ids and not text, can be written into the artifact keyed by
the premise texts they scored. The research code seeded each pool's selection
with the labels ``apriori`` and ``aposteriori``; the package uses
``introspected`` and ``extracted``, so this is the one place the old labels
survive, and only to describe what was recorded.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cruxes.selection import derive_seed, select_prefix

#: Recorded key -> package key, applied to dictionary keys at every depth.
KEY_RENAMES = {
    "per_k": "per_contrasts_per_side",
    "k": "contrasts_per_side",
    "k_max": "max_contrasts_per_side",
    "per_matchup": "per_question",
    "n_matchups": "n_questions",
    "a_only": "introspected_only",
    "b_only": "extracted_only",
    "a_only_frac": "introspected_only_frac",
    "b_only_frac": "extracted_only_frac",
    "a_only_frac_mean": "introspected_only_frac_mean",
    "a_only_frac_std": "introspected_only_frac_std",
    "a_only_frac_se": "introspected_only_frac_se",
    "b_only_frac_mean": "extracted_only_frac_mean",
    "b_only_frac_std": "extracted_only_frac_std",
    "b_only_frac_se": "extracted_only_frac_se",
    "permutation_a_only_mean": "permutation_introspected_only_mean",
    "permutation_a_only_std": "permutation_introspected_only_std",
    "permutation_b_only_mean": "permutation_extracted_only_mean",
    "permutation_b_only_std": "permutation_extracted_only_std",
    "per_rho": "per_resolution",
    "rho": "resolution",
    "rho_grid": "resolution_grid",
    "a_priori": "introspected",
    "a_posteriori": "extracted",
    "within_a_priori_mean": "within_introspected_mean",
    "within_a_priori_se": "within_introspected_se",
    "within_a_posteriori_mean": "within_extracted_mean",
    "within_a_posteriori_se": "within_extracted_se",
    "cross_set_observed_mean": "between_pools_observed_mean",
    "cross_set_observed_se": "between_pools_observed_se",
    "cross_set_permutation_mean": "between_pools_permutation_mean",
    "within_set_baseline": "within_pool",
}

#: The labels the research code hashed into each pool's selection seed.
LEGACY_SEED_LABELS = ("apriori", "aposteriori")


def rename_keys(value):
    """A deep copy with every recorded key replaced by the package's name."""
    if isinstance(value, dict):
        return {KEY_RENAMES.get(k, k): rename_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rename_keys(v) for v in value]
    return value


def convert_gather(recorded: dict, source: Path) -> dict:
    """A recorded gather in the package's format, saying where it came from."""
    converted = rename_keys(recorded)
    metadata = converted.pop("metadata", {})
    if isinstance(metadata.get("analysis"), str):
        metadata["analysis"] = KEY_RENAMES.get(metadata["analysis"], metadata["analysis"])
    converted = {
        "metadata": {
            "converted_from": str(source),
            "converted_from_sha256": sha256(source),
            "recorded_metadata": metadata,
            "permutation_seeding": "constant 42 for every null (as recorded)",
        },
        **converted,
    }
    return converted


def legacy_selection(pool: list, question_id: str, label: str, max_contrasts_per_side: int = 25, seed: int = 42) -> list:
    """The premises the research code selected from one pool of one question."""
    return select_prefix(
        pool, min(max_contrasts_per_side, len(pool)), derive_seed(seed, question_id, label)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

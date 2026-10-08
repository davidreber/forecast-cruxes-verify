"""CPU tests of the verifier on a small synthetic release and synthetic expected numbers.

Nothing here loads a model or reads the real release. A synthetic release of
the specified layout (inputs only) and a synthetic expected numbers directory
are built in a temporary directory, with score caches written through the
package's own writer to stand in for a GPU rerun. The last tests read the
expected numbers shipped with the verifier.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from cruxes import ScoreMatrices, find_cached_scores, load_premise_sets, write_score_cache
from cruxes_verify import cli, compare, tolerances
from cruxes_verify.artifact import Artifact, ArtifactError
from cruxes_verify.expected import Expected, ExpectedError, Run
from cruxes_verify.pipeline import WorkDir, planned, prepare, report, score, select_runs

SRC = Path(__file__).resolve().parents[1] / "src" / "cruxes_verify"


def _write(root: Path, relative: str, payload) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _result(shared25, null25, shared5=0.1, null5=0.3, n=6, per_question=None):
    """A set inclusion report with the numbers the checks read."""

    def entry(count, shared, null):
        pq = per_question or {
            f"q{i}": {
                "shared_frac": shared + 0.01 * (i - n / 2),
                "permutation": {"permutation_shared_mean": null},
            }
            for i in range(n)
        }
        return {
            "contrasts_per_side": count,
            "per_question": pq,
            "summary": {"shared_frac_mean": shared, "shared_frac_se": 0.02, "n_questions": n},
            "permutation": {"permutation_shared_mean": null},
        }

    return {
        "metadata": {},
        "per_contrasts_per_side": {"5": entry(5, shared5, null5), "25": entry(25, shared25, null25)},
    }


def _sweep(shared, null, grid=(0.1, 0.5, 1.0)):
    return {
        "metadata": {},
        "per_resolution": [
            {"resolution": r, "shared_frac_mean": s, "permutation_shared_mean": p}
            for r, s, p in zip(grid, shared, null)
        ],
    }


def _within(bump_at=None, bump=0.0, counts=range(1, 13)):
    rows = []
    for c in counts:
        rows.append(
            {
                "contrasts_per_side": c,
                "within_introspected_mean": 0.2 + 0.01 * c + (bump if c == bump_at else 0.0),
                "within_introspected_se": 0.01,
                "within_extracted_mean": 0.1 + 0.01 * c,
                "within_extracted_se": 0.01,
                "between_pools_observed_mean": 0.05 + 0.005 * c,
                "between_pools_observed_se": 0.01,
                "between_pools_permutation_mean": 0.1 + 0.01 * c,
            }
        )
    return {"metadata": {}, "per_contrasts_per_side": rows}


CRITERIA = {
    "primary": "resolution",
    "criteria": [
        {"name": "resolution", "positive_instruction": "same?", "negative_instruction": "different?"},
        {"name": "debate", "positive_instruction": "same debate?", "negative_instruction": "other debate?"},
    ],
}

RUNS = [
    {"dataset": "march_madness", "criterion": "resolution", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion", "granularity_sweep"]},
    {"dataset": "march_madness", "criterion": "resolution", "max_contrasts_per_side": 50,
     "analyses": ["within_pool_split"]},
    {"dataset": "march_madness", "criterion": "debate", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
    {"dataset": "metaculus", "criterion": "resolution", "max_contrasts_per_side": 25,
     "analyses": ["set_inclusion"]},
]

#: One repeated extracted premise, in one March Madness question.
DEDUPE = {
    "march_madness": {"removed": {"introspected": 0, "extracted": 1},
                      "questions_with_repeats": {"introspected": 0, "extracted": 1}},
    "metaculus": {"removed": {"introspected": 0, "extracted": 0},
                  "questions_with_repeats": {"introspected": 0, "extracted": 0}},
}


def _manifest(root: Path, spec_version=2) -> None:
    files = {
        p.relative_to(root).as_posix(): {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
            "role": "x",
        }
        for p in root.rglob("*")
        if p.is_file()
    }
    _write(root, "MANIFEST.json", {"spec_version": spec_version, "release_status": "test", "files": files})


@pytest.fixture
def release_dir(tmp_path):
    root = tmp_path / "release"
    _write(root, "method/matching_criteria.json", CRITERIA)
    for dataset, n in (("march_madness", 3), ("metaculus", 2)):
        ids = [f"{dataset}-q{i}" for i in range(n)]
        extracted = {q: [f"{q} extr {j}" for j in range(5)] for q in ids}
        if dataset == "march_madness":
            extracted[ids[1]].insert(3, f"  {ids[1]}  extr 0 ")  # a repeat, spaced differently
        _write(root, f"datasets/{dataset}/dataset.json", {"name": dataset, "question_ids": ids})
        _write(root, f"datasets/{dataset}/questions.json", [{"question_id": q} for q in ids])
        _write(root, f"datasets/{dataset}/introspected.json", {q: [f"{q} intro {j}" for j in range(4)] for q in ids})
        _write(root, f"datasets/{dataset}/extracted.json", extracted)
        _write(root, f"datasets/{dataset}/noise_reference/introspected.json", {q: [f"{q} other {j}" for j in range(4)] for q in ids})
    _manifest(root)
    return root


def _noise(root: Path) -> None:
    samples = {
        ("march_madness", "sample1", "resolution", "set_inclusion"): _result(0.14, 0.40),
        ("march_madness", "sample2", "resolution", "set_inclusion"): _result(0.13, 0.41),
        ("march_madness", "sample1", "debate", "set_inclusion"): _result(0.11, 0.40),
        # Largest headline difference: debate null at 25, 0.025.
        ("march_madness", "sample2", "debate", "set_inclusion"): _result(0.12, 0.425),
        ("march_madness", "sample1", "resolution", "granularity_sweep"): _sweep((0.3, 0.2, 0.0), (0.5, 0.3, 0.0)),
        # Largest granularity difference: null at 0.5, 0.03.
        ("march_madness", "sample2", "resolution", "granularity_sweep"): _sweep((0.31, 0.22, 0.0), (0.49, 0.33, 0.0)),
        ("march_madness", "sample1", "resolution", "within_pool_split"): _within(),
        # Largest within pool difference: introspected at 12, 0.04; 25 is not reached.
        ("march_madness", "sample2", "resolution", "within_pool_split"): _within(bump_at=12, bump=0.04),
        ("metaculus", "sample1", "resolution", "set_inclusion"): _result(0.36, 0.64),
        # Largest Metaculus difference: shared at 25, 0.04.
        ("metaculus", "sample2", "resolution", "set_inclusion"): _result(0.40, 0.66),
    }
    for (dataset, sample, criterion, analysis), payload in samples.items():
        _write(root, f"noise/{dataset}/{sample}/{criterion}/{analysis}.json", payload)


@pytest.fixture
def expected_dir(tmp_path):
    root = tmp_path / "expected"
    _write(root, "runs.json", RUNS)
    _write(root, "march_madness/resolution/set_inclusion.json", _result(0.14, 0.40))
    _write(root, "march_madness/resolution/granularity_sweep.json", _sweep((0.3, 0.2, 0.0), (0.5, 0.3, 0.0)))
    _write(root, "march_madness/resolution@50/within_pool_split.json", _within(counts=range(1, 26)))
    _write(root, "march_madness/debate/set_inclusion.json", _result(0.11, 0.40))
    _write(root, "metaculus/resolution/set_inclusion.json", _result(0.36, 0.64))
    for dataset, counts in DEDUPE.items():
        _write(root, f"{dataset}/dedupe.json", counts)
    _noise(root)
    return root


def _write_caches(work: WorkDir, runs: list, seed: int = 0) -> None:
    """Stand in for the GPU stage: random scores for every planned selection."""
    rng = np.random.default_rng(seed)
    for run in runs:
        for entry in planned(run, work):
            if find_cached_scores(work.caches, entry.key) is not None:
                continue
            n = entry.key.n_items
            pos = rng.uniform(0.1, 0.9, (n, n))
            np.fill_diagonal(pos, 1.0)
            neg = rng.uniform(0.1, 0.9, (n, n))
            np.fill_diagonal(neg, 0.0)
            write_score_cache(
                work.caches, entry.key,
                {"pos_fwd": pos, "pos_rev": pos.T, "neg_fwd": neg, "neg_rev": neg.T},
                pools=entry.pools,
            )


# The release -----------------------------------------------------------------


def test_the_manifest_check_passes_on_an_untouched_release(release_dir):
    assert Artifact(release_dir).check_manifest()["files"] > 10


def test_a_changed_file_fails_the_manifest_check(release_dir):
    target = release_dir / "datasets/metaculus/introspected.json"
    target.write_text(target.read_text().replace("intro 0", "intro X"))
    with pytest.raises(ArtifactError, match="changed"):
        Artifact(release_dir).check_manifest()


def test_an_unlisted_file_fails_the_manifest_check(release_dir):
    (release_dir / "datasets" / "extra.json").write_text("{}")
    with pytest.raises(ArtifactError, match="not in the manifest"):
        Artifact(release_dir).check_manifest()


def test_a_git_clone_of_the_release_passes_the_manifest_check(release_dir):
    git = release_dir / ".git"
    (git / "objects" / "ab").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "objects" / "ab" / "cdef").write_bytes(b"\x00")
    assert Artifact(release_dir).check_manifest()["files"] > 10


def test_files_the_metaculus_fetch_writes_inside_the_release_are_not_checked(release_dir):
    fetched = release_dir / "datasets" / "metaculus" / "metaculus_fetched"
    fetched.mkdir()
    (fetched / "fetch_log.json").write_text("{}")
    (fetched / "metaculus-q0.json").write_text("{}")
    assert Artifact(release_dir).check_manifest()["files"] > 10
    (release_dir / "datasets" / "metaculus" / "fetched_elsewhere.json").write_text("{}")
    with pytest.raises(ArtifactError, match="not in the manifest: datasets/metaculus/fetched_elsewhere.json"):
        Artifact(release_dir).check_manifest()


def test_a_release_of_another_spec_version_is_refused(release_dir):
    _manifest(release_dir, spec_version=1)
    with pytest.raises(ArtifactError, match="spec version 1"):
        Artifact(release_dir)


def test_the_release_holds_inputs_only(release_dir):
    assert not (release_dir / "results").exists() and not (release_dir / "scores").exists()
    assert not hasattr(Artifact, "result") and not hasattr(Artifact, "recorded_scores")
    introspected, extracted = Artifact(release_dir).pools("march_madness", noise_reference=True)
    assert introspected["march_madness-q0"][0] == "march_madness-q0 other 0"


def test_prepare_passes_the_raw_pools_and_the_package_removes_the_repeat(release_dir, expected_dir, tmp_path):
    artifact, work = Artifact(release_dir), WorkDir(tmp_path / "work")
    prepare(artifact, work)
    sets = load_premise_sets(work.premises("march_madness"))
    assert [s.question_id for s in sets] == ["march_madness-q0", "march_madness-q1", "march_madness-q2"]
    assert len(sets[1].extracted) == 6  # as produced, repeat kept
    run = Expected(expected_dir).run("march_madness/resolution")
    removed = {e.premise_set.question_id: e.duplicates["extracted"]["removed"] for e in planned(run, work)}
    assert removed == {"march_madness-q0": 0, "march_madness-q1": 1, "march_madness-q2": 0}
    assert json.loads(work.criterion("debate").read_text())["positive_instruction"] == "same debate?"
    prepare(artifact, work)  # idempotent on identical content


# The expected numbers --------------------------------------------------------


def test_runs_come_from_runs_json_with_the_count_in_the_name(expected_dir):
    runs = Expected(expected_dir).runs()
    assert [r.name for r in runs] == [
        "march_madness/resolution", "march_madness/resolution@50",
        "march_madness/debate", "metaculus/resolution",
    ]
    assert runs[1] == Run("march_madness", "resolution", 50, ("within_pool_split",))


def test_a_missing_expected_result_is_an_error(expected_dir):
    with pytest.raises(ExpectedError, match="no expected granularity_sweep"):
        Expected(expected_dir).result("metaculus/resolution", "granularity_sweep")


def test_an_unknown_run_is_refused(release_dir, expected_dir):
    with pytest.raises(ValueError, match="not a run"):
        select_runs(Expected(expected_dir), Artifact(release_dir), ["metaculus/debate"])


def test_a_run_the_release_cannot_serve_is_refused(release_dir, expected_dir):
    runs = RUNS + [{"dataset": "elections", "criterion": "resolution", "max_contrasts_per_side": 25, "analyses": ["set_inclusion"]}]
    _write(expected_dir, "runs.json", runs)
    with pytest.raises(ValueError, match="elections/resolution"):
        select_runs(Expected(expected_dir), Artifact(release_dir))


# Tolerances ------------------------------------------------------------------


def test_the_headline_tolerance_is_one_and_a_half_times_the_largest_sample_difference(expected_dir):
    expected = Expected(expected_dir)
    derived = tolerances.headline_tolerance(expected, "march_madness")
    assert derived["measured"] == pytest.approx(0.025)
    assert derived["tolerance"] == pytest.approx(1.5 * 0.025)
    assert derived["compared"] == 12 and "debate" in derived["derivation"]
    assert tolerances.headline_tolerance(expected, "metaculus")["tolerance"] == pytest.approx(1.5 * 0.04)


def test_the_granularity_tolerance_is_one_and_a_half_times_the_largest_sample_difference(expected_dir):
    derived = tolerances.granularity_tolerance(Expected(expected_dir), "march_madness")
    assert derived["tolerance"] == pytest.approx(1.5 * 0.03)
    assert derived["compared"] == 6


def test_the_within_pool_tolerance_is_measured_where_both_samples_reach(expected_dir):
    derived = tolerances.within_pool_tolerance(Expected(expected_dir), "march_madness")
    assert derived["tolerance"] == pytest.approx(1.5 * 0.04)
    assert derived["measured_at_counts"] == [5, 12]
    assert "applied also at [25]" in derived["derivation"]


def test_a_dataset_without_a_noise_sample_gets_no_tolerance(expected_dir):
    expected = Expected(expected_dir)
    with pytest.raises(tolerances.ToleranceError, match="metaculus has no granularity_sweep noise sample"):
        tolerances.granularity_tolerance(expected, "metaculus")
    for path in (expected_dir / "noise" / "metaculus").rglob("*.json"):
        path.unlink()
    with pytest.raises(tolerances.ToleranceError, match="no tolerance can be derived"):
        compare.derive_tolerances(expected, expected.runs())


def test_a_missing_second_sample_is_an_error(expected_dir):
    (expected_dir / "noise/march_madness/sample2/debate/set_inclusion.json").unlink()
    with pytest.raises(tolerances.ToleranceError, match="needs both samples"):
        tolerances.headline_tolerance(Expected(expected_dir), "march_madness")


# The gated checks ------------------------------------------------------------


def _report_with_dedupe(removed_extracted=1, with_repeats=1):
    return {"metadata": {"deduplication": {
        "removed": {"introspected": 0, "extracted": removed_extracted},
        "questions_with_repeats": {"introspected": 0, "extracted": with_repeats},
        "per_question": {},
    }}}


def test_the_dedupe_check_passes_on_equal_counts_and_fails_on_different_ones():
    checks, _ = compare.check_dedupe(DEDUPE["march_madness"], _report_with_dedupe())
    assert len(checks) == 4 and all(c["passed"] for c in checks.values())
    checks, _ = compare.check_dedupe(DEDUPE["march_madness"], _report_with_dedupe(removed_extracted=2))
    assert [k for k, c in checks.items() if not c["passed"]] == ["removed extracted"]
    checks, _ = compare.check_dedupe(DEDUPE["march_madness"], {"metadata": {}})
    assert not any(c["passed"] for c in checks.values())


def test_headlines_within_tolerance_pass_and_outside_fail():
    paper, close, far = _result(0.14, 0.40), _result(0.15, 0.40), _result(0.25, 0.40)
    assert all(c["passed"] for c in compare.compare_headlines(paper, close, 0.03).values())
    failed = [k for k, c in compare.compare_headlines(paper, far, 0.03).items() if not c["passed"]]
    assert failed == ["shared at 25", "gap at 25"]


def test_the_granularity_check_covers_every_resolution():
    paper = _sweep((0.3, 0.2, 0.0), (0.5, 0.3, 0.0))
    checks = compare.compare_granularity(paper, _sweep((0.32, 0.2, 0.0), (0.5, 0.3, 0.0)), 0.045)
    assert len(checks) == 6 and all(c["passed"] for c in checks.values())
    checks = compare.compare_granularity(paper, _sweep((0.3, 0.2, 0.0), (0.5, 0.4, 0.0)), 0.045)
    assert [k for k, c in checks.items() if not c["passed"]] == ["permutation_shared_mean at resolution 0.5"]
    checks = compare.compare_granularity(paper, _sweep((0.3, 0.2), (0.5, 0.3), grid=(0.1, 0.5)), 0.045)
    assert not checks["shared_frac_mean at resolution 1.0"]["passed"]


def test_the_within_pool_check_is_at_five_twelve_and_twenty_five():
    paper = _within(counts=range(1, 26))
    checks = compare.compare_within_pool(paper, _within(counts=range(1, 26), bump_at=12, bump=0.05), 0.06)
    assert sorted(checks) == sorted(
        f"{q} at {c}" for c in (5, 12, 25) for q in ("within_introspected_mean", "within_extracted_mean")
    )
    assert all(c["passed"] for c in checks.values())
    checks = compare.compare_within_pool(paper, _within(counts=range(1, 26), bump_at=25, bump=0.07), 0.06)
    assert [k for k, c in checks.items() if not c["passed"]] == ["within_introspected_mean at 25"]
    checks = compare.compare_within_pool(paper, _within(counts=range(1, 13)), 0.06)
    assert checks["within_extracted_mean at 25"]["passed"] is False


def _matrices(similar: bool, n: int = 4):
    size = 2 * n
    pos = np.full((size, size), 0.05)
    for i in range(n):
        if similar:
            pos[i, n + i] = pos[n + i, i] = 0.95
        elif i + 1 < n:
            pos[i, i + 1] = pos[i + 1, i] = 0.95
            pos[n + i, n + i + 1] = pos[n + i + 1, n + i] = 0.95
    np.fill_diagonal(pos, 1.0)
    neg = np.zeros((size, size))
    return ScoreMatrices(pos, pos.T, neg, neg.T, n, n)


def test_the_paper_test_separates_disjoint_pools_from_matching_ones():
    from cruxes_verify.procedures.aggregate_null import aggregate_permutation_test

    disjoint = aggregate_permutation_test({f"q{i}": _matrices(False) for i in range(5)}, 4, n_permutations=200)
    assert disjoint["observed_mean"] == 0.0 and disjoint["null_mean"] > 0
    matching = aggregate_permutation_test({f"q{i}": _matrices(True) for i in range(5)}, 4, n_permutations=200)
    assert matching["observed_mean"] == 1.0 and matching["p_value"] == 1.0


def test_the_paper_test_gate_needs_the_observed_mean_below_the_null():
    # p = (b + 1) / (n + 1) needs more than 1 / CLAIM_ALPHA draws to fall below the gate.
    disjoint = compare.check_paper_test({f"q{i}": _matrices(False) for i in range(8)}, n_permutations=1500)
    assert list(disjoint) == ["paper's test at 5", "paper's test at 25"]
    assert all(c["passed"] for c in disjoint.values())
    matching = compare.check_paper_test({f"q{i}": _matrices(True) for i in range(8)}, n_permutations=300)
    assert not any(c["passed"] for c in matching.values())


# The rerun, end to end on the CPU --------------------------------------------


def test_score_passes_the_array_split_to_the_package(release_dir, expected_dir, tmp_path, capsys):
    artifact, work = Artifact(release_dir), WorkDir(tmp_path / "work")
    prepare(artifact, work)
    runs = select_runs(Expected(expected_dir), artifact, ["march_madness/resolution"])
    assert score(runs, work, dry_run=True, array_task_id=1, num_array_tasks=2) == 0
    printed = capsys.readouterr().out
    assert "march_madness-q1" in printed and "march_madness-q0:" not in printed
    with pytest.raises(ValueError, match="go together"):
        score(runs, work, dry_run=True, array_task_id=1)


@pytest.fixture
def rerun(release_dir, expected_dir, tmp_path):
    artifact, expected, work = Artifact(release_dir), Expected(expected_dir), WorkDir(tmp_path / "work")
    prepare(artifact, work)
    runs = select_runs(expected, artifact)
    _write_caches(work, runs)
    assert report(runs, work) == 0
    # The paper's set inclusion and granularity numbers become the rerun's own,
    # so those checks can pass; the within pool numbers stay synthetic.
    for run in runs:
        for analysis in ("set_inclusion", "granularity_sweep"):
            path = work.latest_report(run, analysis)
            if path is not None:
                (expected_dir / run.name / f"{analysis}.json").write_text(path.read_text())
    return artifact, expected, work, runs


def test_report_writes_each_listed_analysis_in_its_own_run_directory(rerun):
    _, _, work, runs = rerun
    by_name = {r.name: r for r in runs}
    assert work.latest_report(by_name["march_madness/resolution"], "granularity_sweep") is not None
    assert work.latest_report(by_name["march_madness/resolution"], "within_pool_split") is None
    assert work.latest_report(by_name["march_madness/resolution@50"], "within_pool_split") is not None
    assert work.reports(by_name["march_madness/resolution@50"]).name == "resolution@50"
    report = json.loads(work.latest_report(by_name["march_madness/resolution"]).read_text())
    assert report["metadata"]["max_contrasts_per_side"] == 25
    assert report["metadata"]["deduplication"]["removed"]["extracted"] == 1


def test_compare_gates_every_listed_check_and_writes_the_verdict(rerun):
    artifact, expected, work, runs = rerun
    verdict = compare.compare_all(expected, runs, work, release=artifact)
    mm = verdict["runs"]["march_madness/resolution"]["checks"]
    for group in ("removed repeats", "headline numbers", "granularity sweep"):
        assert all(c["passed"] for c in mm[group].values()), group
    assert "raw scores" not in mm
    at50 = verdict["runs"]["march_madness/resolution@50"]
    assert set(at50["checks"]) == {"removed repeats", "within pool split"}
    # Pools of four and five premises cannot reach a half split at 5 a side.
    assert not any(c["passed"] for c in at50["checks"]["within pool split"].values())
    assert "shared at 50" in at50["reported"]["set inclusion, reference only"]
    assert verdict["passed"] is False
    assert set(verdict["tolerances"]) == {"set_inclusion", "granularity_sweep", "within_pool_split"}

    json_path, md_path = compare.write_verdict(verdict, work)
    text = md_path.read_text()
    assert "**Overall: FAILED**" in text and "1.5 x 0.0250" in text
    assert "the rerun does not reach this count" in text
    assert json.loads(json_path.read_text())["gated_checks"] == verdict["gated_checks"]


def test_the_verdict_fails_when_a_number_moves_beyond_its_tolerance(rerun, expected_dir):
    _, expected, work, runs = rerun
    path = expected_dir / "march_madness/debate/set_inclusion.json"
    paper = json.loads(path.read_text())
    paper["per_contrasts_per_side"]["25"]["summary"]["shared_frac_mean"] += 0.1
    path.write_text(json.dumps(paper))
    verdict = compare.compare_all(expected, [r for r in runs if r.name == "march_madness/debate"], work)
    headline = verdict["runs"]["march_madness/debate"]["checks"]["headline numbers"]
    assert [k for k, c in headline.items() if not c["passed"]] == ["shared at 25", "gap at 25"]


def test_the_cli_exit_status_is_the_verdict(rerun, release_dir, expected_dir):
    _, _, work, _ = rerun
    args = ["compare", "--artifact", str(release_dir), "--work-dir", str(work.root), "--expected", str(expected_dir)]
    assert cli.main(args + ["--run", "march_madness/resolution@50"]) == 1


def test_raw_scores_are_checked_only_with_recorded_scores_and_matched_by_text(rerun, tmp_path):
    _, expected, work, runs = rerun
    run = next(r for r in runs if r.name == "metaculus/resolution")
    recorded_dir = tmp_path / "recorded"
    for entry in planned(run, work):
        cached = compare.read_score_cache(find_cached_scores(work.caches, entry.key))
        texts, n_introspected = cached["key"].premises, entry.pools["introspected"]
        order = list(reversed(range(len(texts))))
        pos, neg = np.asarray(cached["pos_fwd"]), np.asarray(cached["neg_fwd"])
        # The "recorded" scores: the same texts in another order, every score moved by 0.01.
        _write(recorded_dir, f"metaculus/resolution/{entry.premise_set.question_id}.json", {
            "introspected": [texts[i] for i in order[:n_introspected]],
            "extracted": [texts[i] for i in order[n_introspected:]],
            "pos_fwd": (pos[np.ix_(order, order)] + 0.01).tolist(),
            "neg_fwd": (neg[np.ix_(order, order)] + 0.01).tolist(),
        })
    result = compare.compare_raw_scores(compare.RecordedScores(recorded_dir), run, work)
    assert result["questions_compared"] == 2
    assert result["max_abs_difference"] == pytest.approx(0.01)
    assert result["passed"] is True
    other = next(r for r in runs if r.name == "march_madness/debate")
    missing = compare.compare_raw_scores(compare.RecordedScores(recorded_dir), other, work)
    assert missing["passed"] is False and missing["questions_without_recorded_scores"] == 3


def test_the_figures_are_drawn_from_the_rerun_and_from_the_expected_numbers(rerun, expected_dir):
    pytest.importorskip("matplotlib")
    from cruxes_verify.figures import render

    _, _, work, _ = rerun
    assert render.main(["--work-dir", str(work.root), "--expected", str(expected_dir)]) == 0
    figures = work.root / "figures"
    for directory in (figures, figures / "paper"):
        names = {p.name for p in directory.glob("*.png")}
        assert "march_madness_resolution_set_inclusion.png" in names
        assert "march_madness_resolution_granularity_sweep.png" in names
        assert "march_madness_resolution@50_within_pool_split.png" in names
        assert "per_question_histogram.png" in names
    with pytest.raises(FileExistsError):
        render.main(["--work-dir", str(work.root), "--expected", str(expected_dir)])


def test_the_paper_figures_draw_from_the_shipped_expected_numbers(tmp_path):
    pytest.importorskip("matplotlib")
    from cruxes_verify.figures import render

    assert render.main(["--work-dir", str(tmp_path)]) == 0
    names = {p.name for p in (tmp_path / "figures" / "paper").glob("*.png")}
    assert len(names) == 7 * 2 + 1 + 1 + 1  # two per run, two baselines, the histogram
    assert not list((tmp_path / "figures").glob("*.png"))  # no rerun yet


def test_no_verifier_module_knows_the_authors_layout():
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("Data/runs", "/net/projects", "artifact_builder", "march_madness_objects59"):
            assert forbidden not in text, f"{path.name} mentions {forbidden}"


# The expected numbers shipped with the verifier ------------------------------


def test_the_shipped_runs_are_the_ones_the_paper_prints():
    names = [r.name for r in Expected().runs()]
    assert names == [
        "march_madness/resolution", "march_madness/resolution@50", "march_madness/equivalence",
        "march_madness/debate", "metaculus/resolution", "metaculus/equivalence", "metaculus/debate",
    ]


def test_the_shipped_tolerances_are_the_measured_ones():
    expected = Expected()
    assert tolerances.headline_tolerance(expected, "march_madness")["tolerance"] == pytest.approx(0.0356, abs=1e-3)
    assert tolerances.headline_tolerance(expected, "metaculus")["tolerance"] == pytest.approx(0.1588, abs=1e-3)
    assert tolerances.granularity_tolerance(expected, "march_madness")["tolerance"] == pytest.approx(0.0495, abs=1e-3)
    assert tolerances.within_pool_tolerance(expected, "march_madness")["tolerance"] == pytest.approx(0.0978, abs=1e-3)
    derived = compare.derive_tolerances(expected, expected.runs())
    assert set(derived["set_inclusion"]) == {"march_madness", "metaculus"}


def test_the_shipped_dedupe_counts_are_the_ruled_ones():
    expected = Expected()
    mm, meta = expected.dedupe_counts("march_madness"), expected.dedupe_counts("metaculus")
    assert mm["removed"] == {"introspected": 0, "extracted": 88}
    assert mm["questions_with_repeats"] == {"introspected": 0, "extracted": 36}
    assert meta["removed"] == {"introspected": 0, "extracted": 321}
    assert meta["questions_with_repeats"] == {"introspected": 0, "extracted": 8}
    assert len(mm["per_question"]) == 59 and len(meta["per_question"]) == 15


def test_every_shipped_run_has_its_expected_numbers():
    expected = Expected()
    for run in expected.runs():
        for analysis in run.analyses:
            result = expected.result(run, analysis)
            assert result["metadata"]["converted_from_sha256"]
        n = 59 if run.dataset == "march_madness" else 15
        if "set_inclusion" in run.analyses:
            assert expected.result(run)["per_contrasts_per_side"]["25"]["summary"]["n_questions"] == n
    within = expected.result("march_madness/resolution@50", "within_pool_split")
    assert [r["contrasts_per_side"] for r in within["per_contrasts_per_side"]] == list(range(1, 26))

"""Tests of the authors' builders, on synthetic inputs only.

The builders read the authors' internal runs, which a reviewer does not have,
so these tests exercise their pure functions and their refusals, never the
real sources. Neither builder is imported by the verifier.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "artifact_builder"))

import build_expected  # noqa: E402
import build_release  # noqa: E402
from legacy import LEGACY_SEED_LABELS, legacy_selection  # noqa: E402

from cruxes_verify.artifact import Artifact  # noqa: E402
from cruxes_verify.expected import Expected  # noqa: E402


# build_release: the dedupe checks -------------------------------------------


def test_dedupe_pools_counts_repeats_under_the_package_rule():
    pools = {
        "q1": ["a b", "a  b", " a b ", "c"],
        "q2": ["x", "X", "y"],
        "q3": ["z"],
    }
    deduped, counts = build_release.dedupe_pools(pools)
    assert deduped == {"q1": ["a b", "c"], "q2": ["x", "X", "y"], "q3": ["z"]}
    assert counts["removed"] == 2 and counts["questions_with_repeats"] == 1
    assert counts["per_question"]["q1"] == {"given": 4, "kept": 2, "removed": 2}


def test_the_dedupe_counts_must_be_the_papers():
    counts = {"removed": 88, "questions_with_repeats": 36}
    build_release.check_dedupe_counts("march_madness extracted", counts, (88, 36))
    with pytest.raises(build_release.BuildCheckError, match="removes 87 repeats across 36"):
        build_release.check_dedupe_counts("x", {"removed": 87, "questions_with_repeats": 36}, (88, 36))


def test_the_deduped_pools_must_equal_the_research_codes_text_by_text():
    ours = {"q1": ["a", "b"], "q2": ["c"]}
    build_release.check_same_pools("x", ours, {"q1": ["a", "b"], "q2": ["c"]})
    with pytest.raises(build_release.BuildCheckError, match="q1 differs .* first difference at position 1"):
        build_release.check_same_pools("x", ours, {"q1": ["a", "B"], "q2": ["c"]})
    with pytest.raises(build_release.BuildCheckError, match="first difference at position 2"):
        build_release.check_same_pools("x", ours, {"q1": ["a", "b", "d"], "q2": ["c"]})
    with pytest.raises(build_release.BuildCheckError, match="questions differ"):
        build_release.check_same_pools("x", ours, {"q1": ["a", "b"]})


def test_check_pools_applies_both_checks(monkeypatch):
    monkeypatch.setitem(build_release.EXPECTED_DEDUPE, "toy", {"introspected": (0, 0), "extracted": (1, 1)})
    introspected = {"q1": ["i1", "i2"], "q2": ["i3"]}
    extracted = {"q1": ["e1", "e1 ", "e2"], "q2": ["e3"]}
    research = {"q1": ["e1", "e2"], "q2": ["e3"]}
    source = Path(build_release.__file__)  # any file, for its hash
    deduped_i, deduped_e, record = build_release.check_pools("toy", introspected, extracted, research, source)
    assert deduped_e == research and deduped_i == introspected
    assert record["extracted"]["removed"] == 1 and record["introspected"]["removed"] == 0
    with pytest.raises(build_release.BuildCheckError):
        build_release.check_pools("toy", introspected, {"q1": ["e1", "e2"], "q2": ["e3"]}, research, source)


# build_release: Metaculus forecasts and post ids ----------------------------


def test_each_forecast_is_filed_under_its_own_question():
    question_of = {"d1/f1": "q1", "d1/f2": "q1", "d1/f3": "q2", "d1/f4": "other", "d2/f1": "q2"}
    files = {"d1": ["d1/f1", "d1/f2", "d1/f3", "d1/f4"], "d2": ["d2/f1"]}
    filed, record = build_release.file_forecasts(files, question_of.__getitem__, {"q1", "q2"})
    assert filed == {"q1": {"d1": ["d1/f1", "d1/f2"]}, "q2": {"d1": ["d1/f3"], "d2": ["d2/f1"]}}
    assert record["forecast_files"] == 5 and record["shipped"] == 4
    assert record["refiled_by_own_question"] == [{"file": "d1/f3", "question_id": "q2"}]
    assert record["left_out_other_question"] == [{"file": "d1/f4", "question_id": "other"}]


def test_the_post_ids_file_must_cover_exactly_the_questions():
    records = [
        {"question_id": "q1", "metaculus_post_id": 42119, "id_status": "confirmed"},
        {"question_id": "q2", "metaculus_post_id": None, "id_status": "unresolved"},
        {"question_id": "q3", "metaculus_post_id": 42230, "id_status": "ambiguous", "alternative_post_ids": [42135]},
    ]
    by_question, record = build_release.post_ids_by_question(records, ["q1", "q2", "q3"])
    assert by_question["q1"]["metaculus_post_id"] == 42119
    assert (record["with_post_id"], record["without_post_id"]) == (2, ["q2"])
    assert record["by_status"] == {"ambiguous": 1, "confirmed": 1, "unresolved": 1}
    assert record["ambiguous"] == [{"question_id": "q3", "metaculus_post_id": 42230, "alternative_post_ids": [42135]}]
    records = records[:2]
    with pytest.raises(build_release.BuildCheckError, match="missing"):
        build_release.post_ids_by_question(records, ["q1", "q2", "q3"])
    with pytest.raises(build_release.BuildCheckError):
        build_release.post_ids_by_question(records + [records[0]], ["q1", "q2"])


def test_the_shipped_post_ids_cover_the_fifteen_metaculus_questions():
    records = json.loads(build_release.POST_IDS.read_text(encoding="utf-8"))
    questions = sorted(Expected().dedupe_counts("metaculus")["per_question"])
    _, record = build_release.post_ids_by_question(records, questions)
    assert record["with_post_id"] == 15 and record["by_status"] == {"ambiguous": 3, "confirmed": 12}
    assert build_release.FETCH_SCRIPT.is_file()


# build_release: the release as a whole --------------------------------------


def test_file_roles():
    role = build_release.file_role
    assert role("method/matching_criteria.json") == "method"
    assert role("datasets/metaculus/extracted.json") == "premises"
    assert role("datasets/metaculus/questions.json") == "questions"
    assert role("datasets/march_madness/forecasts/a.json") == "forecasts"
    assert role("datasets/march_madness/noise_reference/introspected.json") == "noise_reference"
    assert role("datasets/metaculus/metaculus_post_ids.json") == "third_party_access"
    assert role("README.md") == "documentation"


def test_the_manifest_is_spec_version_two_and_the_verifier_accepts_it(tmp_path):
    out = tmp_path / "release"
    build_release.write_json(out / "method" / "matching_criteria.json", {"primary": "resolution", "criteria": []})
    build_release.write_json(out / "datasets" / "toy" / "introspected.json", {"q": ["a"]})
    build_release.write_text(out / "README.md", "toy")
    manifest = build_release.write_manifest(out, {"toy": "nowhere"})
    assert manifest["spec_version"] == 2 == Artifact(out).manifest["spec_version"]
    assert manifest["files"]["datasets/toy/introspected.json"]["role"] == "premises"
    assert Artifact(out).check_manifest()["files"] == 3
    with pytest.raises(FileExistsError):
        build_release.write_text(out / "README.md", "again")


def test_the_build_refuses_an_existing_output_before_reading_anything(tmp_path, monkeypatch, capsys):
    def must_not_run():
        raise AssertionError("read the sources")

    monkeypatch.setattr(build_release, "prepare_march_madness", must_not_run)
    monkeypatch.setattr(build_release, "prepare_metaculus", must_not_run)
    existing = tmp_path / "exists"
    existing.mkdir()
    assert build_release.main(["--out", str(existing)]) == 1
    assert build_release.main(["--out", str(tmp_path / "new"), "--provenance-out", str(existing)]) == 1
    assert build_release.main(["--out", str(tmp_path / "a"), "--provenance-out", str(tmp_path / "a" / "p")]) == 1
    assert "exists" in capsys.readouterr().out
    assert not (tmp_path / "new").exists() and not (tmp_path / "a").exists()


# build_release: the recorded scores (internal provenance) -------------------


def _cache(tmp_path, n_i, n_e, nan=False):
    n = n_i + n_e
    matrix = np.full((n, n), 0.5)
    if nan:
        matrix[0, 1] = np.nan
    payload = {k: matrix.tolist() for k in ("pos_fwd", "pos_rev", "neg_fwd", "neg_rev")}
    payload.update({"item_ids": list(range(n)), "max_k_a": n_i, "max_k_b": n_e})
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(payload))
    return path


def test_recorded_scores_are_keyed_by_the_texts_the_research_code_selected(tmp_path):
    introspected = [f"i{j}" for j in range(30)]
    extracted = [f"e{j}" for j in range(40)]
    scores = build_release.recorded_scores(_cache(tmp_path, 25, 25), introspected, extracted, "q")
    assert scores["introspected"] == legacy_selection(introspected, "q", LEGACY_SEED_LABELS[0])
    assert scores["extracted"] == legacy_selection(extracted, "q", LEGACY_SEED_LABELS[1])
    assert len(scores["pos_fwd"]) == 50 and scores["provenance"]["recorded_cache_sha256"]


def test_recorded_scores_refuse_a_size_mismatch_and_a_missing_score(tmp_path):
    introspected, extracted = [f"i{j}" for j in range(30)], [f"e{j}" for j in range(40)]
    with pytest.raises(build_release.BuildCheckError, match="reconstructed 25\\+25"):
        build_release.recorded_scores(_cache(tmp_path, 25, 24), introspected, extracted, "q")
    with pytest.raises(build_release.BuildCheckError, match="missing score"):
        build_release.recorded_scores(_cache(tmp_path, 25, 25, nan=True), introspected, extracted, "q")


# build_expected -------------------------------------------------------------


MANIFEST = {
    "rule": "the rule",
    "summary": {
        "extracted": {"removed_total": 3, "questions_with_repeats": 1},
        "introspected": {"removed_total": 0, "questions_with_repeats": 0},
    },
    "per_question": {
        "q1": {"extracted": {"pool_size": 10, "distinct": 7, "removed": 3},
               "introspected": {"pool_size": 5, "distinct": 5, "removed": 0}},
    },
}


def test_the_dedup_manifest_becomes_the_package_vocabulary(tmp_path):
    source = tmp_path / "dedup_manifest.json"
    source.write_text(json.dumps(MANIFEST))
    expectation = build_expected.dedupe_expectation(MANIFEST, source)
    assert expectation["removed"] == {"introspected": 0, "extracted": 3}
    assert expectation["questions_with_repeats"] == {"introspected": 0, "extracted": 1}
    assert expectation["per_question"]["q1"]["extracted"] == {"given": 10, "kept": 7, "removed": 3}


def test_the_manifest_counts_must_be_the_ruled_ones(tmp_path):
    source = tmp_path / "dedup_manifest.json"
    source.write_text(json.dumps(MANIFEST))
    with pytest.raises(ValueError, match="the ruling says"):
        build_expected.check_ruled_counts("march_madness", build_expected.dedupe_expectation(MANIFEST, source))


def test_per_question_records_can_be_dropped_keeping_summaries():
    result = {"metadata": {}, "per_contrasts_per_side": {"5": {"summary": {"a": 1}, "per_question": {"q": 1}}},
              "per_question": {"q": []}}
    assert build_expected.without_per_question(result) == {
        "metadata": {}, "per_contrasts_per_side": {"5": {"summary": {"a": 1}}}
    }


def test_build_expected_refuses_an_existing_directory(tmp_path):
    with pytest.raises(FileExistsError):
        build_expected.build(tmp_path)


def test_the_shipped_sources_name_every_expected_file():
    root = ROOT / "src" / "cruxes_verify" / "expected"
    sources = json.loads((root / "SOURCES.json").read_text(encoding="utf-8"))
    shipped = {
        p.relative_to(root).as_posix() for p in root.rglob("*.json") if p.name != "SOURCES.json"
    }
    assert shipped == set(sources)
    listed = set(build_expected.EXPECTED_FILES) | set(build_expected.NOISE_FILES)
    assert listed <= shipped

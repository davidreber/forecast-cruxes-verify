"""Offline tests of scripts/fetch_metaculus.py and the post ids file.

No network: the snapshot fixture holds invented posts in the shape of the
Metaculus posts endpoint, and the HTTP client is driven by a fake opener.
Standard library and pytest only; the package is not needed.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "fixtures" / "metaculus_snapshot"
IDS_FILE = ROOT / "artifact_builder" / "metaculus_post_ids.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fm = _load("fetch_metaculus", ROOT / "scripts" / "fetch_metaculus.py")
resolver = _load("resolve_metaculus_post_ids", ROOT / "artifact_builder" / "resolve_metaculus_post_ids.py")

FERRY = "will-the-glass-harbor-ferry-line-carry-at-least-2000000-passengers-in-2030"


def _ids(tmp_path, entries):
    path = tmp_path / "metaculus_post_ids.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_snapshot_run_writes_one_file_per_question(tmp_path):
    ids = _ids(tmp_path, [
        {"question_id": FERRY, "metaculus_post_id": 900001},
        {"question_id": "some-question-without-an-id", "metaculus_post_id": None},
        {"question_id": "an-older-question-id", "source": {"metaculus_post_id": 900002}},
    ])
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT)]) == 0

    out = tmp_path / "metaculus_fetched"
    assert sorted(p.name for p in out.iterdir()) == sorted([f"{FERRY}.json", "an-older-question-id.json", "fetch_log.json"])
    record = json.loads((out / f"{FERRY}.json").read_text(encoding="utf-8"))
    assert record["metaculus_post_id"] == 900001
    assert record["metaculus_question_id"] == 800001
    assert record["url"] == "https://www.metaculus.com/questions/900001/"
    assert record["title_matches_question_id"] is True
    assert record["resolution"] == "yes"
    assert record["actual_close_time"] == "2030-06-01T00:00:00Z"
    assert record["resolution_criteria"].startswith("Resolves Yes")
    assert list(record["community_forecast"]) == ["recency_weighted"]
    assert len(record["community_forecast"]["recency_weighted"]["history"]) == 2
    assert record["community_forecast_latest"] == 0.62
    assert "aggregations" in record["api_fields"]["question"]
    assert record["retrieved"]["from"] == "snapshot"

    other = json.loads((out / "an-older-question-id.json").read_text(encoding="utf-8"))
    assert other["title_matches_question_id"] is False
    assert other["community_forecast"] is None and other["resolution"] is None

    log = json.loads((out / "fetch_log.json").read_text(encoding="utf-8"))
    assert log["counts"] == {"fetched": 2, "no post id": 1}


def test_existing_files_are_kept_unless_refresh(tmp_path):
    ids = _ids(tmp_path, [900001])
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT)]) == 0
    target = tmp_path / "metaculus_fetched" / "post_900001.json"
    target.write_text("{}", encoding="utf-8")
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT)]) == 0
    assert target.read_text(encoding="utf-8") == "{}"
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT), "--refresh"]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["metaculus_post_id"] == 900001


def test_dry_run_writes_nothing_and_lists_the_fields(tmp_path, capsys):
    ids = _ids(tmp_path, [900001])
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT), "--dry-run"]) == 0
    assert list(tmp_path.iterdir()) == [ids]
    printed = capsys.readouterr().out
    assert "post 900001 (question 800001)" in printed
    assert "question fields:" in printed and "resolution_criteria" in printed


def test_a_missing_post_is_an_error_and_the_run_continues(tmp_path):
    ids = _ids(tmp_path, [900404, 900001])
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT)]) == 1
    log = json.loads((tmp_path / "metaculus_fetched" / "fetch_log.json").read_text(encoding="utf-8"))
    assert [e["status"] for e in log["entries"]] == ["error", "fetched"]


def test_shipped_in_the_release_layout_it_reads_questions_json_next_to_it(tmp_path):
    base = tmp_path / "datasets" / "metaculus"
    base.mkdir(parents=True)
    (base / "fetch_metaculus.py").write_text((ROOT / "scripts" / "fetch_metaculus.py").read_text(encoding="utf-8"), encoding="utf-8")
    (base / "questions.json").write_text(json.dumps([
        {"question_id": FERRY, "question": None, "outcome": None,
         "source": {"platform": "Metaculus", "metaculus_post_id": 900001}},
    ]), encoding="utf-8")
    shipped = _load("fetch_metaculus_shipped", base / "fetch_metaculus.py")
    assert shipped.main(["--snapshot-dir", str(SNAPSHOT)]) == 0
    assert (base / "metaculus_fetched" / f"{FERRY}.json").is_file()


def test_fields_the_api_sends_empty_are_listed_as_withheld(tmp_path):
    ids = _ids(tmp_path, [900003, 900001])
    assert fm.main(["--ids", str(ids), "--snapshot-dir", str(SNAPSHOT)]) == 0
    withheld = json.loads((tmp_path / "metaculus_fetched" / "post_900003.json").read_text(encoding="utf-8"))
    assert withheld["withheld_by_api"] == ["description", "resolution_criteria", "fine_print", "resolution", "community_forecast"]
    assert withheld["tournaments"] == ["Invented Bot Tournament"]
    assert withheld["resolution_set_time"] == "2030-07-02T10:00:00Z"
    full = json.loads((tmp_path / "metaculus_fetched" / "post_900001.json").read_text(encoding="utf-8"))
    assert full["withheld_by_api"] == []


def test_a_post_without_a_single_question_is_recorded_with_a_note():
    record = fm.question_record({"id": 5, "title": "A group", "group_of_questions": {}}, 5, None, {})
    assert record["question_type"] is None and "note" in record
    assert record["title_matches_question_id"] is None


def test_ids_file_entries_are_validated(tmp_path):
    with pytest.raises(SystemExit):
        fm.load_targets(_ids(tmp_path, [42.5]))
    with pytest.raises(SystemExit):
        fm.load_targets(_ids(tmp_path, [True]))
    assert fm.load_targets(_ids(tmp_path, [7, "8"])) == [(None, 7), (None, 8)]


def test_the_token_comes_from_an_env_file_first_then_the_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("METACULUS_API_TOKEN", raising=False)
    monkeypatch.setenv("METACULUS_API_KEY", "from-the-environment")
    env = tmp_path / ".env"
    env.write_text('OTHER_KEY=ignored\n# a comment\nexport METACULUS_API_KEY="from-the-file"\n', encoding="utf-8")
    assert fm.load_token(env) == "from-the-file"
    assert fm.read_env_file(env) == {"METACULUS_API_KEY": "from-the-file"}
    assert fm.load_token() == "from-the-environment"
    monkeypatch.delenv("METACULUS_API_KEY")
    assert fm.load_token() is None
    empty = tmp_path / "empty.env"
    empty.write_text("OTHER_KEY=1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        fm.load_token(empty)


# ------------------------------------------------------------- the HTTP client


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code, body=b"", headers=None):
    return urllib.error.HTTPError("https://example.invalid", code, "error", headers or {}, io.BytesIO(body))


class _Opener:
    """Plays back a list of outcomes: an exception to raise or a payload to return."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(json.dumps(outcome).encode("utf-8"))


def _client(opener, sleeps, **kwargs):
    ticks = iter(range(0, 10_000, 1))
    return fm.MetaculusClient(token="secret", opener=opener, sleep=sleeps.append,
                              clock=lambda: float(next(ticks)), **kwargs)


def test_client_honours_retry_after_then_paces_requests():
    opener = _Opener([_http_error(429, headers={"Retry-After": "7"}), {"id": 1}, {"id": 2}])
    sleeps = []
    client = _client(opener, sleeps, interval=4.0)
    assert client.get_json("https://example.invalid/a") == {"id": 1}
    assert client.get_json("https://example.invalid/b") == {"id": 2}
    # 7 s from Retry-After; the retry itself is paced (4 s interval, 1 s elapsed on the fake clock)
    assert sleeps[0] == 7.0 and all(s <= 4.0 for s in sleeps[1:])
    request = opener.requests[0]
    assert request.get_header("Authorization") == "Token secret"
    assert request.get_header("User-agent").startswith("forecast-cruxes-fetch/")


def test_client_backs_off_on_server_errors_and_gives_up():
    opener = _Opener([_http_error(502)] * 3)
    sleeps = []
    client = _client(opener, sleeps, interval=1.0, retries=2)
    with pytest.raises(fm.FetchError, match="3 attempts"):
        client.get_json("https://example.invalid/x")
    assert [s for s in sleeps if s >= 5] == [5.0, 10.0]


def test_a_page_that_is_not_json_is_an_error_not_a_crash():
    class _Html(_Opener):
        def __call__(self, request, timeout):
            return _Response(b"<html>challenge</html>")

    with pytest.raises(fm.FetchError, match="not JSON"):
        _client(_Html([]), []).get_json("https://example.invalid/html")


def test_an_auth_refusal_stops_the_run(tmp_path, monkeypatch):
    refusal = _http_error(403, b"Permission Error: The API is only available to authenticated users.")
    opener = _Opener([refusal])
    monkeypatch.setattr(fm.urllib.request, "urlopen", opener)
    monkeypatch.delenv("METACULUS_API_TOKEN", raising=False)
    monkeypatch.delenv("METACULUS_API_KEY", raising=False)
    ids = _ids(tmp_path, [900001, 900002])
    assert fm.main(["--ids", str(ids), "--interval", "1"]) == 2
    log = json.loads((tmp_path / "metaculus_fetched" / "fetch_log.json").read_text(encoding="utf-8"))
    assert [e["status"] for e in log["entries"]] == ["error", "not attempted"]
    assert "authenticated users" in log["entries"][0]["error"]
    assert len(opener.requests) == 1


# ------------------------------------------------------------- our ids file


def test_the_post_ids_file_covers_the_fifteen_questions():
    records = json.loads(IDS_FILE.read_text(encoding="utf-8"))
    question_ids = [r["question_id"] for r in records]
    assert len(records) == 15 and question_ids == sorted(set(question_ids))
    known = [r["metaculus_post_id"] for r in records if r["metaculus_post_id"] is not None]
    assert len(known) == len(set(known))
    for record in records:
        assert record["id_status"] in {"confirmed", "ambiguous", "unresolved"}
        assert record["id_source"] in {"forecast_link", "api_title_search", None}
        if record["id_status"] == "unresolved":
            assert record["metaculus_post_id"] is None
        if record["id_status"] == "confirmed":
            assert record["metaculus_post_id"] is not None
        assert (record["id_status"] == "ambiguous") == bool(record.get("alternative_post_ids"))
        assert record["evidence"]
    assert fm.load_targets(IDS_FILE)[3] == ("will-any-state-actor-use-chemical-weapons-in-ukraine-before-may-1-2026", 42119)


def test_resolver_accepts_only_a_title_whose_slug_is_the_question_id():
    results = [
        {"id": 11, "title": "Will the Glass Harbor ferry line carry at least 2,000,000 passengers in 2031?"},
        {"id": 12, "title": "Will the Glass Harbor ferry line carry at least 2,000,000 passengers in 2030?"},
        {"id": 13, "title": "Ferry group", "question": {"title": "Will the Glass Harbor ferry line carry at least 2,000,000 passengers in 2030?"}},
    ]
    assert resolver.matching_posts(results, FERRY) == [12, 13]
    assert "search=Will+the" in resolver.search_url("Will the Glass Harbor ferry line")

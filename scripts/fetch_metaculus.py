#!/usr/bin/env python3
"""Fetch the Metaculus side of the forecast-cruxes data release from the Metaculus API.

Metaculus content is proprietary. Its terms of use allow no redistribution with
attribution alone and allow access through the API Metaculus provides, so the
release ships the Metaculus post id of each question (``metaculus_post_ids.json``)
and never the question text. For each post id this script requests the
question text, resolution criteria, resolution, open, close and resolve times
and the community forecast history, and writes one JSON file per question with
whatever the API returns; what that is depends on the token (below). A copy
ships in the data release as ``datasets/metaculus/fetch_metaculus.py``; that
copy is canonical.

    export METACULUS_API_TOKEN=...        # free: Metaculus account settings, API access
    python fetch_metaculus.py             # every id in metaculus_post_ids.json next to this script
    python fetch_metaculus.py --env-file ~/.env     # or read the token from a KEY=VALUE file
    python fetch_metaculus.py --ids my_ids.json --out fetched/
    python fetch_metaculus.py --dry-run --post-id 42119
    python fetch_metaculus.py --snapshot-dir metaculus_snapshot     # a frozen copy, no network

What an ordinary account token is shown (checked 2026-09-24): the title, ids,
type, status, open, close and resolve times and tournaments of every question
and the text of open questions; not the text or resolution of resolved
questions, and no community forecast for any question tried, resolved or open
(those fields come back null). Each file lists them in ``withheld_by_api``. Fuller access is by request
to Metaculus (https://www.metaculus.com/api).

The API refuses anonymous requests (HTTP 403, checked 2026-09-24), so a token is
needed. It is sent as ``Authorization: Token <token>`` and taken from, in order:
``--env-file`` (a ``KEY=VALUE`` file such as a ``.env``; only
``METACULUS_API_TOKEN`` and ``METACULUS_API_KEY`` are read from it), then the
environment variables ``METACULUS_API_TOKEN`` and ``METACULUS_API_KEY``. The
token is never printed or written.

Input (``--ids``, default ``metaculus_post_ids.json`` next to this script, else
``questions.json`` there): a JSON list whose entries are post ids, or records
with ``metaculus_post_id`` (top level, or under ``source`` as in
``questions.json``) and optionally our ``question_id``. Records whose post id
is null are listed and skipped.

Output (``--out``, default ``metaculus_fetched/`` next to the ids file): one file
per question, named by our ``question_id`` (``post_<id>.json`` without one), and
``fetch_log.json``. Our question ids are the first 80 characters of a slug of
the Metaculus title as it read when we forecast (lowercase, letters, digits and
spaces kept, spaces to hyphens); ``title_matches_question_id`` records whether
the fetched title still gives that slug. Files already fetched are kept unless
``--refresh``.

``--dry-run`` fetches and prints a summary of each post, including the fields
the API returned, and writes nothing. ``--snapshot-dir`` reads raw API
responses (``<post_id>.json``) from a directory instead of the network: the
optional frozen snapshot, shipped only if Metaculus gives written permission.
``--save-raw DIR`` stores the raw responses of a network run in that format.

Nothing the verification checks reads these files: set inclusion reads premises
only. Standard library only; one request every four seconds by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_ROOT = "https://www.metaculus.com/api"
POST_ENDPOINT = API_ROOT + "/posts/{post_id}/"
PAGE_URL = "https://www.metaculus.com/questions/{post_id}/"
TOKEN_VARIABLES = ("METACULUS_API_TOKEN", "METACULUS_API_KEY")
USER_AGENT = "forecast-cruxes-fetch/1.0 (research data release; python urllib; one request per {interval:g} s)"
DEFAULT_INTERVAL = 4.0
DEFAULT_RETRIES = 4
TIMEOUT_SECONDS = 30
MAX_BACKOFF_SECONDS = 120.0
DEFAULT_IDS_FILES = ("metaculus_post_ids.json", "questions.json")
FETCHED_DIR = "metaculus_fetched"
LOG_FILE = "fetch_log.json"


class FetchError(Exception):
    """A post could not be fetched; the run continues with the next one."""


class NotFound(FetchError):
    """HTTP 404, or no file for the post in the snapshot."""


class AuthError(Exception):
    """HTTP 401 or 403: every further request would fail the same way."""


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def question_slug(text: str) -> str:
    """Our question id for a question text (the research code's generic slug)."""
    kept = "".join(c if c.isalnum() or c == " " else "" for c in text.lower())
    return "-".join(kept.split())[:80]


def read_env_file(path: Path) -> dict:
    """The token variables of a KEY=VALUE file (``export`` and quotes allowed)."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in TOKEN_VARIABLES:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        found[key] = value
    return found


def load_token(env_file=None):
    """The API token from ``env_file`` if given, else from the environment; None if absent."""
    sources = []
    if env_file is not None:
        if not Path(env_file).is_file():
            raise SystemExit(f"--env-file {env_file} is not a file")
        sources.append(read_env_file(Path(env_file)))
    sources.append(os.environ)
    for values in sources:
        for name in TOKEN_VARIABLES:
            if values.get(name):
                return values[name]
    if env_file is not None:
        raise SystemExit(f"no {' or '.join(TOKEN_VARIABLES)} in {env_file} or the environment")
    return None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- sources


class MetaculusClient:
    """GET JSON from the Metaculus API: polite, rate limited, retrying.

    At most one request per ``interval`` seconds. HTTP 429, 5xx and network
    errors are retried up to ``retries`` times, waiting for the server's
    Retry-After when it sends one and otherwise 5, 10, 20, ... seconds (at most
    120). HTTP 401 and 403 raise AuthError at once; 404 raises NotFound.
    """

    def __init__(self, token=None, interval=DEFAULT_INTERVAL, retries=DEFAULT_RETRIES,
                 user_agent=None, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.token = token
        self.interval = interval
        self.retries = retries
        self.user_agent = user_agent or USER_AGENT.format(interval=interval)
        self.opener = opener
        self.sleep = sleep
        self.clock = clock
        self._last = None

    def _pace(self) -> None:
        if self._last is not None:
            wait = self.interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)

    def get_json(self, url: str):
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        opener = self.opener or urllib.request.urlopen
        for attempt in range(self.retries + 1):
            self._pace()
            request = urllib.request.Request(url, headers=headers)
            try:
                with opener(request, timeout=TIMEOUT_SECONDS) as response:
                    body = response.read()
                self._last = self.clock()
                try:
                    return json.loads(body.decode("utf-8"))
                except ValueError:
                    raise FetchError(f"the response from {url} is not JSON: {body[:120]!r}") from None
            except urllib.error.HTTPError as error:
                self._last = self.clock()
                detail = _body_snippet(error)
                if error.code in (401, 403):
                    raise AuthError(f"HTTP {error.code} from {url}: {detail}") from None
                if error.code == 404:
                    raise NotFound(f"HTTP 404 from {url}") from None
                if error.code != 429 and error.code < 500:
                    raise FetchError(f"HTTP {error.code} from {url}: {detail}") from None
                reason = f"HTTP {error.code}"
                delay = _retry_after(error)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                self._last = self.clock()
                reason = f"{type(error).__name__}: {getattr(error, 'reason', error)}"
                delay = None
            if attempt == self.retries:
                raise FetchError(f"{reason} from {url}, gave up after {attempt + 1} attempts")
            if delay is None:
                delay = min(MAX_BACKOFF_SECONDS, 5.0 * 2**attempt)
            log(f"  {reason}; retrying in {delay:g} s")
            self.sleep(delay)
        raise AssertionError("unreachable")


def _body_snippet(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", "replace").strip()[:300]
    except Exception:  # noqa: BLE001 - a diagnostic only
        return ""


def _retry_after(error: urllib.error.HTTPError):
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(MAX_BACKOFF_SECONDS, max(0.0, float(value)))
    except (TypeError, ValueError):
        return None


class NetworkSource:
    kind = "api"

    def __init__(self, client: MetaculusClient):
        self.client = client

    def get_post(self, post_id: int):
        url = POST_ENDPOINT.format(post_id=post_id)
        return self.client.get_json(url), url


class SnapshotSource:
    """Raw API responses saved as ``<snapshot_dir>/<post_id>.json``."""

    kind = "snapshot"

    def __init__(self, directory: Path):
        if not directory.is_dir():
            raise SystemExit(f"--snapshot-dir {directory} is not a directory")
        self.directory = directory

    def get_post(self, post_id: int):
        path = self.directory / f"{post_id}.json"
        if not path.is_file():
            raise NotFound(f"no {path.name} in {self.directory}")
        try:
            return json.loads(path.read_text(encoding="utf-8")), path.name
        except ValueError as error:
            raise FetchError(f"{path} is not JSON: {error}") from None


# ---------------------------------------------------------------- records


def community_forecast(question: dict):
    """{aggregation method: {"history": [...], "latest": {...}}} or None."""
    found = {}
    for method, aggregation in (question.get("aggregations") or {}).items():
        if not isinstance(aggregation, dict):
            continue
        history, latest = aggregation.get("history"), aggregation.get("latest")
        if history or latest:
            found[method] = {"history": history or [], "latest": latest}
    return found or None


def latest_center(forecast):
    """The community prediction shown on the site: recency weighted, latest median."""
    try:
        return forecast["recency_weighted"]["latest"]["centers"][0]
    except (KeyError, IndexError, TypeError):
        return None


def withheld_fields(post: dict, question: dict) -> list:
    """Fields the API has but sent empty: what an ordinary token is not shown.

    Seen 2026-09-24 with an ordinary account token: for resolved questions
    ``description``, ``resolution_criteria`` and ``fine_print`` are null and
    ``resolution`` is null although ``status`` is resolved; for every question
    tried, open or resolved, each aggregation's ``history`` and ``latest`` are
    null. Text fields count as withheld when description and resolution
    criteria are both empty, since no real question lacks both.
    """
    text = ("description", "resolution_criteria", "fine_print")
    withheld = []
    if all(f in question and not question.get(f) for f in text[:2]):
        withheld = [f for f in text if f in question and not question.get(f)]
    if question.get("status") == "resolved" and question.get("resolution") is None:
        withheld.append("resolution")
    aggregations = question.get("aggregations")
    if isinstance(aggregations, dict) and aggregations and community_forecast(question) is None:
        withheld.append("community_forecast")
    return withheld


def tournaments(post: dict) -> list:
    projects = post.get("projects") if isinstance(post.get("projects"), dict) else {}
    return [t.get("name") for t in projects.get("tournament") or [] if isinstance(t, dict)]


def question_record(post: dict, post_id: int, question_id, retrieved: dict) -> dict:
    """The per-question file: what a reader needs to see what a question asked."""
    question = post.get("question") if isinstance(post.get("question"), dict) else None
    q = question or {}
    title = post.get("title") or q.get("title")
    forecast = community_forecast(q)
    record = {
        "question_id": question_id,
        "metaculus_post_id": post.get("id", post_id),
        "metaculus_question_id": q.get("id"),
        "url": PAGE_URL.format(post_id=post.get("id", post_id)),
        "title": title,
        "title_matches_question_id": (
            None if question_id is None or title is None else question_slug(title) == question_id
        ),
        "question_type": q.get("type"),
        "description": q.get("description"),
        "resolution_criteria": q.get("resolution_criteria"),
        "fine_print": q.get("fine_print"),
        "status": q.get("status") or post.get("status"),
        "resolution": q.get("resolution"),
        "open_time": q.get("open_time") or post.get("open_time"),
        "scheduled_close_time": q.get("scheduled_close_time") or post.get("scheduled_close_time"),
        "actual_close_time": q.get("actual_close_time") or post.get("actual_close_time"),
        "scheduled_resolve_time": q.get("scheduled_resolve_time") or post.get("scheduled_resolve_time"),
        "actual_resolve_time": q.get("actual_resolve_time"),
        "resolution_set_time": q.get("resolution_set_time"),
        "tournaments": tournaments(post),
        "nr_forecasters": post.get("nr_forecasters"),
        "community_forecast": forecast,
        "community_forecast_latest": latest_center(forecast),
        "withheld_by_api": withheld_fields(post, q),
        "api_fields": {"post": sorted(post), "question": sorted(q)},
        "retrieved": retrieved,
    }
    if question is None:
        record["note"] = "the post holds no single question (a group, conditional or notebook); question fields are null"
    return record


# ---------------------------------------------------------------- inputs


def load_targets(path: Path) -> list:
    """[(question_id or None, post_id or None)] from an ids file."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise SystemExit(f"{path}: expected a JSON list of post ids or records")
    targets = []
    for entry in entries:
        if isinstance(entry, bool):
            raise SystemExit(f"{path}: not a post id: {entry!r}")
        if isinstance(entry, (int, str)):
            targets.append((None, _post_id(entry, path)))
        elif isinstance(entry, dict):
            source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
            raw = entry.get("metaculus_post_id", source.get("metaculus_post_id"))
            targets.append((entry.get("question_id"), None if raw is None else _post_id(raw, path)))
        else:
            raise SystemExit(f"{path}: not a post id or record: {entry!r}")
    return targets


def _post_id(value, path) -> int:
    try:
        post_id = int(value)
    except (TypeError, ValueError):
        raise SystemExit(f"{path}: not a post id: {value!r}") from None
    if post_id <= 0 or str(value).strip() != str(post_id):
        raise SystemExit(f"{path}: not a post id: {value!r}")
    return post_id


def output_name(question_id, post_id: int) -> str:
    if question_id and "/" not in question_id and "\\" not in question_id and not question_id.startswith("."):
        return f"{question_id}.json"
    return f"post_{post_id}.json"


def write_json(path: Path, payload) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    partial.replace(path)


def summarize(record: dict) -> str:
    history = sum(len(v["history"]) for v in (record["community_forecast"] or {}).values())
    lines = [
        f"  post {record['metaculus_post_id']} (question {record['metaculus_question_id']}): {record['title']}",
        f"    type {record['question_type']}, status {record['status']}, resolution {record['resolution']}",
        f"    close {record['actual_close_time'] or record['scheduled_close_time']}, "
        f"community forecast: {', '.join(record['community_forecast'] or {}) or 'none'} "
        f"({history} history points, latest {record['community_forecast_latest']})",
        f"    title matches question_id: {record['title_matches_question_id']}; "
        f"tournaments: {', '.join(record['tournaments']) or 'none'}",
        f"    sent empty by the API: {', '.join(record['withheld_by_api']) or 'nothing'}",
        f"    post fields: {', '.join(record['api_fields']['post'])}",
        f"    question fields: {', '.join(record['api_fields']['question'])}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- main


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--ids", type=Path, help="JSON list of post ids or records (default: metaculus_post_ids.json, else questions.json, next to this script)")
    which.add_argument("--post-id", type=int, action="append", help="a post id; repeat for several")
    parser.add_argument("--out", type=Path, help=f"output directory (default: {FETCHED_DIR}/ next to the ids file)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print a summary; write nothing")
    parser.add_argument("--snapshot-dir", type=Path, help="read raw responses <post_id>.json from here instead of the network")
    parser.add_argument("--save-raw", type=Path, help="also store each raw API response as <post_id>.json here")
    parser.add_argument("--refresh", action="store_true", help="fetch again questions already in the output directory")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="seconds between requests (default 4, minimum 1)")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="retries on 429, 5xx and network errors (default 4)")
    parser.add_argument("--env-file", type=Path, help="read METACULUS_API_TOKEN or METACULUS_API_KEY from this KEY=VALUE file")
    parser.add_argument("--contact", help="an email or URL to add to the User-Agent, so Metaculus can reach you")
    args = parser.parse_args(argv)
    if args.interval < 1.0:
        parser.error("--interval below 1 s is not polite to the Metaculus API")
    if args.dry_run and args.save_raw:
        parser.error("--dry-run writes nothing, so it cannot --save-raw")
    if args.snapshot_dir and args.save_raw:
        parser.error("--save-raw stores network responses; a snapshot run has none")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.post_id:
        targets = [(None, post_id) for post_id in args.post_id]
        base = Path.cwd()
    else:
        here = Path(__file__).resolve().parent
        candidates = [args.ids] if args.ids else [here / name for name in DEFAULT_IDS_FILES]
        ids_file = next((c for c in candidates if c.is_file()), None)
        if ids_file is None:
            raise SystemExit(f"no ids file ({', '.join(map(str, candidates))}); pass --ids or --post-id")
        targets = load_targets(ids_file)
        base = ids_file.resolve().parent
    out = args.out or base / FETCHED_DIR

    if args.snapshot_dir:
        source = SnapshotSource(args.snapshot_dir)
    else:
        token = load_token(args.env_file)
        if not token:
            log("no METACULUS_API_TOKEN or METACULUS_API_KEY set; the API refused anonymous requests (HTTP 403) on 2026-09-24")
        agent = USER_AGENT.format(interval=args.interval) + (f" contact: {args.contact}" if args.contact else "")
        source = NetworkSource(MetaculusClient(token, args.interval, args.retries, agent))

    missing = [qid for qid, post_id in targets if post_id is None]
    if missing:
        log(f"{len(missing)} of {len(targets)} entries have no post id and are skipped:")
        for question_id in missing:
            log(f"  {question_id}")
    if not args.dry_run:
        out.mkdir(parents=True, exist_ok=True)
        if args.save_raw:
            args.save_raw.mkdir(parents=True, exist_ok=True)

    started = now_utc()
    entries, auth_failure, withheld_warned = [], None, False
    for question_id, post_id in targets:
        entry = {"question_id": question_id, "metaculus_post_id": post_id}
        entries.append(entry)
        if post_id is None:
            entry["status"] = "no post id"
            continue
        if auth_failure:
            entry["status"] = "not attempted"
            continue
        name = output_name(question_id, post_id)
        entry["file"] = name
        if not args.dry_run and not args.refresh and (out / name).exists():
            entry["status"] = "already fetched"
            log(f"post {post_id}: already fetched ({name})")
            continue
        log(f"post {post_id}: fetching from {source.kind}")
        try:
            post, location = source.get_post(post_id)
        except AuthError as error:
            auth_failure = str(error)
            entry.update(status="error", error=auth_failure)
            log(f"  {auth_failure}")
            log("  stopping: the API needs a valid token (METACULUS_API_TOKEN)")
            continue
        except FetchError as error:
            entry.update(status="error", error=str(error))
            log(f"  {error}")
            continue
        if not isinstance(post, dict):
            entry.update(status="error", error="the response is not a JSON object")
            log(f"  {entry['error']}")
            continue
        record = question_record(post, post_id, question_id, {"from": source.kind, "location": location, "at": now_utc()})
        entry["title_matches_question_id"] = record["title_matches_question_id"]
        entry["withheld_by_api"] = record["withheld_by_api"]
        if record["withheld_by_api"] and not withheld_warned:
            withheld_warned = True
            log(f"  the API sent empty: {', '.join(record['withheld_by_api'])}. Ordinary tokens are not shown the text or"
                " resolution of resolved questions, nor community forecasts; see https://www.metaculus.com/api about access")
        if record["title_matches_question_id"] is False:
            log(f"  warning: the title's slug is not {question_id}; check the post id")
        if args.dry_run:
            entry["status"] = "fetched, dry run"
            print(summarize(record), flush=True)
            continue
        write_json(out / name, record)
        if args.save_raw:
            write_json(args.save_raw / f"{post_id}.json", post)
        entry["status"] = "fetched"

    errors = [e for e in entries if e.get("status") == "error"]
    summary = {
        "script": "fetch_metaculus.py",
        "source": source.kind,
        "endpoint": None if args.snapshot_dir else POST_ENDPOINT,
        "started": started,
        "finished": now_utc(),
        "dry_run": args.dry_run,
        "counts": {s: sum(e.get("status") == s for e in entries) for s in sorted({e["status"] for e in entries})},
        "entries": entries,
    }
    if not args.dry_run:
        write_json(out / LOG_FILE, summary)
        log(f"wrote {out}")
    log(f"done: {summary['counts']}")
    if auth_failure:
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

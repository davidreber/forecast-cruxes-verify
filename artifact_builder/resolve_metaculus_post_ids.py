"""Look up the missing Metaculus post ids of our questions by title.

AUTHORS ONLY: it needs the question text, which the release does not carry, so
it reads the release's ``datasets/metaculus/questions.json``. It also
needs a Metaculus API token (``METACULUS_API_TOKEN`` or ``METACULUS_API_KEY``, in
the environment or in ``--env-file``): the API refuses anonymous requests.

For every record of ``metaculus_post_ids.json`` whose post id is null, it
searches the API (``/api/posts/?search=<title>``) and accepts a post only when
the slug of its title equals our question_id, the way the question ids were
made. A question with several such posts is marked ``ambiguous`` with the
candidates in ``alternative_post_ids`` and its post id left null for a person
to choose; one with none stays ``unresolved`` and its closest hits are printed.
The completed list goes to ``--out``; review it, then replace
``artifact_builder/metaculus_post_ids.json``.

    python artifact_builder/resolve_metaculus_post_ids.py --env-file <project>/cruxes/.env \\
        --questions <dev slice>/datasets/metaculus/questions.json --out $TMPDIR/metaculus_post_ids.json

Then confirm every id, the six from recorded citations included:

    python scripts/fetch_metaculus.py --env-file <project>/cruxes/.env --ids $TMPDIR/metaculus_post_ids.json --dry-run

Run 2026-09-24 with an account token: it resolved 7 of the 9 questions
without a recorded link and found two exact matches for the other 2.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
IDS_FILE = HERE / "metaculus_post_ids.json"


def _load_fetch_module():
    path = HERE.parent / "scripts" / "fetch_metaculus.py"
    spec = importlib.util.spec_from_file_location("fetch_metaculus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = _load_fetch_module()


def search_url(text: str) -> str:
    return fetch.API_ROOT + "/posts/?" + urllib.parse.urlencode({"search": text, "limit": 20})


def matching_posts(results: list, question_id: str) -> list:
    """Post ids among search results whose title slug is our question_id."""
    hits = []
    for post in results:
        titles = [post.get("title"), (post.get("question") or {}).get("title")]
        if any(t and fetch.question_slug(t) == question_id for t in titles):
            hits.append(post["id"])
    return sorted(set(hits))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", required=True, type=Path, help="the dev slice's questions.json (has the text)")
    parser.add_argument("--ids", type=Path, default=IDS_FILE)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, help="read METACULUS_API_TOKEN or METACULUS_API_KEY from this file")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; choose a new path")

    text_of = {q["question_id"]: q["question"] for q in json.loads(args.questions.read_text(encoding="utf-8"))}
    records = json.loads(args.ids.read_text(encoding="utf-8"))
    client = fetch.MetaculusClient(fetch.load_token(args.env_file))

    for record in records:
        if record["metaculus_post_id"] is not None:
            continue
        question_id = record["question_id"]
        text = text_of.get(question_id)
        if not text:
            print(f"{question_id}: no text in {args.questions}")
            continue
        try:
            page = client.get_json(search_url(text))
        except fetch.AuthError as error:
            print(f"{error}\nstopping: the API needs a valid token (METACULUS_API_TOKEN)")
            return 2
        except fetch.FetchError as error:
            print(f"{question_id}: {error}")
            continue
        results = page.get("results", []) if isinstance(page, dict) else []
        hits = matching_posts(results, question_id)
        if len(hits) == 1:
            record.update(
                metaculus_post_id=hits[0],
                url=fetch.PAGE_URL.format(post_id=hits[0]),
                id_source="api_title_search",
                id_status="confirmed",
                evidence="the only API title search result whose title slug equals our question_id",
            )
            print(f"{question_id}: {hits[0]}")
        elif hits:
            record.update(id_source="api_title_search", id_status="ambiguous", alternative_post_ids=hits,
                          evidence=f"{len(hits)} posts have a title whose slug equals our question_id; choose one")
            print(f"{question_id}: ambiguous, {hits}")
        else:
            print(f"{question_id}: no exact match; top hits:")
            for post in results[:5]:
                print(f"    {post.get('id')}: {post.get('title')}")

    args.out.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    resolved = sum(r["metaculus_post_id"] is not None for r in records)
    print(f"{resolved} of {len(records)} post ids known; wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

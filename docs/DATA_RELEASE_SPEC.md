# The data release: layout specification

Spec version 2, 2026-09-24. It replaces version 1 (2026-09-23, then called
the data artifact). The data release built to it was released on 2026-10-08
as https://github.com/davidreber/forecast-cruxes-data.

## Three parts

The paper's claims rest on three things, kept apart:

1. **Inputs**, the data release specified here: what the language models
   produced (forecasts, introspected premises, extracted premises), the
   outcomes, our scouting reports, the second introspection samples used as
   noise references, and the matching criteria.
2. **The function**, the `forecast-cruxes` package: the method as code, with
   no data in it.
3. **Results**, what the paper prints: the package run on the release. The
   verification repository checks exactly this, by running the package on the
   release and comparing with the numbers it carries as its own package data
   (`src/cruxes_verify/expected/`).

So the release holds inputs only, and nothing computed from them, apart from
the authors' recorded reranker scores, which ship separately under
`provenance/` (role `provenance`) and which nothing in the analysis reads.

## What changed from version 1

| in version 1 | now |
|---|---|
| `results/<dataset>/<criterion>/*.json`, the paper's numbers | left the release: the verifier's package data, `src/cruxes_verify/expected/` in the verification repository, with the noise samples every tolerance is derived from |
| `scores/<dataset>/<criterion>/<question_id>.json`, our recorded reranker scores | left the inputs: provenance, written by the builder with `--provenance-out`, shipped since 2026-10-08 under `provenance/scores/`, and read only by the raw score check (`cruxes-verify compare --recorded-scores DIR`) |
| pools as recorded | unchanged in kind, and now stated: as produced, repeats kept; the package removes repeated texts before selection and reports how many (rule below) |
| a noise reference for March Madness only | a noise reference for both datasets |
| Metaculus post ids `null`, a fetch template | post ids for all 15 questions and a validated fetch script (section "Metaculus ids and the fetch step") |

## Principles

1. **One directory, self describing.** A reviewer is given this directory and
   nothing else of ours. Every file is listed in `MANIFEST.json` with its
   SHA-256 and size; the verifier refuses a release whose files do not match,
   except the reader's own `datasets/*/metaculus_fetched/` and top level
   directories whose names start with a dot (such as the `.git/` of a clone).
2. **Inputs only.** No number the paper prints is in the release, and no
   score computed from the inputs is among the inputs. A result shipped beside
   its inputs would only be checked against itself. The authors' recorded
   reranker scores ship apart, under `provenance/`, for the raw score check
   only.
3. **As produced.** Premise pools ship exactly as the models produced them, in
   recorded order, with their repeats. Removing repeats is a step of the
   method, so it belongs to the package, which reports what it removed.
4. **Package vocabulary.** Every key uses the package's names:
   `introspected`, `extracted`, `contrasts_per_side`, `question_id`.
5. **Generic questions.** A question is an opaque `question_id` plus its
   text and outcome. Nothing in the layout is specific to basketball or to
   Metaculus; a dataset is a directory of the same files.
6. **Ours versus theirs.** Everything we produced ships directly. Third party
   content ships only where its terms allow; otherwise the release ships the
   identifiers and a script that fetches it (section "Redistribution").

## Layout

```
<release>/
  README.md                     what this is, how to verify it, release status
  LICENSE                       the licence of our own outputs
  MANIFEST.json                 spec_version, release_status, every file: sha256, bytes, role
  REDISTRIBUTION.md             what may be redistributed and why
  provenance/
    README.md                   what the recorded scores are and how they were made
    scores/<dataset>/<criterion>/<question_id>.json   our recorded reranker scores
  method/
    matching_criteria.json      every matching criterion the paper reports
  datasets/<dataset>/
    dataset.json                name, description, question ids, provenance, build checks
    questions.json              one record per question
    introspected.json           {question_id: [premise, ...]}, as produced
    extracted.json              {question_id: [premise, ...]}, as produced
    forecasts/                  our forecasts, one file or directory per question
    provenance/                 generator metadata as recorded, both samples
    noise_reference/
      introspected.json         an independent second introspection sample
  datasets/march_madness/
    scouting_reports/           our per team scouting reports
  datasets/metaculus/           also, because Metaculus content may not ship:
    metaculus_post_ids.json     [{question_id, metaculus_post_id, url, id_source, id_status, ...}]
    fetch_metaculus.py          reads from the Metaculus API what a reader's token is shown
    metaculus_snapshot/         optional frozen copy; an empty slot unless Metaculus permits
    metaculus_fetched/          written by fetch_metaculus.py on the reader's machine; never shipped
```

There is no `results/`, and no `scores/` among the inputs; the recorded
scores are under `provenance/scores/`.

### `MANIFEST.json`

`spec_version` (2), `release_status` (`release`), `release_note`, `built`,
`builder`,
`internal_sources` (the recorded files the build read) and `files`: for every
file, its `sha256`, `bytes` and `role`, one of `method`, `questions`,
`premises`, `forecasts`, `scouting_reports`, `noise_reference`, `provenance`,
`third_party_access` and `documentation`. The verifier reads version 2 only.

### `method/matching_criteria.json`

```json
{
  "primary": "resolution",
  "criteria": [
    {"name": "resolution", "positive_instruction": "...", "negative_instruction": "...",
     "paper_label": "resolution matching (moderate)", "study_prompt_id": 1}
  ]
}
```

The primary criterion is the one the package ships as its default and the
one every main text number uses. The others are the paper's robustness
comparison; the verifier passes them to the package as a caller supplied
criterion, which is how the package takes any criterion other than its own.

### `datasets/<dataset>/dataset.json`

`name`, `description`, `question_ids` (sorted; exactly the questions the
paper's numbers cover), `inclusion_rule` (in words), `pools` (the pools are as
produced), `noise_reference` (what the second sample is), `provenance` (the
recorded source paths and their SHA-256) and `build_checks`: pool sizes, and
under `deduplication` the rule, the number of repeats the package's own
`dedupe_premises` removes from each pool, the number of questions with
repeats, the counts required, and the research code's deduplicated pools the
result was found equal to, text by text. The build fails on any mismatch. For
Metaculus also `forecasts` (how the forecast files were filed) and
`metaculus_post_ids` (how many ids are known, by status).

### `datasets/<dataset>/questions.json`

A list of records: `question_id`, `question` (the text as we recorded it),
`outcome` (dataset specific object, or `null`), `source` (the platform and,
for third party questions, its identifiers). A Metaculus record's `question`
is the title as our forecaster recorded it, its `outcome` is `null`, and
`question_text_and_resolution` says the question's text, resolution and
community forecast are pending written permission from Metaculus. Its
`source` carries `metaculus_post_id`, `id_status`, `alternative_post_ids`
where the id is ambiguous, and the recorded forecast directories.

### `introspected.json`, `extracted.json`

`{question_id: [premise, ...]}` with the full pool in recorded order,
repeats kept. A premise is a string. Recorded order matters: the package's
selection is a seeded permutation of the pool as given, after repeats are
removed.

The package removes repeats before it selects: two premises of
one pool are repeats when they are equal after collapsing every run of
whitespace to one space, case sensitive, with no fuzzy matching; the first
occurrence is kept verbatim in place. It records the counts in every report
(`metadata.deduplication`), and the verifier checks them exactly. On this
release: extracted, March Madness 88 repeats across 36 of 59 questions,
Metaculus 321 across 8 of 15; introspected, none in either.

### `noise_reference/introspected.json`

An independent second introspection sample of every question, same shape as
`introspected.json`. March Madness: the same model, prompts and schema as the
first (gpt-5.4-nano, five prompts, one call each, objects schema). Metaculus:
the paper's protocol rerun (gpt-5.4, prompts 0 to 10, 55 calls per question,
OpenAI batch `batch_6ab45598ade08190be679c8aac52dd14`). Runs on these samples
set the verifier's tolerances; the verification repository ships those runs'
numbers under `expected/noise/`, and `src/cruxes_verify/tolerances.py` says
how each tolerance follows from them.

### `forecasts/`

March Madness: one recorded forecast file per matchup. Metaculus: one
directory per question holding the recorded run directories, each with its
forecast files. Every Metaculus forecast file is filed under the question its
own text names, not under its directory: one recorded directory
(`2026-03-01_english-wikipedia-least`) holds `forecast15.json` of another
question (7,160,000 articles, Metaculus post 42238), which is therefore left
out. The build checks record how many files were refiled or left out.

## Where the results went

**The paper's numbers**: `src/cruxes_verify/expected/` in the verification
repository, written by `artifact_builder/build_expected.py`: `runs.json` (the
runs the paper prints), the numbers of each run in the package's report
format, the expected counts of removed repeats, and two sample runs per
dataset from which every tolerance is derived. They are the numbers the
paper prints: the research code's runs on the deduplicated pools (the
headline set inclusion numbers from the per question seeded runs of
2026-09-24, the March Madness coarser-cut sweep and within pool split from the
runs of 2026-09-23).

**Our recorded reranker scores**: provenance, not inputs; they ship under
`provenance/scores/` (role `provenance`), added to the release on 2026-10-08
unchanged from the build. `artifact_builder/build_release.py --provenance-out DIR` writes
`DIR/scores/<dataset>/<criterion>/<question_id>.json` from the caches of the
research code's runs on the deduplicated pools, at 25 premises a side and
under all three criteria, keyed by premise text (the texts reconstructed with
the research code's selection, since the caches store item ids only). Passing
`RELEASE/provenance/scores` to `cruxes-verify compare --recorded-scores` checks
a rerun's raw scores pair by pair.

## Redistribution

Decided 2026-09-23, updated 2026-09-24.

- **Ours ships directly**: forecasts, scouting reports, introspected and
  extracted premises (including the second samples), matching criteria.
- **Metaculus content does not.** Metaculus content is proprietary and its
  terms allow no attribution only redistribution; they carve out access
  through their API. The release ships, for each Metaculus question, its post
  id, our recorded title, and a fetch script. With an ordinary account token
  the API does not show the text, resolution or community forecast of a
  resolved question, and all 15 of ours are resolved, so the fetch script
  cannot deliver them either. The release marks them as pending written
  permission from Metaculus.
- **Verification is unaffected.** It needs our premises and the forecasts
  they came from, both of which ship, and none of the Metaculus text. The
  missing text is not a gap in reproducibility.
- **Optional frozen snapshot.** `datasets/metaculus/metaculus_snapshot/` is a
  documented, empty slot. It is filled only if Metaculus gives written
  permission (request to legal@metaculus.com, ForecastBench precedent).

### Metaculus ids and the fetch step

Added 2026-09-24.

**Why.** The terms of use make Metaculus content proprietary, forbid copying
it by automated means except through an API Metaculus provides, and grant no
license to redistribute it with attribution. So the release ships each
question's Metaculus post id, which is an identifier and not content, and a
script that reads the content from the API on the reader's machine.

Our Metaculus question ids are slugs of the titles (the first 80
characters), so they carry most of each title's words. They ship, as do our
recorded titles, because the paper's appendix prints the titles and they
identify the questions.

**The ids file.** `datasets/metaculus/metaculus_post_ids.json` is a JSON list
with one record per question, sorted by `question_id`: `question_id`,
`metaculus_post_id` (an integer, or `null` while unknown), `url`, `id_source`,
`id_status`, `alternative_post_ids` (only when ambiguous) and `evidence`.
`id_source` says where the id came from: `forecast_link` (our forecaster's web
search linked this post in its forecasts of the question) or
`api_title_search` (the API's title search, keeping only posts whose title
slug equals our `question_id`). `id_status` is `confirmed` (the API's title for
the post gives our `question_id` and no other post does), `ambiguous` (several
posts have exactly this title; the chosen one is named and the others listed)
or `unresolved`. The authors' copy is `artifact_builder/metaculus_post_ids.json`;
`artifact_builder/resolve_metaculus_post_ids.py` fills it from the API. The
builder copies it into the dataset and fills `source.metaculus_post_id` of
`questions.json` from it; the two must agree.

State on 2026-09-24, all 15 checked against the API with an account token: 12
`confirmed` (5 from forecast links: 42119, 42120, 42235, 42243, 42246; 7 from
the title search: 42116, 42117, 42118, 42237, 42240, 42241, 42245) and 3
`ambiguous`, where two posts carry the identical title. All 12 confirmed posts
are in the Spring 2026 FutureEval Bot Tournament, so for the three the copy in
that tournament is chosen: Khamenei 42232 (other: 42148, no tournament),
Hungary 42231 (other: 40005, no tournament), UK settlement 42230 (other: 42135,
Metaculus Cup Spring 2026, the one our forecasts link). The Kassandra run that
made the forecasts fetched questions by id but recorded only their titles, so
nothing recorded settles the three.

**The fetch step.** `datasets/metaculus/fetch_metaculus.py` is a copy of
`scripts/fetch_metaculus.py` in this repository, standard library only. It
reads `metaculus_post_ids.json` next to it (or `questions.json`, or `--ids`),
requests `https://www.metaculus.com/api/posts/<post_id>/` with the header
`Authorization: Token <token>` (as Kassandra does), one request every 4
seconds, retrying 429, 5xx and network errors with backoff, and writes
`metaculus_fetched/<question_id>.json` plus `metaculus_fetched/fetch_log.json`.
The token comes from `--env-file` (a `KEY=VALUE` file; only
`METACULUS_API_TOKEN` and `METACULUS_API_KEY` are read from it), else from the
environment variable `METACULUS_API_TOKEN` or `METACULUS_API_KEY`; it is never
printed or written. The API refuses anonymous requests (HTTP 403 "only
available to authenticated users", on `/api/posts/`, `/api2/questions/` and
the search). `--dry-run` fetches and prints without writing.

A per question file holds `question_id`, `metaculus_post_id`,
`metaculus_question_id`, `url`, `title`, `title_matches_question_id`,
`question_type`, `description`, `resolution_criteria`, `fine_print`, `status`,
`resolution`, `open_time`, `scheduled_close_time`, `actual_close_time`,
`scheduled_resolve_time`, `actual_resolve_time`, `resolution_set_time`,
`tournaments`, `nr_forecasters`, `community_forecast` (per aggregation method,
its `history` and `latest`), `community_forecast_latest` (the recency weighted
median), `withheld_by_api`, `api_fields` and `retrieved`.

What the API returned, 2026-09-24, with an ordinary account token: the same
keys for all 15 of our posts, and every title gives its `question_id`. Post keys:
`actual_close_time`, `actual_resolve_time`, `author_id`, `author_username`,
`coauthors`, `comment_count`, `created_at`, `curation_status`,
`curation_status_updated_at`, `edited_at`, `forecasts_count`,
`html_metadata_json`, `id`, `is_current_content_translated`, `key_factors`,
`nr_forecasters`, `open_time`, `projects`, `published_at`, `question`,
`resolved`, `scheduled_close_time`, `scheduled_resolve_time`, `short_title`,
`slug`, `status`, `subscriptions`, `title`, `url_title`, `user_permission`,
`vote`. Question keys: `actual_close_time`, `actual_resolve_time`,
`aggregations`, `all_options_ever`, `average_coverage`,
`coherence_link_aggregations`, `coherence_links`, `cp_reveal_time`,
`created_at`, `default_aggregation_method`, `default_score_type`,
`description`, `fine_print`, `group_rank`, `group_variable`, `id`,
`inbound_outcome_count`, `include_bots_in_aggregates`, `label`,
`my_forecasts`, `open_lower_bound`, `open_time`, `open_upper_bound`,
`options`, `options_history`, `options_order`, `possibilities`, `post_id`,
`question_weight`, `resolution`, `resolution_criteria`,
`resolution_set_time`, `scaling`, `scheduled_close_time`,
`scheduled_resolve_time`, `short_title`, `spot_scoring_time`, `status`,
`title`, `type`, `unit`.

**What that token is not shown.** The keys are all there, but for resolved
questions `description`, `resolution_criteria`, `fine_print` and `resolution`
are null (with `status` resolved and `resolution_set_time` set; so for all
15 of ours), and for every question tried, our 15, three other resolved and
two open ones, each aggregation's `history` and `latest` are null or empty. Open questions do return their description and
resolution criteria. Query parameters (`include_description`, `with_cp`,
`include_cp_history`) change nothing, and `/api/posts/<id>/download-data/`
answers 403 "Use of this endpoint is restricted. See
https://www.metaculus.com/api for instructions on requesting access". All 15
of our questions are resolved, so with an ordinary token the fetch yields
titles, ids, times, status and tournament, and no question text, resolution or
community forecast. Each file lists what was withheld in `withheld_by_api`.
Getting the rest to readers needs Metaculus: elevated API access for readers,
or written permission to ship the snapshot below. The release therefore
shipped without the Metaculus text, resolutions and community forecasts,
marked pending written permission; verification does not need them.

**The snapshot slot.** `metaculus_snapshot/` holds raw API responses as
`<post_id>.json`, the format `fetch_metaculus.py --save-raw` writes and
`--snapshot-dir` reads. It is filled only with written permission from
Metaculus.

**The verifier and the fetched files.** `cruxes-verify check` refuses files that
are not in the manifest, and `metaculus_fetched/` is created after the
manifest was written, so the verifier skips `datasets/*/metaculus_fetched/`.
A reader can fetch inside the release and still check it.

**The API and tokens, in short.** The Metaculus API answers anonymous
requests with HTTP 403, so the fetch step needs a free Metaculus account
token. With one, a resolved question comes back with its title, times, status
and tournament, and with null description, resolution criteria, fine print,
resolution and community history. Our question ids are the first 80
characters of slugs of the titles.

## What shipped (2026-10-08)

The release status is `release`.

1. **Titles and question ids.** Our recorded Metaculus titles and our
   question ids, which are slugs of the titles, ship: the paper's appendix
   prints them.
2. **Post ids.** Every Metaculus question has one (12 confirmed, 3
   ambiguous). The three ambiguous ones are listed with their alternatives in
   `datasets/metaculus/metaculus_post_ids.json` (`alternative_post_ids`):
   Khamenei 42232 (other: 42148), Hungary 42231 (other: 40005), UK settlement
   42230 (other: 42135).
3. **Metaculus text.** The release carries no Metaculus content beyond ids
   and our recorded titles. Question text, resolutions and community
   forecasts are pending written permission from Metaculus, and would ship in
   the snapshot slot. Verification does not depend on them.
4. **Fetch script.** Run against the API with a token on 2026-09-24; every
   fetched title gives its question id.
5. **Recorded scores.** The authors' recorded reranker scores ship under
   `provenance/scores/` (role `provenance`), for the raw score check.

## Contents (built 2026-09-24, released 2026-10-08)

Built by `artifact_builder/build_release.py` from the authors' internal runs,
through `scripts/authors_cluster/build_artifact.slurm` (output paths in
`scripts/authors_cluster/common.sh`). Released on 2026-10-08 with the dataset
files unchanged from the build; the README and REDISTRIBUTION.md were
rewritten by hand, and LICENSE and `provenance/` added.

| dataset | questions | introspected pool | noise reference | extracted pool |
|---|---|---|---|---|
| `march_madness` | the 59 resolved matchups of `march_madness_objects59` | objects schema pool (gpt-5.4-nano, 5 calls) | `march_madness_objects59_rep2` | the matchups' records of the March 2026 extraction, 88 repeats |
| `metaculus` | 15 | gpt-5.4, 55 calls | a second pool under the same protocol, 2026-09-23 | the 2026-03-31 extraction, 321 repeats |

## Not included

- The pools of the appendix experiments: the open weight replication pools,
  the contested March Madness matchups, the example scouting reports of the
  appendix.
- The granularity sweep and within pool split for Metaculus (never computed).
- The generation-stage scripts and prompt texts.
- The parallel array introspection pool of March 2026, its clean
  recomputation, and the April canonical file. They are provenance for an
  appendix note on the parser defect and are not verification targets.

"""Build the data release from our internal runs.

AUTHORS ONLY. This and ``build_expected.py`` are the only programs in this
repository that know our internal directory layout, and ``verify`` never
imports them. A reviewer receives what this writes, never what it reads.

    python artifact_builder/build_release.py \\
        --out /net/projects/veitch/forecast-cruxes/Data/runs/refactor_proposal_4_release \\
        --provenance-out /net/projects/veitch/forecast-cruxes/Data/runs/refactor_proposal_4_provenance

Everything under ``Data/`` is opened read only. Neither output directory may
exist; the build refuses to write into one that does, and it checks every
input before it creates either.

The release holds inputs only (``docs/DATA_RELEASE_SPEC.md``): the premises as
produced, repeats kept, the forecasts they came from, outcomes, scouting
reports, the second introspection samples as noise references and the
matching criteria. No results and no recorded scores: the paper's numbers are
the verifier's package data, and the recorded reranker scores are provenance,
written only with ``--provenance-out`` into a separate directory (the release
of 2026-10-08 carries them under ``provenance/scores/``, added after the
build).

The build checks what the package will do to the raw pools. It applies the
package's own ``dedupe_premises`` to every pool, requires the counts of
removed repeats to be the ones the paper reports, and requires the pools that
remain to equal, question by question and text by text, the research code's
deduplicated pools that produced the paper's numbers. Any mismatch fails the
build before anything is written.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from cruxes.dedupe import DEDUPE_RULE, dedupe_premises

from legacy import LEGACY_SEED_LABELS, legacy_selection, sha256

PROJECT = Path("/net/projects/veitch/forecast-cruxes")
RUNS = PROJECT / "Data" / "runs"
PROMPTS = PROJECT / "Data" / "prompts" / "reranker_prompts.json"

SPEC_VERSION = 2
RELEASE_STATUS = "release"

#: study prompt id -> package criterion name, paper label. Resolution first: primary.
CRITERIA = {
    1: ("resolution", "resolution matching (moderate)"),
    0: ("equivalence", "equivalence matching (strict)"),
    9: ("debate", "debate matching (broad)"),
}

MM = RUNS / "march_madness_objects59" / "apriori"
MM_REP2 = RUNS / "march_madness_objects59_rep2" / "apriori"
MM_DEDUP = RUNS / "march_madness_objects59_dedup"
MM_SOURCES = {
    "introspected": MM / "apriori_contrasts_merged.json",
    "introspection_metadata": MM / "apriori_metadata_2026-09-21T22-08-29.json",
    "introspected_noise_reference": MM_REP2 / "apriori_contrasts_merged.json",
    "introspection_metadata_noise_reference": MM_REP2 / "apriori_metadata_2026-09-22T13-28-37.json",
    # The file march_madness_objects59/cruxes/intermediate_contrasts_latest.json resolves to (348 MB).
    "extracted": RUNS / "march_madness" / "cruxes" / "intermediate_contrasts_2026-03-19T03-52-42.json",
    "extracted_deduplicated_by_research_code": MM_DEDUP / "cruxes" / "intermediate_contrasts_dedup_2026-09-23T16-21-28.json",
    "question_list": MM_DEDUP / "apriori" / "set_inclusion_resolved_p1_pos_only_2026-09-23T17-35-08.json",
    "ground_truth": PROJECT / "march_madness" / "ground_truth_full_2026.json",
    "forecasts_dir": RUNS / "march_madness" / "matchups",
    "scouting_reports_dir": RUNS / "march_madness" / "teams",
}
MM_SCORE_CACHE = str(MM_DEDUP / "apriori" / "similarity_matrices" / "{question_id}_resolved_p{prompt_id}_k25_seed42_raw4.json")

META_RUN = RUNS / "02_28_26_gpt-5-nano_OpenAI-search"
META_REP2 = RUNS / "02_28_26_gpt-5-nano_OpenAI-search_rep2" / "apriori"
META_DEDUP = RUNS / "02_28_26_gpt-5-nano_OpenAI-search_dedup"
META_SOURCES = {
    "introspected": META_RUN / "apriori" / "apriori_contrasts_2026-03-31T18-55-23.json",
    "introspection_metadata": META_RUN / "apriori" / "apriori_metadata_2026-03-31T18-55-23.json",
    "introspected_noise_reference": META_REP2 / "apriori_contrasts_2026-09-23T17-53-03.json",
    "introspection_metadata_noise_reference": META_REP2 / "apriori_metadata_2026-09-23T17-53-03.json",
    "extracted": META_RUN / "cruxes" / "intermediate_contrasts_2026-03-31T16-34-41.json",
    "extracted_deduplicated_by_research_code": META_DEDUP / "cruxes" / "intermediate_contrasts_dedup_2026-09-23T16-21-28.json",
    "question_list": META_DEDUP / "apriori" / "set_inclusion_all_p1_pos_only_2026-09-23T16-50-14.json",
    "forecasts_dir": META_RUN / "forecasts",
}
META_SCORE_CACHE = str(META_DEDUP / "apriori" / "similarity_matrices" / "{question_id}_all_p{prompt_id}_k25_seed42_raw4.json")

#: (removed repeats, questions with repeats) per pool, as the paper reports them (R2).
EXPECTED_DEDUPE = {
    "march_madness": {"introspected": (0, 0), "extracted": (88, 36)},
    "metaculus": {"introspected": (0, 0), "extracted": (321, 8)},
}

POOLS = ("introspected", "extracted")
MATCHUP_QUESTION = re.compile(r"Who wins:\s*(.+?)\s+vs\s+(.+?)\s*\?")
FETCH_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_metaculus.py"
POST_IDS = Path(__file__).resolve().parent / "metaculus_post_ids.json"


class BuildCheckError(ValueError):
    """An input is not what the paper's numbers were computed from."""


def load(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=indent, ensure_ascii=False)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as handle:
        handle.write(text)


def copy_new(source: Path, target: Path) -> None:
    """Copy a file to a path that must not exist yet."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(source, "rb") as reader, open(target, "xb") as writer:
        shutil.copyfileobj(reader, writer)


def team_slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("'", "").replace(".", "").replace("&", "")


def matchup_slug(question: str):
    match = MATCHUP_QUESTION.match(question)
    if not match:
        return None
    return f"{team_slug(match.group(1).strip())}-vs-{team_slug(match.group(2).strip())}"


def question_slug(question: str) -> str:
    """The research code's slug for a generic question (generate_generic.py)."""
    slug = "".join(c if c.isalnum() or c == " " else "" for c in question.lower())
    return "-".join(slug.split())[:80]


def index_pool(records: list, slug_of, wanted: set) -> dict:
    """{question_id: premises} for the wanted questions, refusing duplicates."""
    pools, seen = {}, Counter()
    for record in records:
        slug = slug_of(record["question"])
        if slug in wanted:
            seen[slug] += 1
            pools[slug] = list(record["contrasts"])
    repeated = [s for s, n in seen.items() if n > 1]
    if repeated:
        raise BuildCheckError(f"more than one record for {repeated[:5]}")
    missing = wanted - set(pools)
    if missing:
        raise BuildCheckError(f"no record for {sorted(missing)[:5]}")
    return {q: pools[q] for q in sorted(pools)}


def pool_report(name: str, pools: dict) -> dict:
    sizes = [len(p) for p in pools.values()]
    report = {
        "questions": len(pools),
        "premises": sum(sizes),
        "min_pool": min(sizes),
        "max_pool": max(sizes),
    }
    print(f"  {name}: {report}")
    return report


def question_ids_of(gather_path: Path) -> list:
    """The questions a recorded gather covers at 25 a side: the ones the paper's numbers cover."""
    return sorted(load(gather_path)["per_k"]["25"]["per_matchup"])


# The checks of what the package will do -------------------------------------


def dedupe_pools(pools: dict) -> tuple:
    """``(deduplicated pools, counts)`` under the package's own rule."""
    deduped, per_question = {}, {}
    for question_id, pool in pools.items():
        kept, dropped = dedupe_premises(pool)
        deduped[question_id] = kept
        per_question[question_id] = {"given": len(pool), "kept": len(kept), "removed": len(dropped)}
    counts = {
        "removed": sum(c["removed"] for c in per_question.values()),
        "questions_with_repeats": sum(1 for c in per_question.values() if c["removed"]),
        "per_question": per_question,
    }
    return deduped, counts


def check_dedupe_counts(where: str, counts: dict, expected: tuple) -> None:
    found = (counts["removed"], counts["questions_with_repeats"])
    if found != tuple(expected):
        raise BuildCheckError(
            f"{where}: the package removes {found[0]} repeats across {found[1]} questions, "
            f"the paper reports {expected[0]} across {expected[1]}"
        )


def check_same_pools(where: str, ours: dict, research: dict) -> None:
    """Question by question and text by text, or a BuildCheckError naming the first difference."""
    if set(ours) != set(research):
        raise BuildCheckError(
            f"{where}: questions differ from the research code's; only ours "
            f"{sorted(set(ours) - set(research))[:5]}, only theirs {sorted(set(research) - set(ours))[:5]}"
        )
    for question_id in sorted(ours):
        a, b = ours[question_id], research[question_id]
        if a == b:
            continue
        first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        raise BuildCheckError(
            f"{where}: {question_id} differs from the research code's deduplicated pool "
            f"({len(a)} against {len(b)} premises, first difference at position {first})"
        )


def check_pools(dataset: str, introspected: dict, extracted: dict, research_extracted: dict,
                research_path: Path) -> tuple:
    """Apply the package's dedupe to both pools and check it against the paper. Returns
    ``(deduplicated introspected, deduplicated extracted, build check record)``."""
    expected = EXPECTED_DEDUPE[dataset]
    deduped_i, counts_i = dedupe_pools(introspected)
    deduped_e, counts_e = dedupe_pools(extracted)
    check_dedupe_counts(f"{dataset} introspected", counts_i, expected["introspected"])
    check_dedupe_counts(f"{dataset} extracted", counts_e, expected["extracted"])
    # The research code's deduplicated introspected pool is the recorded pool
    # itself (it had no repeats), so the count check covers it.
    check_same_pools(f"{dataset} extracted", deduped_e, research_extracted)
    record = {"rule": DEDUPE_RULE}
    for pool, counts in (("introspected", counts_i), ("extracted", counts_e)):
        record[pool] = {
            "removed": counts["removed"],
            "questions_with_repeats": counts["questions_with_repeats"],
            "required": list(expected[pool]),
        }
    record["extracted"]["equal_to_research_code_pools"] = {"path": str(research_path), "sha256": sha256(research_path)}
    record["introspected"]["equal_to_research_code_pools"] = "the recorded pool itself, which has no repeats"
    print(
        f"  dedupe: introspected {counts_i['removed']} over {counts_i['questions_with_repeats']}, "
        f"extracted {counts_e['removed']} over {counts_e['questions_with_repeats']}; "
        "deduplicated extracted pools equal the research code's"
    )
    return deduped_i, deduped_e, record


# Loading and checking, nothing written ---------------------------------------


def prepare_march_madness() -> dict:
    print("march_madness")
    questions = question_ids_of(MM_SOURCES["question_list"])
    wanted = set(questions)
    ground_truth = {g["matchup_file"]: g for g in load(MM_SOURCES["ground_truth"])}
    if not wanted <= set(ground_truth):
        raise BuildCheckError(f"no ground truth for {sorted(wanted - set(ground_truth))}")
    introspected = index_pool(load(MM_SOURCES["introspected"]), matchup_slug, wanted)
    noise = index_pool(load(MM_SOURCES["introspected_noise_reference"]), matchup_slug, wanted)
    print("  loading the extraction (348 MB)")
    extracted = index_pool(load(MM_SOURCES["extracted"]), matchup_slug, wanted)
    research = index_pool(load(MM_SOURCES["extracted_deduplicated_by_research_code"]), matchup_slug, wanted)
    deduped_i, deduped_e, dedupe_record = check_pools(
        "march_madness", introspected, extracted, research, MM_SOURCES["extracted_deduplicated_by_research_code"]
    )
    dedupe_record["noise_reference_introspected"] = {
        k: v for k, v in dedupe_pools(noise)[1].items() if k != "per_question"
    }
    missing_forecasts = [q for q in questions if not (MM_SOURCES["forecasts_dir"] / f"{q}.json").is_file()]
    if missing_forecasts:
        raise BuildCheckError(f"no forecast file for {missing_forecasts[:5]}")
    return {
        "questions": questions,
        "ground_truth": ground_truth,
        "introspected": introspected,
        "extracted": extracted,
        "noise_reference": noise,
        "deduped": {"introspected": deduped_i, "extracted": deduped_e},
        "checks": {
            "introspected": pool_report("introspected, as produced", introspected),
            "extracted": pool_report("extracted, as produced", extracted),
            "introspected_noise_reference": pool_report("introspected noise reference", noise),
            "deduplication": dedupe_record,
        },
    }


def file_forecasts(files_by_directory: dict, question_of, wanted: set) -> tuple:
    """File every forecast under the question its own text names.

    ``files_by_directory`` is ``{directory name: [forecast files]}`` and
    ``question_of(file)`` the question id a file's own text gives. A recorded
    directory can hold a forecast of another question (the directory names
    collided), so the directory is not trusted. Returns ``(filed, record)``:
    ``filed`` is ``{question_id: {directory name: [files]}}`` for the wanted
    questions, and ``record`` counts the files refiled (their question is
    wanted but differs from the one of the directory's first file, which is
    how directories were assigned before) and the files left out (their
    question is not one of the dataset's).
    """
    filed, refiled, left_out, total = {}, [], [], 0
    for directory, files in sorted(files_by_directory.items()):
        questions = [question_of(f) for f in files]
        for f, question_id in zip(files, questions):
            total += 1
            where = f"{directory}/{Path(f).name}"
            if question_id not in wanted:
                left_out.append({"file": where, "question_id": question_id})
                continue
            if question_id != questions[0]:
                refiled.append({"file": where, "question_id": question_id})
            filed.setdefault(question_id, {}).setdefault(directory, []).append(f)
    record = {
        "forecast_files": total,
        "shipped": total - len(left_out),
        "refiled_by_own_question": refiled,
        "left_out_other_question": left_out,
    }
    return filed, record


def metaculus_forecasts(wanted: set) -> tuple:
    """Our Metaculus forecast files, filed by the question each one states."""
    files_by_directory = {}
    for directory in sorted(META_SOURCES["forecasts_dir"].iterdir()):
        files = sorted(directory.glob("forecast*.json")) if directory.is_dir() else []
        if files:
            files_by_directory[directory.name] = files
    filed, record = file_forecasts(
        files_by_directory, lambda f: question_slug(load(f)["question"]), wanted
    )
    print(
        f"  forecasts: {record['shipped']} of {record['forecast_files']} files shipped, "
        f"{len(record['refiled_by_own_question'])} refiled by their own question, "
        f"{len(record['left_out_other_question'])} left out as forecasts of another question"
    )
    return filed, record


def post_ids_by_question(records: list, questions: list) -> tuple:
    """``({question_id: record}, build check record)``; the ids file must cover exactly our questions."""
    by_question = {r["question_id"]: r for r in records}
    if len(by_question) != len(records) or sorted(by_question) != sorted(questions):
        raise BuildCheckError(
            "metaculus_post_ids.json must hold one record per question of the dataset; "
            f"only in the file {sorted(set(by_question) - set(questions))[:3]}, "
            f"missing {sorted(set(questions) - set(by_question))[:3]}"
        )
    with_id = sorted(q for q, r in by_question.items() if r.get("metaculus_post_id") is not None)
    statuses = Counter(r.get("id_status") for r in records)
    record = {
        "with_post_id": len(with_id),
        "without_post_id": sorted(set(questions) - set(with_id)),
        "by_status": dict(sorted(statuses.items(), key=lambda kv: str(kv[0]))),
        "ambiguous": [
            {
                "question_id": q,
                "metaculus_post_id": r.get("metaculus_post_id"),
                "alternative_post_ids": r.get("alternative_post_ids", []),
            }
            for q, r in sorted(by_question.items())
            if r.get("id_status") == "ambiguous"
        ],
        "note": (
            "a null post id needs a Metaculus API token to resolve "
            "(artifact_builder/resolve_metaculus_post_ids.py); an ambiguous one names the "
            "post chosen among posts of identical title and lists the others"
        ),
    }
    print(
        f"  post ids: {len(with_id)} of {len(questions)} known, by status {record['by_status']}"
    )
    return by_question, record


def prepare_metaculus() -> dict:
    print("metaculus")
    questions = question_ids_of(META_SOURCES["question_list"])
    wanted = set(questions)
    introspected_records = load(META_SOURCES["introspected"])
    text_of = {question_slug(r["question"]): r["question"] for r in introspected_records}
    introspected = index_pool(introspected_records, question_slug, wanted)
    noise = index_pool(load(META_SOURCES["introspected_noise_reference"]), question_slug, wanted)
    extracted = index_pool(load(META_SOURCES["extracted"]), question_slug, wanted)
    research = index_pool(load(META_SOURCES["extracted_deduplicated_by_research_code"]), question_slug, wanted)
    deduped_i, deduped_e, dedupe_record = check_pools(
        "metaculus", introspected, extracted, research, META_SOURCES["extracted_deduplicated_by_research_code"]
    )
    dedupe_record["noise_reference_introspected"] = {
        k: v for k, v in dedupe_pools(noise)[1].items() if k != "per_question"
    }
    forecasts, forecast_record = metaculus_forecasts(wanted)
    post_ids_records = load(POST_IDS)
    post_ids, post_id_record = post_ids_by_question(post_ids_records, questions)
    return {
        "questions": questions,
        "text_of": text_of,
        "introspected": introspected,
        "extracted": extracted,
        "noise_reference": noise,
        "forecasts": forecasts,
        "post_ids": post_ids,
        "post_ids_records": post_ids_records,
        "deduped": {"introspected": deduped_i, "extracted": deduped_e},
        "checks": {
            "introspected": pool_report("introspected, as produced", introspected),
            "extracted": pool_report("extracted, as produced", extracted),
            "introspected_noise_reference": pool_report("introspected noise reference", noise),
            "deduplication": dedupe_record,
            "forecasts": forecast_record,
            "questions_with_two_forecast_directories": sum(
                1 for q in questions if len(forecasts.get(q, {})) > 1
            ),
            "questions_without_forecasts": [q for q in questions if q not in forecasts],
            "metaculus_post_ids": post_id_record,
        },
    }


# Writing the release ---------------------------------------------------------


def criteria_file() -> dict:
    prompts = {p["id"]: p for p in load(PROMPTS)}
    return {
        "primary": "resolution",
        "note": "Instruction texts verbatim from the study's reranker prompt file.",
        "criteria": [
            {
                "name": name,
                "positive_instruction": prompts[pid]["pos_instruction"],
                "negative_instruction": prompts[pid]["neg_instruction"],
                "paper_label": label,
                "study_prompt_id": pid,
                "study_prompt_name": prompts[pid]["name"],
            }
            for pid, (name, label) in CRITERIA.items()
        ],
    }


def provenance_of(sources: dict) -> dict:
    return {
        name: {"path": str(path), "sha256": sha256(path)}
        for name, path in sources.items()
        if path.is_file()
    }


#: What the Metaculus records carry instead of the question's text and resolution.
METACULUS_PENDING = (
    "pending written permission from Metaculus: the description, resolution criteria, "
    "fine print, resolution and community forecast are Metaculus content, and the API "
    "withholds them for resolved questions from an ordinary account token"
)

POOLS_NOTE = (
    "introspected.json and extracted.json hold every premise as the models produced it, in "
    "recorded order, repeats kept. The package removes repeated texts before it selects "
    "(rule in build_checks.deduplication) and reports how many it removed."
)


def write_march_madness(out: Path, data: dict) -> None:
    base = out / "datasets" / "march_madness"
    write_json(base / "introspected.json", data["introspected"])
    write_json(base / "extracted.json", data["extracted"])
    write_json(base / "noise_reference" / "introspected.json", data["noise_reference"])

    records, teams = [], set()
    for question_id in data["questions"]:
        forecast_file = MM_SOURCES["forecasts_dir"] / f"{question_id}.json"
        forecast = load(forecast_file)
        teams.update(team_slug(forecast[side]) for side in ("team-a", "team-b"))
        copy_new(forecast_file, base / "forecasts" / forecast_file.name)
        truth = data["ground_truth"][question_id]
        records.append(
            {
                "question_id": question_id,
                "question": f"Who wins: {forecast['team-a']} vs {forecast['team-b']}?",
                "outcome": {"winner": truth["winner"], "round": truth["round"]},
                "source": {"platform": "NCAA men's tournament 2026"},
            }
        )
    write_json(base / "questions.json", records)

    copied = 0
    for team in sorted(teams):
        report = MM_SOURCES["scouting_reports_dir"] / f"{team}.json"
        if report.exists():
            copy_new(report, base / "scouting_reports" / report.name)
            copied += 1
    print(f"  scouting reports: {copied} of {len(teams)} teams have one")

    copy_new(MM_SOURCES["introspection_metadata"], base / "provenance" / "introspection_metadata.json")
    copy_new(
        MM_SOURCES["introspection_metadata_noise_reference"],
        base / "provenance" / "introspection_metadata_noise_reference.json",
    )
    checks = {**data["checks"], "scouting_reports_copied": copied, "teams": len(teams)}
    write_json(
        base / "dataset.json",
        {
            "name": "march_madness",
            "description": (
                "2026 NCAA men's tournament matchups. Introspected premises: "
                "gpt-5.4-nano asked in advance what would decide each matchup, "
                "five prompts, one call each, array of objects response schema. "
                "Extracted premises: gpt-5.4-mini extraction from pairs of "
                "disagreeing forecasts."
            ),
            "question_ids": data["questions"],
            "inclusion_rule": "every matchup with a known winner that both pools cover (59)",
            "pools": POOLS_NOTE,
            "noise_reference": (
                "noise_reference/introspected.json is an independent second "
                "introspection sample with the same model, prompts and schema; "
                "the verifier's tolerances are measured from runs on it"
            ),
            "provenance": provenance_of(MM_SOURCES),
            "build_checks": checks,
        },
    )


def write_metaculus(out: Path, data: dict) -> None:
    base = out / "datasets" / "metaculus"
    write_json(base / "introspected.json", data["introspected"])
    write_json(base / "extracted.json", data["extracted"])
    write_json(base / "noise_reference" / "introspected.json", data["noise_reference"])

    records = []
    for question_id in data["questions"]:
        directories = data["forecasts"].get(question_id, {})
        for directory, files in sorted(directories.items()):
            for f in files:
                copy_new(f, base / "forecasts" / question_id / directory / Path(f).name)
        ids = data["post_ids"][question_id]
        source = {
            "platform": "Metaculus",
            "metaculus_post_id": ids.get("metaculus_post_id"),
            "id_status": ids.get("id_status"),
            "forecast_directories": sorted(directories),
        }
        if ids.get("alternative_post_ids"):
            source["alternative_post_ids"] = ids["alternative_post_ids"]
        if source["metaculus_post_id"] is None:
            source["note"] = "post id unresolved; needs a Metaculus API token; fill before release"
        records.append(
            {
                "question_id": question_id,
                "question": data["text_of"][question_id],
                "question_text_and_resolution": METACULUS_PENDING,
                "outcome": None,
                "source": source,
            }
        )
    write_json(base / "questions.json", records)
    write_json(base / "metaculus_post_ids.json", data["post_ids_records"])
    copy_new(FETCH_SCRIPT, base / "fetch_metaculus.py")
    write_text(
        base / "metaculus_snapshot" / "README.md",
        "Optional slot. Left empty on purpose: a frozen copy of Metaculus content\n"
        "goes here only once Metaculus has given written permission to\n"
        "redistribute it. Until then run ../fetch_metaculus.py.\n",
    )
    copy_new(META_SOURCES["introspection_metadata"], base / "provenance" / "introspection_metadata.json")
    copy_new(
        META_SOURCES["introspection_metadata_noise_reference"],
        base / "provenance" / "introspection_metadata_noise_reference.json",
    )
    write_json(
        base / "dataset.json",
        {
            "name": "metaculus",
            "description": (
                "15 binary Metaculus questions open in February 2026. Introspected "
                "premises: gpt-5.4, eleven prompts, 55 calls. Extracted premises: "
                "gpt-5.4-mini extraction from pairs of disagreeing forecasts by an "
                "automated forecaster (gpt-5-nano with web search)."
            ),
            "question_ids": data["questions"],
            "inclusion_rule": "every question both pools cover (15)",
            "pools": POOLS_NOTE,
            "noise_reference": (
                "noise_reference/introspected.json is an independent second "
                "introspection sample under the same protocol (gpt-5.4, prompts 0 to 10, "
                "55 calls, OpenAI batch batch_6ab45598ade08190be679c8aac52dd14); the "
                "verifier's tolerances are measured from runs on it"
            ),
            "provenance": provenance_of(META_SOURCES),
            "build_checks": data["checks"],
        },
    )


README = """# forecast-cruxes data release

Built {built} by `forecast-cruxes-verify/artifact_builder/build_release.py`
from our internal runs, read only. Layout and contents: `docs/DATA_RELEASE_SPEC.md`
in the verification repository (spec version {spec}). Every file is listed in
MANIFEST.json with its SHA-256.

This directory holds the paper's inputs and nothing computed from them: the
premises as the models produced them (repeats kept; the package removes them),
the forecasts they came from, outcomes, scouting reports, the second
introspection samples used as noise references, and the matching criteria.
The paper's numbers are results of running the package on these inputs, and
they ship with the verification repository, which checks them.

The Metaculus dataset ships, for each of its {n_metaculus} questions, the
Metaculus post id (`datasets/metaculus/metaculus_post_ids.json`, copied into
`source.metaculus_post_id` of `questions.json`; {post_ids_known} of
{n_metaculus} known), our recorded title (in `questions.json`, and quoted in
our forecast files), our forecasts and our premises. The question's text
(description, resolution criteria, fine print), its resolution and the
community forecast are Metaculus content and are marked "pending written
permission from Metaculus". `fetch_metaculus.py` cannot fill that gap for
readers: with an ordinary account token the API withholds exactly those
fields for resolved questions, and all {n_metaculus} are resolved. It
delivers ids, titles, times, status and tournament. Verification is
unaffected: it reads the premises and nothing of the question text.

What ships for Metaculus:

1. Our recorded titles and our question ids, which are slugs of the titles.
   They ship because the paper's appendix prints them and they identify the
   questions.
2. A post id for each question. {post_ids_ambiguous} of them are ambiguous:
   two posts carry the identical title, the one in the Spring 2026 FutureEval
   Bot Tournament is chosen, and the other is listed in
   `alternative_post_ids` of `datasets/metaculus/metaculus_post_ids.json`.
   Nothing we recorded settles them.
3. Not the text, resolutions or community forecasts of the Metaculus
   questions: they are pending written permission from Metaculus, and would
   ship in `datasets/metaculus/metaculus_snapshot/` if it is given.

`cruxes-verify check` ignores `datasets/*/metaculus_fetched/`, where the fetch
script writes by default, so fetching inside this directory does not break the check.

To verify the paper from this directory:

    cruxes-verify all --artifact <this directory> --work-dir <an empty directory>

(the GPU stage needs a CUDA device; see the verification repository's README).
"""

REDISTRIBUTION = """# Redistribution

Decided 2026-09-23, updated 2026-09-24.

Ours, shipped directly: forecasts, scouting reports, introspected and extracted
premises (including the second introspection samples), matching criteria.

Metaculus content is proprietary; its terms allow no attribution only
redistribution and carve out access through their API. For each Metaculus
question the release therefore ships its post id
(`datasets/metaculus/metaculus_post_ids.json`), our recorded title, and
`datasets/metaculus/fetch_metaculus.py`, which reads from the API what a
reader's account token is shown. For resolved questions, which all of ours
are, that is ids, titles, times, status and tournament, and not the question
text, resolution or community forecast. Those are marked pending written
permission from Metaculus; `datasets/metaculus/metaculus_snapshot/` is the
slot for them, filled only if Metaculus gives it (legal@metaculus.com).
Verification needs none of them.
"""


def file_role(relative: str) -> str:
    """What a release file is, for the manifest."""
    parts = relative.split("/")
    if parts[0] == "method":
        return "method"
    if parts[0] != "datasets" or len(parts) < 3:
        return "documentation"
    name = parts[2]
    if name in ("introspected.json", "extracted.json"):
        return "premises"
    if name in ("dataset.json", "questions.json"):
        return "questions"
    if name in ("forecasts", "scouting_reports", "noise_reference", "provenance"):
        return name
    if name in ("fetch_metaculus.py", "metaculus_post_ids.json", "metaculus_snapshot"):
        return "third_party_access"
    return "other"


def write_manifest(out: Path, sources: dict) -> dict:
    files = {}
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        relative = path.relative_to(out).as_posix()
        files[relative] = {"sha256": sha256(path), "bytes": path.stat().st_size, "role": file_role(relative)}
    manifest = {
        "spec_version": SPEC_VERSION,
        "release_status": RELEASE_STATUS,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "forecast-cruxes-verify/artifact_builder/build_release.py",
        "internal_sources": sources,
        "files": files,
    }
    write_json(out / "MANIFEST.json", manifest)
    print(f"manifest: {len(files)} files")
    return manifest


# Internal provenance ---------------------------------------------------------


def recorded_scores(cache: Path, introspected: list, extracted: list, question_id: str) -> dict:
    """One recorded cache, keyed by the premise texts the research code selected.

    ``introspected`` and ``extracted`` are the deduplicated pools the recorded
    run selected from.
    """
    recorded = load(cache)
    selected_i = legacy_selection(introspected, question_id, LEGACY_SEED_LABELS[0])
    selected_e = legacy_selection(extracted, question_id, LEGACY_SEED_LABELS[1])
    if (len(selected_i), len(selected_e)) != (recorded["max_k_a"], recorded["max_k_b"]):
        raise BuildCheckError(
            f"{cache}: reconstructed {len(selected_i)}+{len(selected_e)} premises, "
            f"recorded {recorded['max_k_a']}+{recorded['max_k_b']}"
        )
    n = len(selected_i) + len(selected_e)
    for key in ("pos_fwd", "pos_rev", "neg_fwd", "neg_rev"):
        if len(recorded[key]) != n or any(len(row) != n for row in recorded[key]):
            raise BuildCheckError(f"{cache}: {key} is not {n} by {n}")
        for row in recorded[key]:
            if any(value is None or value != value for value in row):
                raise BuildCheckError(f"{cache}: {key} holds a missing score")
    return {
        "introspected": selected_i,
        "extracted": selected_e,
        **{key: recorded[key] for key in ("pos_fwd", "pos_rev", "neg_fwd", "neg_rev")},
        "provenance": {
            "recorded_cache": str(cache),
            "recorded_cache_sha256": sha256(cache),
            "selection": (
                "reconstructed: seeded prefix of the deduplicated pools with the research "
                f"code's labels {list(LEGACY_SEED_LABELS)} and base seed 42; the recorded "
                "cache stores item ids only"
            ),
            "batching": "adaptive, four blocks of directions (research code)",
        },
    }


PROVENANCE_README = """# Recorded reranker scores (provenance)

Built {built} by `forecast-cruxes-verify/artifact_builder/build_release.py`
beside the data release `{release}`.

`scores/<dataset>/<criterion>/<question_id>.json` holds the reranker scores
the research code recorded in the runs on the deduplicated pools that produced
the paper's numbers (2026-09-23), at 25 premises a side, keyed by premise
text. The texts were reconstructed with the research code's selection applied
to the deduplicated pools, since the recorded caches store item ids only; the
number of premises is checked against each cache. Each file names its cache
and the cache's SHA-256.

These are results, not inputs, so the build writes them apart from the
inputs; the release of 2026-10-08 carries them under `provenance/scores/`.
`cruxes-verify compare --recorded-scores <this directory>/scores` uses them to
check a rerun's raw scores pair by pair wherever
both runs scored the same two premises.
"""


def write_scores(provenance_out: Path, dataset: str, data: dict, cache_pattern: str) -> int:
    written = 0
    for prompt_id, (criterion, _) in CRITERIA.items():
        for question_id in data["questions"]:
            cache = Path(cache_pattern.format(question_id=question_id, prompt_id=prompt_id))
            write_json(
                provenance_out / "scores" / dataset / criterion / f"{question_id}.json",
                recorded_scores(
                    cache,
                    data["deduped"]["introspected"][question_id],
                    data["deduped"]["extracted"][question_id],
                    question_id,
                ),
                indent=None,
            )
            written += 1
    print(f"  recorded scores, {dataset}: {written} files")
    return written


# The build -------------------------------------------------------------------


def refuse_existing(*paths) -> str | None:
    """A message naming the first output path that exists, or None."""
    for path in paths:
        if path is not None and path.exists():
            return f"{path} exists; the build never writes into an existing directory"
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="The release. Must not exist.")
    parser.add_argument(
        "--provenance-out", type=Path, default=None,
        help="Internal provenance (recorded scores). Must not exist. Written apart from the release inputs.",
    )
    args = parser.parse_args(argv)
    out = args.out.resolve()
    provenance_out = args.provenance_out.resolve() if args.provenance_out else None
    problem = refuse_existing(out, provenance_out)
    if problem is None and provenance_out is not None and (
        provenance_out in out.parents or out in provenance_out.parents or out == provenance_out
    ):
        problem = "the release and the provenance must be separate directories"
    if problem:
        print(problem)
        return 1

    march_madness = prepare_march_madness()
    metaculus = prepare_metaculus()

    out.mkdir(parents=True)
    write_json(out / "method" / "matching_criteria.json", criteria_file(), indent=2)
    write_march_madness(out, march_madness)
    write_metaculus(out, metaculus)
    built = datetime.now(timezone.utc).isoformat(timespec="seconds")
    post_ids = metaculus["checks"]["metaculus_post_ids"]
    write_text(
        out / "README.md",
        README.format(
            built=built,
            spec=SPEC_VERSION,
            post_ids_known=post_ids["with_post_id"],
            post_ids_ambiguous=len(post_ids["ambiguous"]),
            n_metaculus=len(metaculus["questions"]),
        ),
    )
    write_text(out / "REDISTRIBUTION.md", REDISTRIBUTION)
    sources = {
        **{f"march_madness:{k}": str(v) for k, v in MM_SOURCES.items()},
        **{f"metaculus:{k}": str(v) for k, v in META_SOURCES.items()},
    }
    write_manifest(out, sources)
    for name in ("results", "scores"):
        if (out / name).exists():
            raise BuildCheckError(f"the release must hold inputs only, and it has {name}/")

    if provenance_out is not None:
        provenance_out.mkdir(parents=True)
        write_scores(provenance_out, "march_madness", march_madness, MM_SCORE_CACHE)
        write_scores(provenance_out, "metaculus", metaculus, META_SCORE_CACHE)
        write_text(provenance_out / "README.md", PROVENANCE_README.format(built=built, release=out))

    print(json.dumps({"march_madness": march_madness["checks"], "metaculus": metaculus["checks"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

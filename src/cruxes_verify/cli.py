"""The ``verify`` command.

    cruxes-verify check   --artifact A                  manifest hashes only
    cruxes-verify prepare --artifact A --work-dir W     the package's input files
    cruxes-verify score   --artifact A --work-dir W     GPU: cruxes-score for every run
    cruxes-verify report  --artifact A --work-dir W     CPU: cruxes-report and the analyses
    cruxes-verify compare --artifact A --work-dir W     CPU: the checks, a verdict file
    cruxes-verify all     --artifact A --work-dir W     all of the above in order

``--artifact`` is the data release. The runs are the ones the paper prints,
listed in the verifier's expected numbers. ``--run march_madness/resolution``
(repeatable) restricts score, report and compare to some runs, and
``--array-task-id i --num-array-tasks n`` makes score do every n-th question
of each run starting at i, which is how the GPU stage is split across jobs.
``--recorded-scores DIR`` (compare) adds the raw score check against the
authors' recorded scores, which ship in the data release under
``provenance/scores/``. Exit status 0 means every gated check passed.
"""

from __future__ import annotations

import argparse
import sys

from .artifact import Artifact
from .expected import Expected
from .pipeline import WorkDir, prepare, report, score, select_runs

STEPS = ("check", "prepare", "score", "report", "compare", "all")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cruxes-verify", description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("--artifact", required=True, help="The data release directory.")
    parser.add_argument("--work-dir", help="Where the rerun writes. Required except for check.")
    parser.add_argument("--run", action="append", default=None, help="dataset/criterion[@count]")
    parser.add_argument("--dry-run", action="store_true", help="score: plan only, no model")
    parser.add_argument("--array-task-id", type=int, default=None, help="score: this slice of the questions")
    parser.add_argument("--num-array-tasks", type=int, default=None, help="score: out of this many")
    parser.add_argument(
        "--recorded-scores",
        default=None,
        help="compare: the authors' recorded raw scores (RELEASE/provenance/scores in the data release), for the raw score check",
    )
    parser.add_argument("--expected", default=None, help="Another expected numbers directory (tests).")
    parser.add_argument(
        "--n-permutations", type=int, default=None,
        help="compare: draws of the null of the mean for the paper's test (default 10,000)",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    artifact = Artifact(args.artifact)
    print(f"release:  {artifact.root}")
    print(f"manifest: {artifact.check_manifest()}")
    if args.step == "check":
        return 0
    if not args.work_dir:
        print("--work-dir is required for this step")
        return 2
    expected = Expected(args.expected)
    work = WorkDir(args.work_dir)
    runs = select_runs(expected, artifact, args.run)
    print(f"expected: {expected.root}")
    print(f"runs:     {', '.join(r.name for r in runs)}")

    if args.step in ("prepare", "all"):
        for path in prepare(artifact, work):
            print(f"prepared {path}")
    if args.step in ("score", "all"):
        status = score(
            runs, work, dry_run=args.dry_run,
            array_task_id=args.array_task_id, num_array_tasks=args.num_array_tasks,
        )
        if status:
            return status
    if args.step in ("report", "all"):
        status = report(runs, work)
        if status:
            return status
    if args.step in ("compare", "all"):
        from .compare import compare_all, render_markdown, write_verdict

        verdict = compare_all(
            expected, runs, work, recorded_scores=args.recorded_scores, release=artifact,
            n_permutations=args.n_permutations,
        )
        json_path, md_path = write_verdict(verdict, work)
        print(render_markdown(verdict))
        print(f"wrote {json_path}\nwrote {md_path}")
        return 0 if verdict["passed"] else 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

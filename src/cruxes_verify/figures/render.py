"""Render the paper's figures from a verification rerun and from the paper's numbers.

    python -m cruxes_verify.figures.render --work-dir W

For every run the paper prints (the verifier's expected numbers,
``runs.json``), finds the newest ``set_inclusion_*.json`` the rerun wrote in
``W/reports/<run name>/`` (and ``granularity_sweep_*.json``,
``within_pool_split_*.json`` when present) and draws the stacked area chart, a
Venn diagram at 25 contrasts per side, and the baseline figures where the
input exists. Also draws the per question histogram at 25 contrasts per side
from the ``march_madness/resolution`` and ``metaculus/resolution`` runs when
both exist. Everything is written under ``W/figures/``; a run's figures are
named after the run, with ``/`` replaced by ``_``.

The same figures are drawn from the paper's numbers, which are the verifier's
own expected numbers (``cruxes_verify/expected/``, same format), into
``W/figures/paper/``, so a reader can put the two side by side.
``--expected DIR`` reads another expected numbers directory.

A figure whose input is missing is skipped with a printed line; every other
error propagates. No output PNG is ever overwritten: the work directory is
expected to be fresh for each rerun, so an existing target raises
``FileExistsError``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..expected import Expected, ExpectedError
from .granularity_sweep_figure import render_granularity_sweep
from .per_question_histogram import render_per_question_histogram
from .polished_set_inclusion import render_set_inclusion
from .venn_diagram import render_venn
from .within_pool_split_figure import render_within_pool_split

VENN_CONTRASTS_PER_SIDE = 25
HISTOGRAM_CONTRASTS_PER_SIDE = 25
ANALYSES = ('set_inclusion', 'granularity_sweep', 'within_pool_split')
HISTOGRAM_RUNS = ('march_madness/resolution', 'metaculus/resolution')


def _newest(report_dir: Path, analysis: str):
    if not report_dir.is_dir():
        return None
    found = sorted(report_dir.glob(f'{analysis}_*.json'))
    return found[-1] if found else None


def _prefix(out_dir: Path, name: str) -> str:
    """Reserve ``out_dir/name.png`` and return the prefix to pass a renderer."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'{name}.png'
    if target.exists():
        raise FileExistsError(f'{target} already exists; use a fresh work directory')
    return str(out_dir / name)


def _figure_name(run_name: str) -> str:
    return run_name.replace('/', '_')


def _render_set(source: str, name: str, out_dir: Path, inputs: dict) -> None:
    """``inputs`` maps each analysis to a report path, a loaded report, or None."""
    set_inclusion = inputs['set_inclusion']
    if set_inclusion is None:
        print(f'skip {source} {name}: no set_inclusion numbers')
    else:
        render_set_inclusion(set_inclusion, _prefix(out_dir, f'{name}_set_inclusion'), title=name)
        render_venn(set_inclusion, _prefix(out_dir, f'{name}_venn'),
                    contrasts_per_side=VENN_CONTRASTS_PER_SIDE)
    if inputs['granularity_sweep'] is not None:
        render_granularity_sweep(inputs['granularity_sweep'], _prefix(out_dir, f'{name}_granularity_sweep'))
    if inputs['within_pool_split'] is not None:
        render_within_pool_split(inputs['within_pool_split'], _prefix(out_dir, f'{name}_within_pool_split'))


def _paper_inputs(expected: Expected, run) -> dict:
    inputs = {}
    for analysis in ANALYSES:
        try:
            inputs[analysis] = expected.result(run, analysis)
        except ExpectedError:
            inputs[analysis] = None
    return inputs


def _rerun_inputs(work_root: Path, run) -> dict:
    report_dir = work_root / 'reports' / run.name
    return {analysis: _newest(report_dir, analysis) for analysis in ANALYSES}


def _render_histogram(source: str, mm, meta, out_dir: Path) -> None:
    if mm is None or meta is None:
        print(f'skip {source} per_question_histogram: needs both {" and ".join(HISTOGRAM_RUNS)}')
        return
    render_per_question_histogram(mm, meta, _prefix(out_dir, 'per_question_histogram'),
                                  contrasts_per_side=HISTOGRAM_CONTRASTS_PER_SIDE)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Render the paper figures from a verification rerun.')
    parser.add_argument('--work-dir', required=True, help='The rerun work directory.')
    parser.add_argument('--expected', default=None, help='Another expected numbers directory.')
    args = parser.parse_args(argv)

    expected = Expected(args.expected)
    work_root = Path(args.work_dir)
    figures_dir = work_root / 'figures'
    paper_dir = figures_dir / 'paper'

    rerun_sets, paper_sets = {}, {}
    for run in expected.runs():
        name = _figure_name(run.name)
        rerun = _rerun_inputs(work_root, run)
        paper = _paper_inputs(expected, run)
        _render_set('rerun', name, figures_dir, rerun)
        _render_set('paper', name, paper_dir, paper)
        rerun_sets[run.name], paper_sets[run.name] = rerun['set_inclusion'], paper['set_inclusion']

    _render_histogram('rerun', *(rerun_sets.get(r) for r in HISTOGRAM_RUNS), figures_dir)
    _render_histogram('paper', *(paper_sets.get(r) for r in HISTOGRAM_RUNS), paper_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

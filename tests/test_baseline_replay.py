"""Developer replay of the two baselines on recorded matrices, exactly.

The fixture is the package's developer replay fixture (three recorded
objects59 resolution caches and the numbers gathered from them), copied here
with the baseline procedures. Replayed with the constant permutation seed the
recorded runs used. A check of the port, not verification of the paper.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cruxes import ScoreMatrices
from cruxes_verify.procedures.baselines import (
    granularity_sweep_for_question,
    within_pool_curves_for_question,
)

FIXTURE = Path(__file__).parent / "fixtures" / "recorded_replay_objects59.json"
QUESTIONS = ["akron-vs-texas-tech", "arizona-vs-purdue", "cal-baptist-vs-kansas"]


def constant_seed(question_id, count, analysis):
    return 42


@pytest.fixture(scope="module")
def recorded():
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("question", QUESTIONS)
def test_granularity_sweep_replays_exactly(recorded, question):
    matrices = ScoreMatrices.from_mapping(recorded["questions"][question])
    sweep = granularity_sweep_for_question(matrices, question, permutation_seed=constant_seed)
    assert json.loads(json.dumps(sweep)) == recorded["questions"][question]["granularity_sweep"]


@pytest.mark.parametrize("question", QUESTIONS)
def test_within_pool_split_replays_exactly(recorded, question):
    matrices = ScoreMatrices.from_mapping(recorded["questions"][question])
    within = within_pool_curves_for_question(matrices, question, permutation_seed=constant_seed)
    assert json.loads(json.dumps(within)) == recorded["questions"][question]["within_pool"]

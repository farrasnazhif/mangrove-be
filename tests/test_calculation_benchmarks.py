"""User-authorized numerical baselines, independent of production calculations."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.calc.engine import LayerInput, TreeInput, calculate_plot
from app.calc.methods import Method

FIXTURE = json.loads((Path(__file__).parent / "fixtures/calculation_benchmarks.json").read_text())


def assert_values(actual, expected):
    for field, value in expected.items():
        if value is None:
            assert actual[field] is None
        else:
            assert actual[field] == pytest.approx(
                float(value), rel=FIXTURE["relative_tolerance"], abs=FIXTURE["absolute_tolerance"]
            ), field


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["id"])
def test_all_intermediates_and_totals_against_frozen_benchmark(case):
    result = calculate_plot(
        [TreeInput(t["dbh_cm"], t["density_g_cm3"], t["species_id"]) for t in case["trees"]],
        [LayerInput(**layer) for layer in case["layers"]],
        case["area_m2"],
        Method("technical-benchmark-v1", (FIXTURE["reference"],)),
        expected_bottom_cm=case["expected_bottom_cm"],
    )
    for actual, expected in zip(result.trees, case["expected"]["trees"], strict=True):
        assert_values(asdict(actual), expected)
    for actual, expected in zip(result.profile.layers, case["expected"]["layers"], strict=True):
        assert_values(asdict(actual), expected)
    assert_values(asdict(result), case["expected"]["stock"])
    assert bool(result.flags) == (not case["layers"])


def test_frozen_workbook_agb_bgb_agree_with_independent_baseline():
    case = FIXTURE["cases"][1]
    for tree, expected in zip(case["trees"], case["expected"]["trees"], strict=True):
        assert_values(
            {"agb_kg": tree["cached_agb_kg"], "bgb_kg": tree["cached_bgb_kg"]},
            {key: expected[key] for key in ("agb_kg", "bgb_kg")},
        )

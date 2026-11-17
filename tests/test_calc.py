"""PRD equation checks, NOT the still-unavailable reviewer-signed golden fixture."""

import ast
import asyncio
import json
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.calc.engine import (
    LayerInput,
    TreeInput,
    calculate_layer,
    calculate_plot,
    calculate_profile,
    calculate_tree,
    kg_c_to_mg_c_ha,
    summarize_plots,
)
from app.calc.methods import Coefficients, Method, round_output
from app.models import MethodVersion
from app.services.method_registry import load_method, method_from_record, register_method

METHOD = Method("prd-section-6-v1", ("PRD.md section 6; local equation checks only",))
TREES = (TreeInput(10, 0.6, "species-a"), TreeInput(20, 0.7, "species-b"))
# BD 0.5 and 1; %C 10 and 5; thickness 10 and 20 -> SOC 50 + 100.
LAYERS = (LayerInput(0, 10, 25, 50, 17.24), LayerInput(10, 30, 50, 50, 8.62))


def plot(area=100, trees=TREES, layers=LAYERS, method=METHOD):
    return calculate_plot(trees, layers, area, method, expected_bottom_cm=30)


@pytest.mark.parametrize(
    "tree,expected",
    [
        (
            TREES[0],
            (43.43351443708668549, 20.86464743413737052, 20.41375178543074218, 8.13721249931357450),
        ),
        (
            TREES[1],
            (
                278.80820527928212756,
                111.65619006379097956,
                131.03985648126259995,
                43.54591412487848203,
            ),
        ),
    ],
)
def test_tree_intermediates_against_independent_decimal_evaluation(tree, expected):
    # Constants evaluated separately with Decimal at 55 digits; not reviewer approval.
    result = calculate_tree(tree, METHOD)
    assert (result.agb_kg, result.bgb_kg, result.agc_kg, result.bgc_kg) == pytest.approx(
        expected, rel=1e-12
    )
    assert result.flags == ()


def test_plot_units_and_soc_counted_once():
    result = plot()
    assert result.agc_mg_c_ha == pytest.approx(15.145360826669334)
    assert result.bgc_mg_c_ha == pytest.approx(5.168312662419206)
    assert result.soc_mg_c_ha == pytest.approx(150)
    assert result.total_mg_c_ha == pytest.approx(170.31367348908854)
    assert result.co2e_mg_ha == pytest.approx(624.4834694599913)
    assert result.profile.layers[0].bulk_density_g_cm3 == 0.5
    assert result.profile.layers[0].carbon_pct == pytest.approx(10)
    assert result.profile.layers[0].soc_mg_c_ha == pytest.approx(50)
    assert plot(200).agc_mg_c_ha == pytest.approx(result.agc_mg_c_ha / 2)
    assert plot(200).soc_mg_c_ha == result.soc_mg_c_ha  # Already normalized per hectare.
    assert kg_c_to_mg_c_ha(1000, 10000) == 1


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), float("-inf"), True])
def test_invalid_positive_measurements(value):
    with pytest.raises(ValueError):
        calculate_tree(replace(TREES[0], dbh_cm=value), METHOD)
    with pytest.raises(ValueError):
        plot(area=value)
    with pytest.raises(ValueError):
        calculate_tree(replace(TREES[0], density_g_cm3=value), METHOD)
    for field in ("dry_mass_g", "volume_cm3", "bottom_cm"):
        with pytest.raises(ValueError):
            calculate_layer(replace(LAYERS[0], **{field: value}), METHOD)


@pytest.mark.parametrize(
    "field,value",
    [
        ("top_cm", -1),
        ("top_cm", 10),
        ("loi_pct", -1),
        ("loi_pct", 100.1),
        ("loi_pct", float("nan")),
        ("top_cm", float("inf")),
    ],
)
def test_invalid_layer_bounds(field, value):
    with pytest.raises(ValueError):
        calculate_layer(replace(LAYERS[0], **{field: value}), METHOD)


def test_density_bound_and_numeric_overflow():
    with pytest.raises(ValueError):
        calculate_tree(TreeInput(10, 2.01, "species"), METHOD)
    assert calculate_tree(TreeInput(10, 2, "species"), METHOD).agb_kg is not None
    with pytest.raises(ValueError):
        calculate_tree(TreeInput(1e308, 1, "species"), METHOD)


@pytest.mark.parametrize(
    "tree,flag",
    [
        (TreeInput(10, None, "species"), "missing-density"),
        (TreeInput(10, 0.6, None), "missing-species"),
    ],
)
def test_missing_tree_input_never_becomes_partial_official_total(tree, flag):
    result = plot(trees=(TREES[0], tree))
    assert flag in result.flags
    assert result.agc_mg_c_ha is None
    assert result.bgc_mg_c_ha is None
    assert result.total_mg_c_ha is None
    assert result.co2e_mg_ha is None
    assert result.trees[0].agc_kg is not None  # Keep valid per-tree intermediates.


@pytest.mark.parametrize("field", ["dry_mass_g", "volume_cm3", "loi_pct"])
def test_missing_layer_measurement(field):
    result = plot(layers=(replace(LAYERS[0], **{field: None}), LAYERS[1]))
    assert "missing-layer-measurements" in result.flags
    assert result.soc_mg_c_ha is None
    assert result.total_mg_c_ha is None
    assert result.agc_mg_c_ha is not None


def test_zero_loi_is_a_measured_zero_not_missing():
    result = calculate_profile((replace(LAYERS[0], loi_pct=0),), METHOD, expected_bottom_cm=10)
    assert result.soc_mg_c_ha == 0
    assert not result.flags


@pytest.mark.parametrize(
    "layers",
    [
        (LayerInput(5, 10, 25, 50, 17.24), LAYERS[1]),  # missing surface
        (LAYERS[0], LayerInput(11, 30, 50, 50, 8.62)),  # internal gap
        (LAYERS[0],),  # missing bottom
        (),
    ],
)
def test_profile_gaps_make_total_unavailable(layers):
    result = calculate_profile(layers, METHOD, expected_bottom_cm=30)
    assert "missing-sediment-layer" in result.flags
    assert result.soc_mg_c_ha is None


def test_profile_order_edges_unknown_depth_and_overlap():
    assert calculate_profile(LAYERS, METHOD, expected_bottom_cm=30) == calculate_profile(
        LAYERS[::-1], METHOD, expected_bottom_cm=30
    )
    assert "unknown-profile-depth" in calculate_profile(LAYERS, METHOD).flags
    for layers in ((LAYERS[0], LAYERS[0]), (LAYERS[0], replace(LAYERS[1], top_cm=9))):
        with pytest.raises(ValueError, match="overlap"):
            calculate_profile(layers, METHOD, expected_bottom_cm=30)
    with pytest.raises(ValueError, match="exceeds"):
        calculate_profile(LAYERS, METHOD, expected_bottom_cm=20)


def test_missing_sediment_supports_explicit_biomass_only_output():
    result = plot(layers=())
    assert result.agc_mg_c_ha is not None
    assert result.soc_mg_c_ha is None
    assert result.total_mg_c_ha is None
    assert "missing-sediment" in result.flags
    assert "missing-tree-inventory" in plot(trees=()).flags


def test_area_weighted_summary_excludes_incomplete_and_labels_denominator():
    first, second, incomplete = plot(100), plot(300), plot(layers=())
    summary = summarize_plots((first, second, incomplete))
    assert summary.aggregation_rule == "area-weighted"
    assert summary.eligible_plots == 2
    assert summary.excluded_plots == 1
    assert summary.eligible_area_m2 == 400
    assert summary.total_mg_c_ha == pytest.approx(160.15683674454427)
    assert summary.co2e_mg_ha == pytest.approx(summary.total_mg_c_ha * 44 / 12)
    assert summarize_plots((incomplete,)).total_mg_c_ha is None
    assert summarize_plots(()).total_mg_c_ha is None
    with pytest.raises(ValueError, match="single method"):
        summarize_plots((first, plot(method=replace(METHOD, version="other"))))


def test_snapshot_replay_survives_new_coefficients_and_json_round_trip():
    original_snapshot = json.loads(json.dumps(METHOD.to_dict()))
    input_snapshot = json.loads(
        json.dumps(
            {
                "trees": [asdict(tree) for tree in TREES],
                "layers": [asdict(layer) for layer in LAYERS],
                "area_m2": 100,
                "expected_bottom_cm": 30,
            }
        )
    )
    saved_result = json.loads(json.dumps(asdict(plot())))
    revised = replace(
        METHOD, version="v2", coefficients=replace(METHOD.coefficients, agb_coefficient=0.3)
    )
    assert plot(method=revised).total_mg_c_ha != plot().total_mg_c_ha
    replay = calculate_plot(
        tuple(TreeInput(**tree) for tree in input_snapshot["trees"]),
        tuple(LayerInput(**layer) for layer in input_snapshot["layers"]),
        input_snapshot["area_m2"],
        Method.from_dict(original_snapshot),
        expected_bottom_cm=input_snapshot["expected_bottom_cm"],
    )
    assert json.loads(json.dumps(asdict(replay))) == saved_result
    with pytest.raises(FrozenInstanceError):
        METHOD.coefficients.agb_coefficient = 1
    broken = METHOD.to_dict()
    del broken["coefficients_json"]["agb"]
    with pytest.raises(KeyError):
        Method.from_dict(broken)


def test_rounding_only_at_output_and_no_implicit_rule():
    rounded = replace(METHOD, output_decimal_places=2)
    assert plot(method=rounded) == plot()  # Rounding metadata does not affect arithmetic.
    assert round_output(1.225, rounded) == 1.22
    assert round_output(1.235, rounded) == 1.24
    assert round_output(None, rounded) is None
    assert round_output(1.23456789, METHOD) == 1.23456789


@pytest.mark.parametrize(
    "changes",
    [
        {"version": ""},
        {"references": ()},
        {"approval_status": "fake"},
        {"approval_status": "approved"},
        {"output_decimal_places": -1},
        {"output_decimal_places": True},
    ],
)
def test_method_metadata_validation(changes):
    with pytest.raises(ValueError):
        replace(METHOD, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"agc_fraction": 1.1},
        {"bgc_fraction": 0},
        {"loi_to_c_divisor": 0},
        {"agb_coefficient": float("nan")},
    ],
)
def test_coefficient_validation(changes):
    with pytest.raises(ValueError):
        Coefficients(**changes)


def test_registry_round_trip_and_insert_only():
    async def check():
        from unittest.mock import MagicMock

        session = AsyncMock()
        session.add = MagicMock()
        session.scalar.return_value = None
        record = await register_method(session, METHOD, data_label="synthetic")
        assert method_from_record(record) == METHOD
        assert record.approved_at is None
        session.flush.assert_awaited_once()
        session.commit.assert_not_awaited()
        session.get.return_value = record
        assert await load_method(session, "stored-id") == METHOD
        session.get.return_value = None
        with pytest.raises(ValueError, match="Unknown"):
            await load_method(session, "missing")
        session.scalar.return_value = "existing-id"
        with pytest.raises(ValueError, match="new version"):
            await register_method(session, METHOD, data_label="synthetic")
        session.add.assert_called_once()

    asyncio.run(check())


def test_registry_preserves_explicit_approval_metadata():
    async def check():
        from unittest.mock import MagicMock

        session = AsyncMock()
        session.add = MagicMock()
        session.scalar.return_value = None
        method = replace(
            METHOD,
            version="reviewed-v1",
            approval_status="approved",
            effective_date=date(2026, 1, 1),
            output_decimal_places=3,
        )
        record = await register_method(session, method, data_label="field")
        assert record.approved_at is not None
        assert record.approved_at.tzinfo is not None
        assert method_from_record(record) == method
        with pytest.raises(ValueError, match="data label"):
            await register_method(session, method, data_label="invalid")

    asyncio.run(check())


def test_existing_seed_method_shape_is_supported():
    record = MethodVersion(
        **{key: value for key, value in METHOD.to_dict().items() if key not in {"effective_date"}},
        effective_date=None,
    )
    record.coefficients_json["source"] = "legacy synthetic seed metadata"
    assert method_from_record(record) == METHOD
    approved = replace(METHOD, approval_status="approved", effective_date=date(2026, 1, 1))
    assert Method.from_dict(approved.to_dict()) == approved


def test_calc_has_no_database_or_web_framework_imports():
    for path in Path("app/calc").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            assert all(
                not module.startswith(("fastapi", "sqlalchemy", "app.db", "app.models"))
                for module in modules
            ), path

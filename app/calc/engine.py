"""PRD section 6 equations; all intermediates retain Python float precision.

Invalid supplied measurements raise ValueError. Missing measurements produce flags
and unavailable totals. Publication, scope, review and persistence belong to services.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum

from app.calc.methods import Method, number


@dataclass(frozen=True)
class TreeInput:
    dbh_cm: float
    density_g_cm3: float | None
    species_id: str | None


@dataclass(frozen=True)
class TreeResult:
    agb_kg: float | None
    bgb_kg: float | None
    agc_kg: float | None
    bgc_kg: float | None
    flags: tuple[str, ...] = ()


def calculate_tree(tree: TreeInput, method: Method) -> TreeResult:
    number(tree.dbh_cm, "dbh_cm")
    flags = []
    if not tree.species_id:
        flags.append("missing-species")
    density = tree.density_g_cm3
    if density is None:
        flags.append("missing-density")
    else:
        number(density, "density_g_cm3")
        if density > 2:
            raise ValueError("density_g_cm3 must be <= 2 (current schema bound)")
    if flags:
        return TreeResult(None, None, None, None, tuple(flags))
    assert density is not None
    c = method.coefficients
    try:
        agb = c.agb_coefficient * density * tree.dbh_cm**c.agb_dbh_exponent
        bgb = c.bgb_coefficient * density**c.bgb_density_exponent * tree.dbh_cm**c.bgb_dbh_exponent
        agc, bgc = agb * c.agc_fraction, bgb * c.bgc_fraction
        for name, value in (("agb", agb), ("bgb", bgb), ("agc", agc), ("bgc", bgc)):
            number(value, name)
    except OverflowError as error:
        raise ValueError("Tree calculation exceeds numeric range") from error
    return TreeResult(agb, bgb, agc, bgc)


@dataclass(frozen=True)
class LayerInput:
    top_cm: float
    bottom_cm: float
    dry_mass_g: float | None
    volume_cm3: float | None
    loi_pct: float | None


@dataclass(frozen=True)
class LayerResult:
    bulk_density_g_cm3: float | None
    carbon_pct: float | None
    soc_mg_c_ha: float | None
    flags: tuple[str, ...] = ()


def calculate_layer(layer: LayerInput, method: Method) -> LayerResult:
    number(layer.top_cm, "top_cm", inclusive=True)
    number(layer.bottom_cm, "bottom_cm", minimum=layer.top_cm)
    for name, value in (("dry_mass_g", layer.dry_mass_g), ("volume_cm3", layer.volume_cm3)):
        if value is not None:
            number(value, name)
    if layer.loi_pct is not None:
        number(layer.loi_pct, "loi_pct", inclusive=True)
        if layer.loi_pct > 100:
            raise ValueError("loi_pct must be <= 100")
    bd = None
    if layer.dry_mass_g is not None and layer.volume_cm3 is not None:
        bd = layer.dry_mass_g / layer.volume_cm3
        number(bd, "bulk_density_g_cm3")
    carbon = None if layer.loi_pct is None else layer.loi_pct / method.coefficients.loi_to_c_divisor
    if carbon is not None and carbon > 100:
        raise ValueError("Method yields carbon percentage > 100")
    soc = None
    if bd is not None and carbon is not None:
        soc = bd * (layer.bottom_cm - layer.top_cm) * (carbon / 100) * 100
        number(soc, "soc_mg_c_ha", inclusive=True)
    return LayerResult(bd, carbon, soc, ("missing-layer-measurements",) if soc is None else ())


@dataclass(frozen=True)
class ProfileResult:
    layers: tuple[LayerResult, ...]
    soc_mg_c_ha: float | None
    flags: tuple[str, ...]


def calculate_profile(
    layers: Sequence[LayerInput], method: Method, *, expected_bottom_cm: float | None = None
) -> ProfileResult:
    """One core only. Expected depth is explicit; no research depth is invented.

    Without an expected bottom a continuous measured profile still has unknown
    completeness. Multi-core plot aggregation needs a separately approved policy.
    """
    if expected_bottom_cm is not None:
        number(expected_bottom_cm, "expected_bottom_cm")
    ordered = sorted(layers, key=lambda layer: layer.top_cm)
    results = tuple(calculate_layer(layer, method) for layer in ordered)
    flags = {flag for result in results for flag in result.flags}
    if expected_bottom_cm is None:
        flags.add("unknown-profile-depth")
    if not ordered:
        flags.add("missing-sediment")
    previous_bottom = 0.0
    for layer in ordered:
        if layer.top_cm < previous_bottom:
            raise ValueError("Sediment intervals overlap within a core")
        if layer.top_cm > previous_bottom:
            flags.add("missing-sediment-layer")
        previous_bottom = layer.bottom_cm
    if expected_bottom_cm is not None:
        if previous_bottom > expected_bottom_cm:
            raise ValueError("Profile exceeds expected bottom depth")
        if previous_bottom < expected_bottom_cm:
            flags.add("missing-sediment-layer")
    total = None if flags else fsum(r.soc_mg_c_ha for r in results if r.soc_mg_c_ha is not None)
    if total is not None:
        number(total, "profile_soc", inclusive=True)
    return ProfileResult(results, total, tuple(sorted(flags)))


def kg_c_to_mg_c_ha(carbon_kg: float, area_m2: float) -> float:
    number(carbon_kg, "carbon_kg", inclusive=True)
    number(area_m2, "area_m2")
    return number(carbon_kg * 10 / area_m2, "stock_mg_c_ha", inclusive=True)


@dataclass(frozen=True)
class PlotResult:
    method_version: str
    area_m2: float
    trees: tuple[TreeResult, ...]
    profile: ProfileResult
    agc_mg_c_ha: float | None
    bgc_mg_c_ha: float | None
    soc_mg_c_ha: float | None
    total_mg_c_ha: float | None
    co2e_mg_ha: float | None
    flags: tuple[str, ...]


def calculate_plot(
    trees: Sequence[TreeInput],
    layers: Sequence[LayerInput],
    area_m2: float,
    method: Method,
    *,
    expected_bottom_cm: float | None = None,
) -> PlotResult:
    number(area_m2, "area_m2")
    tree_results = tuple(calculate_tree(tree, method) for tree in trees)
    profile = calculate_profile(layers, method, expected_bottom_cm=expected_bottom_cm)
    tree_flags = {flag for tree in tree_results for flag in tree.flags}
    if not trees:
        tree_flags.add("missing-tree-inventory")
    agc = bgc = None
    if not tree_flags:
        agc = kg_c_to_mg_c_ha(fsum(t.agc_kg for t in tree_results if t.agc_kg is not None), area_m2)
        bgc = kg_c_to_mg_c_ha(fsum(t.bgc_kg for t in tree_results if t.bgc_kg is not None), area_m2)
    flags = tuple(sorted(tree_flags | set(profile.flags)))
    total = None
    if agc is not None and bgc is not None and profile.soc_mg_c_ha is not None:
        total = number(fsum((agc, bgc, profile.soc_mg_c_ha)), "total", inclusive=True)
    co2e = None if total is None else number(total * (44 / 12), "co2e", inclusive=True)
    return PlotResult(
        method.version,
        area_m2,
        tree_results,
        profile,
        agc,
        bgc,
        profile.soc_mg_c_ha,
        total,
        co2e,
        flags,
    )


@dataclass(frozen=True)
class SummaryResult:
    aggregation_rule: str
    eligible_plots: int
    excluded_plots: int
    eligible_area_m2: float
    total_mg_c_ha: float | None
    co2e_mg_ha: float | None


def summarize_plots(plots: Sequence[PlotResult]) -> SummaryResult:
    """D5 area-weighted complete ecosystem results. Caller selects approved inventory."""
    eligible = [p for p in plots if not p.flags and p.total_mg_c_ha is not None]
    if len({p.method_version for p in eligible}) > 1:
        raise ValueError("Summaries require a single method version")
    area = fsum(p.area_m2 for p in eligible)
    number(area, "eligible_area", inclusive=True)
    total = None
    if eligible:
        # Normalize weights first to avoid unnecessary stock * area overflow.
        total = number(
            fsum(
                p.total_mg_c_ha * (p.area_m2 / area)
                for p in eligible
                if p.total_mg_c_ha is not None
            ),
            "summary_total",
            inclusive=True,
        )
    co2e = None if total is None else number(total * (44 / 12), "summary_co2e", inclusive=True)
    return SummaryResult(
        "area-weighted", len(eligible), len(plots) - len(eligible), area, total, co2e
    )

# Calculation module (Task 04)

`app/calc/` uses only the Python standard library. It does not access FastAPI or
the database. Inputs, method metadata and results are frozen dataclasses. Functions
retain Python float precision; no rounding occurs in intermediate calculations.

```python
from app.calc.engine import LayerInput, TreeInput, calculate_plot, summarize_plots
from app.calc.methods import Method

method = Method(
    version="synthetic-equation-check-v1",
    references=("PRD.md section 6; synthetic demonstration only",),
)
result = calculate_plot(
    trees=(TreeInput(dbh_cm=10, density_g_cm3=0.6, species_id="synthetic-species"),),
    layers=(LayerInput(0, 10, dry_mass_g=25, volume_cm3=50, loi_pct=17.24),),
    area_m2=100,
    method=method,
    expected_bottom_cm=10,
)
summary = summarize_plots((result,))  # aggregation_rule == "area-weighted"
```

These are synthetic examples, not a reviewer benchmark or official inventory.
The default coefficients implement the method approved in BACKLOG decision D1;
creating a method does not implicitly give its registry record scientific approval.

## Equations and units

- Tree AGB = 0.251 × density × DBH^2.46; BGB = 0.199 × density^0.899 × DBH^2.22.
  DBH is cm, density is g/cm³, AGB/BGB are kg dry biomass per tree.
- AGC = AGB × 0.47; BGC = BGB × 0.39, in kg C per tree.
- Plot carbon = sum(kg C) × 10,000 / (1,000 × area_m²), in Mg C/ha.
- Layer BD = dry mass (g) / volume (cm³), in g/cm³; carbon percent = LOI / 1.724.
  SOC = BD × thickness (cm) × (carbon percent / 100) × 100, in Mg C/ha.
- Ecosystem stock = AGC + BGC + one complete profile's SOC, in Mg C/ha.
  CO₂e = ecosystem stock × 44/12, in Mg CO₂e/ha, not annual sequestration.

The immutable `Coefficients` object holds the allometry coefficients, fractions and
LOI divisor. Replay loads every coefficient from the saved method, with no fallback
to current defaults. New equations with a different functional form require engine
support; this engine supports the PRD section 6 formula family only.

## Missing data and unresolved research decisions

Invalid supplied values raise `ValueError`: non-finite numbers, non-positive DBH,
area/mass/volume, negative depth, reversed/overlapping intervals, density outside
(0, 2], or LOI outside [0, 100]. Density and LOI bounds follow the current database
schema; these bounds do not constitute a new scientific range approval.

Missing species or density flags the tree. All plot AGC/BGC totals then remain
`None`, while valid per-tree intermediates remain inspectable. Missing sediment
keeps available biomass stocks, flags the result, and leaves SOC, ecosystem total
and ecosystem CO₂e unavailable. No missing value is replaced by zero. Measured zero
LOI legitimately produces zero SOC. An empty tree list is treated as an unrecorded
inventory, rather than assuming a verified zero-tree survey.

Profiles start at 0 cm. Supply `expected_bottom_cm` from the sampling protocol to
detect absent bottom layers; no default depth is invented. Missing surface, internal
or bottom layers, or missing measurements, make the profile total unavailable.
Without a target depth, `unknown-profile-depth` prevents a completeness claim.
Intervals are sorted by top depth; adjacent intervals are accepted.

One profile represents **one core**. Do not combine layers from different cores or
sum their per-hectare stocks. Multi-core aggregation, required cores per plot and
the target sampling depth remain research inputs. No multi-core rule is assumed.

`summarize_plots` excludes incomplete results, exposes eligible/excluded counts and
eligible area, and uses sum(stock × area weight) with the label `area-weighted` (D5).
An empty eligible set returns `None`, not zero. Mixed method versions are rejected.
The caller must first select reviewed/published, in-scope records; a pure numerical
result does not assert publication authorization or eligibility.

## Registry, replay and output rounding

`app/services/method_registry.py` adapts existing `method_versions` rows:

- `load_method(session, id)` loads an explicit stored version, never the latest one.
- `register_method(session, method, data_label=...)` inserts and flushes a new row;
  the caller handles authorization and transaction commit. An existing version is
  rejected, and existing database constraints/triggers prohibit overwriting rows.
- `method.to_dict()` and `Method.from_dict()` preserve coefficients, references,
  approval status, effective date and rounding rule as JSON-compatible data. The
  existing synthetic seed method is supported without changing its approval.

Preserve the exact input snapshot along with the original method version and full
precision results. Replay through `calculate_plot` with those same inputs and method.
Calculation-run storage, hashes, timestamps and publication are Task 06 work.

An empty rounding rule means rounding has not been approved. `round_output` leaves
values unchanged in that case. A method can explicitly specify decimal places and
decimal half-even rounding for display/export only. Do not persist rounded values
as scientific intermediates. No project-wide rounding precision is assumed.

## Verification and remaining acceptance

Run `uv run pytest tests/test_calc.py -q`. Tests cover independent high-precision
Decimal evaluations of tree intermediates, a synthetic 10×10 m plot with two trees
and two layers, dimensional conversion, actual plot area, missing data, depth gaps,
overlaps, input bounds, area weighting, method registry behavior and JSON replay.
The local equation-check tolerance is 1e-12 relative for tree intermediates; it is
not an approved reviewer tolerance.

**The reviewer-signed golden fixture and approved tolerance are still unavailable.**
Task 04 cannot be marked fully done until that fixture is supplied and every
intermediate is checked against it. Local equation checks are not a substitute.

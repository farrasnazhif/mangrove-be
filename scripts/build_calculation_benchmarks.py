"""Build a technical golden fixture independently of app.calc using Decimal.

Source workbook is read-only and never needed by CI. Plot areas and sediment values
are explicitly synthetic: the workbook supplies tree examples, not official totals.
"""

import hashlib
import json
import warnings
from decimal import Decimal, localcontext
from pathlib import Path

from openpyxl import load_workbook

SOURCE = Path("realdata/Data/Tagging_Tanaman_AGB_BGB_2026.xlsx")
TARGET = Path("tests/fixtures/calculation_benchmarks.json")


def evaluate(case):
    with localcontext() as ctx:
        ctx.prec = 55
        d = lambda value: Decimal(str(value))
        trees = []
        for tree in case["trees"]:
            dbh, rho = d(tree["dbh_cm"]), d(tree["density_g_cm3"])
            agb = d("0.251") * rho * dbh ** d("2.46")
            bgb = d("0.199") * rho ** d("0.899") * dbh ** d("2.22")
            trees.append(
                {"agb_kg": agb, "bgb_kg": bgb, "agc_kg": agb * d("0.47"), "bgc_kg": bgb * d("0.39")}
            )
        layers = []
        for layer in case["layers"]:
            bd = d(layer["dry_mass_g"]) / d(layer["volume_cm3"])
            carbon = d(layer["loi_pct"]) / d("1.724")
            soc = bd * (d(layer["bottom_cm"]) - d(layer["top_cm"])) * carbon
            layers.append({"bulk_density_g_cm3": bd, "carbon_pct": carbon, "soc_mg_c_ha": soc})
        factor = d(10) / d(case["area_m2"])
        agc = sum(t["agc_kg"] for t in trees) * factor
        bgc = sum(t["bgc_kg"] for t in trees) * factor
        soc = sum(l["soc_mg_c_ha"] for l in layers) if layers else None
        total = agc + bgc + soc if soc is not None else None
        stock = {
            "agc_mg_c_ha": agc,
            "bgc_mg_c_ha": bgc,
            "soc_mg_c_ha": soc,
            "total_mg_c_ha": total,
            "co2e_mg_ha": total * d(44) / d(12) if total is not None else None,
        }
        return {
            "trees": [{k: str(v) for k, v in t.items()} for t in trees],
            "layers": [{k: str(v) for k, v in l.items()} for l in layers],
            "stock": {k: str(v) if v is not None else None for k, v in stock.items()},
        }


def main():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        book = load_workbook(SOURCE, read_only=True, data_only=True)
    samples = []
    for row_number, row in enumerate(book["Data Pohon"].values, start=1):
        if (
            len(row) >= 19
            and isinstance(row[9], (float, int))
            and isinstance(row[11], (float, int))
        ):
            if row[8] != "DBH":
                continue  # Do not assume circumference conversion policy for this benchmark.
            samples.append(
                {
                    "dbh_cm": row[9],
                    "density_g_cm3": row[11],
                    "species_id": "workbook-sample",
                    "source_row": row_number,
                    "cached_agb_kg": row[12],
                    "cached_bgb_kg": row[13],
                }
            )
            if len(samples) == 5:
                break
    book.close()
    if len(samples) != 5:
        raise ValueError("Expected five numeric DBH/density workbook samples")
    cases = [
        {
            "id": "synthetic-complete-100m2",
            "area_m2": 100,
            "expected_bottom_cm": 30,
            "trees": [
                {"dbh_cm": 10, "density_g_cm3": 0.6, "species_id": "synthetic-a"},
                {"dbh_cm": 20, "density_g_cm3": 0.7, "species_id": "synthetic-b"},
            ],
            "layers": [
                {
                    "top_cm": 0,
                    "bottom_cm": 10,
                    "dry_mass_g": 25,
                    "volume_cm3": 50,
                    "loi_pct": 17.24,
                },
                {
                    "top_cm": 10,
                    "bottom_cm": 30,
                    "dry_mass_g": 50,
                    "volume_cm3": 50,
                    "loi_pct": 8.62,
                },
            ],
        },
        {
            "id": "workbook-trees-synthetic-100m2",
            "area_m2": 100,
            "expected_bottom_cm": None,
            "trees": samples,
            "layers": [],
        },
        {
            "id": "workbook-trees-synthetic-250m2-and-sediment",
            "area_m2": 250,
            "expected_bottom_cm": 10,
            "trees": samples,
            "layers": [
                {"top_cm": 0, "bottom_cm": 10, "dry_mass_g": 25, "volume_cm3": 50, "loi_pct": 17.24}
            ],
        },
    ]
    for case in cases:
        case["expected"] = evaluate(case)
    fixture = {
        "acceptance": "user-authorized technical benchmark; not independent reviewer sign-off",
        "reference": "https://doi.org/10.1017/S0266467405002476",
        "method": "PRD section 6: AGB/BGB 0.251/0.199; carbon fractions 0.47/0.39; LOI divisor 1.724; CO2e 44/12",
        "precision_digits": 55,
        "relative_tolerance": 1e-12,
        "absolute_tolerance": 1e-10,
        "source_path": SOURCE.as_posix(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "limitations": [
            "Plot areas and sediment inputs are synthetic; not actual workbook plot stocks.",
            "Workbook density values are inputs, not independent species-density approval.",
            "Workbook CO2e uses rounded 3.67; expected results use PRD exact 44/12.",
            "No real records, methods or study boundaries are approved or imported.",
        ],
        "cases": cases,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET} ({len(cases)} cases)")


if __name__ == "__main__":
    main()

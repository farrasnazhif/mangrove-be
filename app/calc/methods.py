"""Immutable method snapshots. No approval or coefficient changes happen implicitly."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from math import isfinite
from typing import Any


def number(value: float, name: str, *, minimum: float = 0, inclusive: bool = False) -> float:
    if isinstance(value, bool) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < minimum or (not inclusive and value == minimum):
        raise ValueError(f"{name} must be {'at least' if inclusive else 'greater than'} {minimum}")
    return value


@dataclass(frozen=True)
class Coefficients:
    agb_coefficient: float = 0.251
    agb_dbh_exponent: float = 2.46
    bgb_coefficient: float = 0.199
    bgb_density_exponent: float = 0.899
    bgb_dbh_exponent: float = 2.22
    agc_fraction: float = 0.47
    bgc_fraction: float = 0.39
    loi_to_c_divisor: float = 1.724

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            number(value, name)
        if self.agc_fraction > 1 or self.bgc_fraction > 1:
            raise ValueError("Carbon fractions must be in (0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agb": {"coefficient": self.agb_coefficient, "dbh_exponent": self.agb_dbh_exponent},
            "bgb": {
                "coefficient": self.bgb_coefficient,
                "density_exponent": self.bgb_density_exponent,
                "dbh_exponent": self.bgb_dbh_exponent,
            },
            "agc_fraction": self.agc_fraction,
            "bgc_fraction": self.bgc_fraction,
            "loi_to_c_divisor": self.loi_to_c_divisor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Coefficients":
        # Required keys deliberately have no defaults when replaying a stored method.
        return cls(
            agb_coefficient=data["agb"]["coefficient"],
            agb_dbh_exponent=data["agb"]["dbh_exponent"],
            bgb_coefficient=data["bgb"]["coefficient"],
            bgb_density_exponent=data["bgb"]["density_exponent"],
            bgb_dbh_exponent=data["bgb"]["dbh_exponent"],
            agc_fraction=data["agc_fraction"],
            bgc_fraction=data["bgc_fraction"],
            loi_to_c_divisor=data["loi_to_c_divisor"],
        )


@dataclass(frozen=True)
class Method:
    version: str
    references: tuple[str, ...]
    coefficients: Coefficients = Coefficients()
    approval_status: str = "pending-scientific-approval"
    effective_date: date | None = None
    # None means no rounding rule has been approved; callers retain full precision.
    output_decimal_places: int | None = None

    def __post_init__(self) -> None:
        if (
            not self.version.strip()
            or not self.references
            or any(not reference.strip() for reference in self.references)
        ):
            raise ValueError("A method needs a version and references")
        if not isinstance(self.references, tuple):
            raise TypeError("References must be an immutable tuple")
        if self.approval_status not in {"pending-scientific-approval", "approved", "rejected"}:
            raise ValueError("Invalid method approval status")
        if self.approval_status == "approved" and self.effective_date is None:
            raise ValueError("Approved methods need an effective date")
        digits = self.output_decimal_places
        if digits is not None and (type(digits) is not int or not 0 <= digits <= 15):
            raise ValueError("Output decimal places must be an integer from 0 to 15")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "references": list(self.references),
            "coefficients_json": self.coefficients.to_dict(),
            "approval_status": self.approval_status,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "rounding_rule": (
                {}
                if self.output_decimal_places is None
                else {"decimal_places": self.output_decimal_places, "mode": "half-even"}
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Method":
        rule = data["rounding_rule"]
        if rule and (set(rule) != {"decimal_places", "mode"} or rule["mode"] != "half-even"):
            raise ValueError("Unsupported rounding rule")
        return cls(
            version=data["version"],
            references=tuple(data["references"]),
            coefficients=Coefficients.from_dict(data["coefficients_json"]),
            approval_status=data["approval_status"],
            effective_date=date.fromisoformat(data["effective_date"])
            if data["effective_date"]
            else None,
            output_decimal_places=rule.get("decimal_places"),
        )


def round_output(value: float | None, method: Method) -> float | None:
    """Display/export boundary only; never feed rounded values back into calculations."""
    if value is None or method.output_decimal_places is None:
        return value
    if not isfinite(value):
        raise ValueError("Output must be finite")
    with localcontext() as context:
        context.prec = 400
        quantum = Decimal(1).scaleb(-method.output_decimal_places)
        return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN))

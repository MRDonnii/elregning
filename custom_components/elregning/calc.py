"""Beregninger for Elregning uden Home Assistant, så de kan testes alene.

Claude AI, 2026-11-01. Brugeren: "jeg vil egentlig også gerne kunne skrive ind hvad mine regninger lyder på og
sammeholde det med det vi selv måler så vi kan se hvad det burde lande på næste måned".

En regning sammenlignes med HA's egen måling for samme periode: kWh fra elmåleren og kroner fra energi-dashboardets
omkostningssensor (forbrug × Strømligning-pris). Forholdet mellem regning og egen beregning på de seneste hele regninger
bruges til at rette prognosen for denne måned, så faste gebyrer, abonnementer og små prisforskelle kommer med.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Andel af regningens dage, HA skal have målinger for, før regningen bruges i sammenligningen
MIN_COVERAGE = 0.9
# Antal seneste hele regninger, forholdet regnes over
RATIO_BILLS = 3
# Forholdet bruges kun, hvis det ligger inden for dette (ellers er noget galt med en indtastning eller målingen)
RATIO_LIMITS = (0.5, 2.0)


@dataclass(frozen=True)
class Measured:
    """HA's egen måling for en periode."""

    kwh: float | None
    cost: float | None
    days_with_data: int
    days: int

    @property
    def coverage(self) -> float:
        return self.days_with_data / self.days if self.days else 0.0


def bill_days(start: date, end: date) -> int:
    """Antal dage i en regningsperiode, begge dage med."""
    return (end - start).days + 1


def compare_bill(bill: dict, measured: Measured) -> dict:
    """Regning mod egen måling. Alle beløb i kr inkl. moms."""
    start, end = date.fromisoformat(bill["start"]), date.fromisoformat(bill["end"])
    days = bill_days(start, end)
    amount = float(bill["amount"])
    kwh = bill.get("kwh")
    out = {
        "id": bill["id"],
        "start": bill["start"],
        "end": bill["end"],
        "days": days,
        "amount": round(amount, 2),
        "kwh": round(float(kwh), 2) if kwh is not None else None,
        "supplier": bill.get("supplier"),
        "note": bill.get("note"),
        "measured_kwh": round(measured.kwh, 2) if measured.kwh is not None else None,
        "measured_cost": round(measured.cost, 2) if measured.cost is not None else None,
        "coverage": round(measured.coverage, 3),
        "complete": measured.coverage >= MIN_COVERAGE and measured.cost is not None,
        "difference": None,
        "difference_pct": None,
        "kwh_difference": None,
        "kwh_difference_pct": None,
        "bill_price": round(amount / float(kwh), 3) if kwh else None,
        "measured_price": None,
    }
    if measured.cost:
        out["difference"] = round(amount - measured.cost, 2)
        out["difference_pct"] = round((amount - measured.cost) / measured.cost * 100, 1)
    if measured.kwh:
        out["measured_price"] = round(measured.cost / measured.kwh, 3) if measured.cost is not None else None
        if kwh is not None:
            out["kwh_difference"] = round(float(kwh) - measured.kwh, 2)
            out["kwh_difference_pct"] = round((float(kwh) - measured.kwh) / measured.kwh * 100, 1)
    return out


def bill_ratio(compared: list[dict]) -> tuple[float | None, int]:
    """Regning ÷ egen beregning over de seneste hele regninger (vægtet efter beløb)."""
    usable = [c for c in compared if c["complete"] and c["measured_cost"]]
    usable.sort(key=lambda c: c["end"])
    usable = usable[-RATIO_BILLS:]
    if not usable:
        return None, 0
    ratio = sum(c["amount"] for c in usable) / sum(c["measured_cost"] for c in usable)
    if not RATIO_LIMITS[0] <= ratio <= RATIO_LIMITS[1]:
        return None, 0
    return ratio, len(usable)


def forecast(
    so_far_cost: float,
    so_far_kwh: float,
    daily_cost: float | None,
    daily_kwh: float | None,
    remaining_days: float,
    ratio: float | None,
) -> dict:
    """Prognose for hele måneden: målt indtil nu + resten af måneden med det seneste daglige gennemsnit."""
    own_cost = so_far_cost + (daily_cost or 0.0) * remaining_days
    own_kwh = so_far_kwh + (daily_kwh or 0.0) * remaining_days
    return {
        "own_cost": round(own_cost, 2),
        "kwh": round(own_kwh, 1),
        "bill": round(own_cost * ratio, 2) if ratio else round(own_cost, 2),
        "ratio": round(ratio, 4) if ratio else None,
    }

"""Henter HA's egne målinger fra statistikken og sammenholder dem med regningerne."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .calc import Measured, bill_ratio, compare_bill, forecast
from .const import AVERAGE_DAYS, CONF_COST, CONF_ENERGY, DOMAIN, HISTORY_MONTHS, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


def _midnight(day: date) -> datetime:
    """Lokal midnat for en dato."""
    return dt_util.start_of_local_day(day)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    return date(day.year + month // 12, month % 12 + 1, 1)


class ElregningCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Én samlet beregning, som alle sensorer og kortet læser fra."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=30))
        self.entry = entry
        self.store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.bills: list[dict[str, Any]] = []

    @property
    def energy_id(self) -> str:
        return self.entry.options.get(CONF_ENERGY, self.entry.data.get(CONF_ENERGY))

    @property
    def cost_id(self) -> str:
        return self.entry.options.get(CONF_COST, self.entry.data.get(CONF_COST))

    async def async_load(self) -> None:
        data = await self.store.async_load() or {}
        self.bills = list(data.get("bills", []))

    async def async_save(self) -> None:
        await self.store.async_save({"bills": self.bills})

    async def _daily(self, start: datetime, end: datetime) -> dict[str, dict[float, float]]:
        """Ændring pr. lokal dag for elmåler og omkostning: {statistic_id: {dagens start (ts): ændring}}."""
        if end <= start:
            return {self.energy_id: {}, self.cost_id: {}}
        ids = {self.energy_id, self.cost_id}
        rows = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period, self.hass, start, end, ids, "day", None, {"change"}
        )
        out: dict[str, dict[float, float]] = {i: {} for i in ids}
        # Med period "day" tager HA også den dag med, som slutpunktet ligger i; den skal ikke tælles med
        first, stop = start.timestamp(), end.timestamp()
        for stat_id, values in rows.items():
            for row in values:
                if row.get("change") is not None and first <= row["start"] < stop:
                    out[stat_id][row["start"]] = float(row["change"])
        return out

    def _sum(self, daily: dict[str, dict[float, float]], stat_id: str) -> float | None:
        values = daily.get(stat_id, {})
        return sum(values.values()) if values else None

    async def _measured(self, start: date, end: date) -> Measured:
        """Egen måling for start–end (begge dage med), kun hele dage frem til i dag."""
        days = (end - start).days + 1
        stop = min(_midnight(end + timedelta(days=1)), dt_util.now())
        daily = await self._daily(_midnight(start), stop)
        with_data = len(set(daily.get(self.energy_id, {})) & set(daily.get(self.cost_id, {})))
        return Measured(
            kwh=self._sum(daily, self.energy_id),
            cost=self._sum(daily, self.cost_id),
            days_with_data=min(with_data, days),
            days=days,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        today = now.date()

        compared = []
        for bill in sorted(self.bills, key=lambda b: (b["start"], b["end"])):
            measured = await self._measured(date.fromisoformat(bill["start"]), date.fromisoformat(bill["end"]))
            compared.append(compare_bill(bill, measured))
        ratio, ratio_bills = bill_ratio(compared)

        # Denne måned indtil nu (statistikken har hele timer; den igangværende time kommer med ved næste opdatering)
        month_start = _month_start(today)
        month_daily = await self._daily(_midnight(month_start), now)
        so_far_cost = self._sum(month_daily, self.cost_id) or 0.0
        so_far_kwh = self._sum(month_daily, self.energy_id) or 0.0

        # Dagligt gennemsnit over de seneste hele dage (højst AVERAGE_DAYS, kun dage med målinger)
        avg_daily = await self._daily(_midnight(today - timedelta(days=AVERAGE_DAYS)), _midnight(today))
        cost_days = avg_daily.get(self.cost_id, {})
        kwh_days = avg_daily.get(self.energy_id, {})
        daily_cost = sum(cost_days.values()) / len(cost_days) if cost_days else None
        daily_kwh = sum(kwh_days.values()) / len(kwh_days) if kwh_days else None

        next_month = _add_months(month_start, 1)
        remaining = max(0.0, (_midnight(next_month) - now).total_seconds() / 86400)
        days_in_month = (next_month - month_start).days
        prognosis = forecast(so_far_cost, so_far_kwh, daily_cost, daily_kwh, remaining, ratio)

        # Målt forbrug pr. måned (de seneste måneder), så regningen kan holdes op mod den måned, den dækker
        months = []
        for back in range(HISTORY_MONTHS, 0, -1):
            first = _add_months(month_start, -back)
            last = _add_months(first, 1) - timedelta(days=1)
            measured = await self._measured(first, last)
            if measured.days_with_data and measured.kwh:
                months.append(
                    {
                        "month": first.strftime("%Y-%m"),
                        "kwh": round(measured.kwh, 1) if measured.kwh is not None else None,
                        "cost": round(measured.cost, 2) if measured.cost is not None else None,
                        "coverage": round(measured.coverage, 3),
                    }
                )

        return {
            "bills": list(reversed(compared)),
            "ratio": ratio,
            "ratio_bills": ratio_bills,
            "month": month_start.strftime("%Y-%m"),
            "so_far_cost": round(so_far_cost, 2),
            "so_far_kwh": round(so_far_kwh, 2),
            "daily_cost": round(daily_cost, 2) if daily_cost is not None else None,
            "daily_kwh": round(daily_kwh, 2) if daily_kwh is not None else None,
            "average_days": len(cost_days),
            "remaining_days": round(remaining, 2),
            "days_in_month": days_in_month,
            "forecast": prognosis,
            "months": months,
        }

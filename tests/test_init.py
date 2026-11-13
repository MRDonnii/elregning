"""Hele integrationen i en test-HA med timestatistik for elmåler og omkostning (Claude AI, 2026-11-01)."""

from datetime import datetime, timedelta

import pytest
import voluptuous as vol
from homeassistant.components.recorder.statistics import async_import_statistics

try:  # HA 2025.4+ wants mean_type (and from 2025.10 unit_class) in the metadata
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # older HA only knows has_mean
    StatisticMeanType = None
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.elregning.const import DOMAIN

ENERGY, COST = "sensor.el_energy", "sensor.el_energy_cost"
KWH_PER_HOUR, PRICE = 1.0, 2.0


async def _seed(hass, end_utc):
    """1 kWh i timen til 2 kr fra 1. september (lokal tid) til end_utc."""
    tz = dt_util.get_default_time_zone()
    start = datetime(2026, 9, 1, tzinfo=tz).astimezone(dt_util.UTC)
    rows_e, rows_c, t, total = [], [], start - timedelta(hours=1), 0.0
    rows_e.append({"start": t, "state": 0.0, "sum": 0.0})
    rows_c.append({"start": t, "state": 0.0, "sum": 0.0})
    t = start
    while t < end_utc:
        total += KWH_PER_HOUR
        rows_e.append({"start": t, "state": total, "sum": total})
        rows_c.append({"start": t, "state": total * PRICE, "sum": total * PRICE})
        t += timedelta(hours=1)
    for stat_id, unit, unit_class, rows in (
        (ENERGY, "kWh", "energy", rows_e),
        (COST, "DKK", None, rows_c),
    ):
        metadata = {
            "has_mean": False,
            "has_sum": True,
            "name": None,
            "source": "recorder",
            "statistic_id": stat_id,
            "unit_of_measurement": unit,
        }
        if StatisticMeanType is not None:
            metadata["mean_type"] = StatisticMeanType.NONE
            metadata["unit_class"] = unit_class
        async_import_statistics(hass, metadata, rows)
    await async_wait_recording_done(hass)


def _hours(a, b):
    tz = dt_util.get_default_time_zone()
    # Samme tzinfo trækkes fra som naive tider i Python, så begge regnes om til UTC først
    utc = [datetime.fromisoformat(x).replace(tzinfo=tz).astimezone(dt_util.UTC) for x in (a, b)]
    return (utc[1] - utc[0]).total_seconds() / 3600


@pytest.mark.parametrize("hass_time_zone", ["Europe/Copenhagen"])
async def test_bill_compare_and_forecast(hass, recorder_mock, freezer, hass_time_zone):
    await hass.config.async_set_time_zone(hass_time_zone)
    now = datetime(2026, 11, 15, 12, 0, tzinfo=dt_util.get_default_time_zone())
    freezer.move_to(now)
    await _seed(hass, now.astimezone(dt_util.UTC))

    entry = MockConfigEntry(domain=DOMAIN, data={"energy_entity": ENERGY, "cost_entity": COST}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Oktober har en ekstra time (sommertid slutter 25/10)
    oct_hours = _hours("2026-10-01T00:00", "2026-11-01T00:00")
    assert oct_hours == 745
    result = await hass.services.async_call(
        DOMAIN,
        "add_bill",
        {
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "amount": 1600,
            "kwh": 744,
            "supplier": "Vindstød",
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    bill_id = result["id"]

    last = hass.states.get("sensor.elregning_seneste_regning")
    assert float(last.state) == 1600
    bills = last.attributes["regninger"]
    assert len(bills) == 1 and bills[0]["complete"]
    assert bills[0]["measured_kwh"] == oct_hours and bills[0]["measured_cost"] == oct_hours * PRICE
    assert bills[0]["difference"] == round(1600 - oct_hours * PRICE, 2)
    assert float(hass.states.get("sensor.elregning_afvigelse_seneste_regning").state) == round(
        (1600 - 1490) / 1490 * 100, 1
    )

    so_far = hass.states.get("sensor.elregning_malt_denne_maned")
    so_far_h = _hours("2026-11-01T00:00", "2026-11-15T12:00")
    assert float(so_far.state) == so_far_h * PRICE and so_far.attributes["kwh"] == so_far_h

    fc = hass.states.get("sensor.elregning_prognose_denne_maned")
    ratio = 1600 / (oct_hours * PRICE)
    remaining = _hours("2026-11-15T12:00", "2026-12-01T00:00") / 24
    own = so_far_h * PRICE + 24 * PRICE * remaining
    assert fc.attributes["dagligt_gennemsnit"] == 48 and fc.attributes["gennemsnit_dage"] == 14
    assert fc.attributes["egen_beregning"] == round(own, 2)
    assert float(fc.state) == round(own * ratio, 2)
    assert [m["month"] for m in fc.attributes["maaneder"]] == ["2026-09", "2026-10"]

    # Rette og slette
    await hass.services.async_call(DOMAIN, "update_bill", {"id": bill_id, "amount": 1490}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.elregning_afvigelse_seneste_regning").state) == 0.0
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "update_bill", {"id": bill_id, "end_date": "2026-09-01"}, blocking=True)
    await hass.services.async_call(DOMAIN, "delete_bill", {"id": bill_id}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.elregning_seneste_regning").state == "unknown"
    # Uden regninger er prognosen HA's egen beregning
    assert float(hass.states.get("sensor.elregning_prognose_denne_maned").state) == round(own, 2)

    # Regningerne overlever en genindlæsning
    await hass.services.async_call(
        DOMAIN,
        "add_bill",
        {"start_date": "2026-09-01", "end_date": "2026-09-30", "amount": 1500},
        blocking=True,
        return_response=True,
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.elregning_seneste_regning").state) == 1500


@pytest.mark.parametrize("hass_time_zone", ["Europe/Copenhagen"])
async def test_gas_bills_are_kept_apart(hass, recorder_mock, freezer, hass_time_zone):
    """Gasregninger gemmes og lægges sammen pr. år, men holdes ikke op mod elmåleren (Claude AI, 2026-11-13)."""
    await hass.config.async_set_time_zone(hass_time_zone)
    now = datetime(2026, 11, 15, 12, 0, tzinfo=dt_util.get_default_time_zone())
    freezer.move_to(now)
    await _seed(hass, now.astimezone(dt_util.UTC))
    entry = MockConfigEntry(domain=DOMAIN, data={"energy_entity": ENERGY, "cost_entity": COST}, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for data in (
        {"start_date": "2026-10-01", "end_date": "2026-10-31", "amount": 1600, "kwh": 744},
        # Gas for samme måned: må ikke blive "seneste regning" eller trække prognosen
        {"start_date": "2026-10-01", "end_date": "2026-10-31", "amount": 900, "m3": 100, "utility": "gas"},
        {"start_date": "2025-10-01", "end_date": "2025-12-31", "amount": 3000, "m3": 600, "utility": "gas"},
        # Fjernvarme a conto: heller ikke med i elsammenligningen
        {
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "amount": 1160,
            "kwh": 1477,
            "utility": "fjernvarme",
            "aconto": True,
        },
    ):
        await hass.services.async_call(DOMAIN, "add_bill", data, blocking=True, return_response=True)
    await hass.async_block_till_done()

    last = hass.states.get("sensor.elregning_seneste_regning")
    assert float(last.state) == 1600
    assert [b["utility"] for b in last.attributes["regninger"]] == ["el"]
    gas = last.attributes["gasregninger"]
    assert [b["start"] for b in gas] == ["2026-10-01", "2025-10-01"]
    assert gas[0]["m3"] == 100 and gas[0]["price_m3"] == 9.0
    years = {(y["year"], y["utility"]): y for y in last.attributes["aar"]}
    assert years[(2026, "el")]["amount"] == 1600 and years[(2026, "gas")]["m3"] == 100
    assert years[(2025, "gas")]["amount"] == 3000
    heat = last.attributes["fjernvarmeregninger"]
    assert len(heat) == 1 and heat[0]["aconto"] and heat[0]["utility"] == "fjernvarme"
    assert heat[0]["price_kwh"] == round(1160 / 1477, 3)
    assert years[(2026, "fjernvarme")]["kwh"] == 1477
    ratio = hass.states.get("sensor.elregning_prognose_denne_maned").attributes["forhold_regning_maaling"]
    assert ratio == round(1600 / (745 * PRICE), 4)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "add_bill",
            {"start_date": "2026-10-01", "end_date": "2026-10-31", "amount": 1, "utility": "vand"},
            blocking=True,
            return_response=True,
        )

"""Hele integrationen i en test-HA med timestatistik for elmåler og omkostning (Claude AI, 2026-11-01)."""

from datetime import datetime, timedelta

import pytest
from homeassistant.components.recorder.statistics import async_import_statistics
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
    for stat_id, unit, rows in ((ENERGY, "kWh", rows_e), (COST, "DKK", rows_c)):
        async_import_statistics(
            hass,
            {
                "has_mean": False,
                "has_sum": True,
                "name": None,
                "source": "recorder",
                "statistic_id": stat_id,
                "unit_of_measurement": unit,
            },
            rows,
        )
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

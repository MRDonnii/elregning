"""Elregning: skriv elregningerne ind og hold dem op mod det, HA selv har målt (Claude AI, 2026-11-01)."""

from __future__ import annotations

import uuid
from datetime import date

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SERVICE_ADD, SERVICE_DELETE, SERVICE_UPDATE
from .coordinator import ElregningCoordinator

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_FIELDS = {
    vol.Optional("kwh"): vol.Any(None, vol.All(vol.Coerce(float), vol.Range(min=0))),
    vol.Optional("supplier"): vol.Any(None, cv.string),
    vol.Optional("note"): vol.Any(None, cv.string),
}
ADD_SCHEMA = vol.Schema(
    {
        vol.Required("start_date"): cv.date,
        vol.Required("end_date"): cv.date,
        vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        **_FIELDS,
    }
)
UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Optional("amount"): vol.All(vol.Coerce(float), vol.Range(min=0)),
        **_FIELDS,
    }
)
DELETE_SCHEMA = vol.Schema({vol.Required("id"): cv.string})


def _coordinator(hass: HomeAssistant) -> ElregningCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Elregning er ikke sat op")
    return entries[0].runtime_data


def _apply(bill: dict, data: dict) -> None:
    """Skriv felterne fra et servicekald ind i en regning og tjek perioden."""
    for key, target in (("start_date", "start"), ("end_date", "end")):
        if key in data:
            bill[target] = data[key].isoformat()
    if "amount" in data:
        bill["amount"] = round(float(data["amount"]), 2)
    for key in ("kwh", "supplier", "note"):
        if key in data:
            value = data[key]
            bill[key] = None if value in (None, "") else value
    if date.fromisoformat(bill["end"]) < date.fromisoformat(bill["start"]):
        raise ServiceValidationError("Slutdatoen ligger før startdatoen")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ElregningCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))

    if not hass.services.has_service(DOMAIN, SERVICE_ADD):

        async def add_bill(call: ServiceCall) -> ServiceResponse:
            coord = _coordinator(hass)
            bill = {"id": uuid.uuid4().hex[:10], "created": dt_util.now().isoformat()}
            _apply(bill, dict(call.data))
            coord.bills.append(bill)
            await coord.async_save()
            await coord.async_refresh()
            return {"id": bill["id"]}

        async def update_bill(call: ServiceCall) -> None:
            coord = _coordinator(hass)
            bill = next((b for b in coord.bills if b["id"] == call.data["id"]), None)
            if bill is None:
                raise ServiceValidationError(f"Ingen regning med id {call.data['id']}")
            changed = dict(bill)
            _apply(changed, dict(call.data))
            bill.update(changed)
            await coord.async_save()
            await coord.async_refresh()

        async def delete_bill(call: ServiceCall) -> None:
            coord = _coordinator(hass)
            before = len(coord.bills)
            coord.bills = [b for b in coord.bills if b["id"] != call.data["id"]]
            if len(coord.bills) == before:
                raise ServiceValidationError(f"Ingen regning med id {call.data['id']}")
            await coord.async_save()
            await coord.async_refresh()

        hass.services.async_register(DOMAIN, SERVICE_ADD, add_bill, ADD_SCHEMA, SupportsResponse.OPTIONAL)
        hass.services.async_register(DOMAIN, SERVICE_UPDATE, update_bill, UPDATE_SCHEMA)
        hass.services.async_register(DOMAIN, SERVICE_DELETE, delete_bill, DELETE_SCHEMA)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others = [e for e in hass.config_entries.async_loaded_entries(DOMAIN) if e.entry_id != entry.entry_id]
    if unloaded and not others:
        for service in (SERVICE_ADD, SERVICE_UPDATE, SERVICE_DELETE):
            hass.services.async_remove(DOMAIN, service)
    return unloaded

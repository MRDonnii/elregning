"""Opsætning af Elregning: vælg elmåleren og dens omkostning (standard: energi-dashboardets net-forbrug)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import CONF_COST, CONF_ENERGY, DOMAIN


async def _energy_defaults(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """Elmåler og omkostning fra energi-dashboardet (begge formater: med og uden flow_from)."""
    try:
        from homeassistant.components.energy.data import async_get_manager

        manager = await async_get_manager(hass)
        sources = (manager.data or {}).get("energy_sources", [])
    except Exception:  # noqa: BLE001 - energi-dashboardet er valgfrit
        return None, None
    for source in sources:
        if source.get("type") != "grid":
            continue
        flows = source.get("flow_from") or [source]
        for flow in flows:
            energy = flow.get("stat_energy_from")
            if energy:
                return energy, flow.get("stat_cost") or f"{energy}_cost"
    return None, None


def _schema(energy: str | None, cost: str | None) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ENERGY, default=energy or vol.UNDEFINED): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_COST, default=cost or vol.UNDEFINED): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="monetary")
            ),
        }
    )


class ElregningConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Elregning", data=user_input)
        energy, cost = await _energy_defaults(self.hass)
        return self.async_show_form(step_id="user", data_schema=_schema(energy, cost))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ElregningOptionsFlow()


class ElregningOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(current.get(CONF_ENERGY), current.get(CONF_COST))
        )

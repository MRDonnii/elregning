"""Opsætningen foreslår energi-dashboardets elmåler (Claude AI, 2026-11-01)."""

from homeassistant import config_entries
from homeassistant.components.energy.data import async_get_manager
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from custom_components.elregning.const import DOMAIN


async def test_flow_defaults_from_energy_dashboard(hass, recorder_mock):
    assert await async_setup_component(hass, "energy", {})
    manager = await async_get_manager(hass)
    await manager.async_update(
        {
            "energy_sources": [
                {
                    "type": "grid",
                    "cost_adjustment_day": 0,
                    "flow_to": [],
                    "flow_from": [
                        {
                            "stat_energy_from": "sensor.hovedmaler",
                            "stat_cost": None,
                            "entity_energy_price": "sensor.pris",
                            "number_energy_price": None,
                        }
                    ],
                }
            ]
        }
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults == {"energy_entity": "sensor.hovedmaler", "cost_entity": "sensor.hovedmaler_cost"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], defaults)
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Elregning"
    await hass.async_block_till_done()
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT

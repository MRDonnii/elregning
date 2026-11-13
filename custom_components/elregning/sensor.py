"""Sensorer for Elregning: prognose, målt indtil nu, seneste regning og afvigelse."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ElregningCoordinator

CURRENCY = "DKK"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: ElregningCoordinator = entry.runtime_data
    async_add_entities(
        [
            ForecastSensor(coordinator),
            SoFarSensor(coordinator),
            LastBillSensor(coordinator),
            DifferenceSensor(coordinator),
        ]
    )


class _Base(CoordinatorEntity[ElregningCoordinator], SensorEntity):
    _attr_has_entity_name = True
    key = ""

    def __init__(self, coordinator: ElregningCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Elregning",
            manufacturer="Claude AI",
            model="Regning mod egen måling",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _last(self) -> dict[str, Any] | None:
        bills = self.coordinator.data.get("bills") or []
        return bills[0] if bills else None


class ForecastSensor(_Base):
    """Hvad regningen for denne måned forventes at lande på."""

    key = "prognose"
    _attr_name = "Prognose denne måned"
    _attr_icon = "mdi:cash-clock"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"maaneder"})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data["forecast"]["bill"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        f = d["forecast"]
        return {
            "maaned": d["month"],
            "egen_beregning": f["own_cost"],
            "forventet_kwh": f["kwh"],
            "forhold_regning_maaling": f["ratio"],
            "regninger_i_forhold": d["ratio_bills"],
            "maalt_indtil_nu": d["so_far_cost"],
            "maalt_kwh_indtil_nu": d["so_far_kwh"],
            "dagligt_gennemsnit": d["daily_cost"],
            "dagligt_gennemsnit_kwh": d["daily_kwh"],
            "gennemsnit_dage": d["average_days"],
            "dage_tilbage": d["remaining_days"],
            "dage_i_maaned": d["days_in_month"],
            "maaneder": d["months"],
            "energi_sensor": self.coordinator.energy_id,
            "omkostning_sensor": self.coordinator.cost_id,
        }


class SoFarSensor(_Base):
    """HA's egen beregning af månedens elregning indtil nu."""

    key = "maalt"
    _attr_name = "Målt denne måned"
    _attr_icon = "mdi:cash-multiple"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data["so_far_cost"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"kwh": self.coordinator.data["so_far_kwh"], "maaned": self.coordinator.data["month"]}


class LastBillSensor(_Base):
    """Den seneste indtastede regning, med alle regninger og deres sammenligning som attribut."""

    key = "seneste"
    _attr_name = "Seneste regning"
    _attr_icon = "mdi:receipt-text-outline"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"regninger", "gasregninger", "fjernvarmeregninger", "aar"})

    @property
    def native_value(self) -> float | None:
        last = self._last
        return last["amount"] if last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._last or {}
        return {
            "periode_start": last.get("start"),
            "periode_slut": last.get("end"),
            "egen_beregning": last.get("measured_cost"),
            "afvigelse": last.get("difference"),
            "afvigelse_pct": last.get("difference_pct"),
            "kwh": last.get("kwh"),
            "maalt_kwh": last.get("measured_kwh"),
            "daekning": last.get("coverage"),
            "regninger": self.coordinator.data["bills"],
            "gasregninger": self.coordinator.data.get("gas_bills", []),
            "fjernvarmeregninger": self.coordinator.data.get("heat_bills", []),
            "aar": self.coordinator.data.get("years", []),
        }


class DifferenceSensor(_Base):
    """Hvor meget den seneste regning afviger fra HA's egen beregning (positiv = regningen er højere)."""

    key = "afvigelse"
    _attr_name = "Afvigelse seneste regning"
    _attr_icon = "mdi:scale-unbalanced"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        last = self._last
        return last["difference_pct"] if last and last["complete"] else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._last or {}
        return {"afvigelse_kr": last.get("difference"), "hel_maaling": last.get("complete")}

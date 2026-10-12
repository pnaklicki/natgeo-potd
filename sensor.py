"""Sensors for the National Geographic Photo of the Day integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NatGeoPhotoCoordinator, device_info

# Home Assistant states are limited to 255 characters; longer text goes to attributes.
MAX_STATE_LENGTH = 255


def _short_text(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= MAX_STATE_LENGTH:
        return text
    return text[: MAX_STATE_LENGTH - 1].rstrip() + "…"


@dataclass(frozen=True, kw_only=True)
class NatGeoSensorDescription(SensorEntityDescription):
    """Sensor description with a value function."""

    value_fn: Callable[[NatGeoPhotoCoordinator], Any]


SENSORS: tuple[NatGeoSensorDescription, ...] = (
    NatGeoSensorDescription(
        key="title",
        translation_key="title",
        icon="mdi:format-title",
        value_fn=lambda c: _short_text(c.data.title) if c.data else None,
    ),
    NatGeoSensorDescription(
        key="author",
        translation_key="author",
        icon="mdi:camera",
        value_fn=lambda c: _short_text(c.data.author) if c.data else None,
    ),
    NatGeoSensorDescription(
        key="description",
        translation_key="description",
        icon="mdi:text",
        value_fn=lambda c: _short_text(c.data.description) if c.data else None,
    ),
    NatGeoSensorDescription(
        key="last_fetched",
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.data.fetched_at if c.data else None,
    ),
    NatGeoSensorDescription(
        key="image_size",
        translation_key="image_size",
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:file-image",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: (
            round(len(c.data.image_bytes) / 1024, 1)
            if c.data and c.data.image_bytes
            else None
        ),
    ),
    NatGeoSensorDescription(
        key="api_calls",
        translation_key="api_calls",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:api",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.api_calls,
    ),
    NatGeoSensorDescription(
        key="api_errors",
        translation_key="api_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.api_errors,
    ),
    NatGeoSensorDescription(
        key="last_error",
        translation_key="last_error",
        icon="mdi:bug-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _short_text(c.last_error),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: NatGeoPhotoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NatGeoSensor(coordinator, entry, description) for description in SENSORS
    )


class NatGeoSensor(CoordinatorEntity[NatGeoPhotoCoordinator], SensorEntity):
    """Sensor exposing one value of the photo of the day integration."""

    _attr_has_entity_name = True
    entity_description: NatGeoSensorDescription

    def __init__(
        self,
        coordinator: NatGeoPhotoCoordinator,
        entry: ConfigEntry,
        description: NatGeoSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the full text when it was shortened to fit the state limit."""
        if self.entity_description.key not in ("description", "title", "author"):
            return None
        data = self.coordinator.data
        if not data:
            return None
        full = {
            "description": data.description,
            "title": data.title,
            "author": data.author,
        }[self.entity_description.key]
        return {"full_text": full} if full else None

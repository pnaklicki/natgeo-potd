"""Camera entity showing the current National Geographic Photo of the Day."""
from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NatGeoPhotoCoordinator, device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the photo of the day camera."""
    coordinator: NatGeoPhotoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NatGeoPhotoCamera(coordinator, entry)])


class NatGeoPhotoCamera(CoordinatorEntity[NatGeoPhotoCoordinator], Camera):
    """Camera showing today's National Geographic photo."""

    _attr_has_entity_name = True
    _attr_name = None  # use the device name as the entity name
    _attr_icon = "mdi:image-frame"

    def __init__(self, coordinator: NatGeoPhotoCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = device_info(entry)
        self._sync_content_type()

    @callback
    def _sync_content_type(self) -> None:
        """Keep the content type in line with the downloaded image."""
        if self.coordinator.data:
            self.content_type = self.coordinator.data.content_type

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_content_type()
        super()._handle_coordinator_update()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the current photo."""
        photo = self.coordinator.data
        return photo.image_bytes if photo else None

    @property
    def available(self) -> bool:
        """Stay available with the last good photo if a later update fails."""
        return self.coordinator.data is not None

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the full photo details."""
        photo = self.coordinator.data
        if not photo:
            return {}
        return {
            "title": photo.title,
            "author": photo.author,
            "description": photo.description,
            "page_url": photo.page_url,
            "image_url": photo.image_url,
            "last_fetched": photo.fetched_at.isoformat(),
        }

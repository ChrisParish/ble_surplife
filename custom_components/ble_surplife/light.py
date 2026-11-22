"""Light platform for Surplife BLE."""

from __future__ import annotations

import math
from typing import Any

from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.color import brightness_to_value, value_to_brightness

from . import SurplifeConfigEntry
from .const import DOMAIN, MANUFACTURER
from .device import SurplifeDevice
from .protocol import get_product

BRIGHTNESS_SCALE = (1, 100)


def _to_percent(brightness: int) -> int:
    return max(1, math.ceil(brightness_to_value(BRIGHTNESS_SCALE, brightness)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurplifeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the light."""
    async_add_entities([SurplifeLight(entry.runtime_data)])


class SurplifeLight(LightEntity):
    """A Surplife BLE light."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, device: SurplifeDevice) -> None:
        self._device = device
        info = device.info
        product = get_product(info.product_id)
        modes = {ColorMode.HS}
        if product is not None and product.supports_white:
            modes.add(ColorMode.WHITE)
        self._attr_supported_color_modes = modes
        self._attr_color_mode = ColorMode.HS
        self._attr_unique_id = device.address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            connections={(dr.CONNECTION_BLUETOOTH, device.address)},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=product.model if product else f"0x{info.product_id:04X}",
            model_id=f"0x{info.product_id:04X}",
            sw_version=str(info.firmware_version),
            hw_version=f"BLE v{info.ble_version} / LED v{info.led_version}",
        )
        self._update_attrs()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._device.register_callback(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self._update_attrs()
        self.async_write_ha_state()

    @callback
    def _update_attrs(self) -> None:
        self._attr_available = self._device.available
        state = self._device.state
        if state is None:
            self._attr_is_on = None
            return
        self._attr_is_on = state.is_on
        if state.is_white and ColorMode.WHITE in self._attr_supported_color_modes:
            self._attr_color_mode = ColorMode.WHITE
            self._attr_brightness = value_to_brightness(BRIGHTNESS_SCALE, state.white)
        else:
            self._attr_color_mode = ColorMode.HS
            self._attr_hs_color = (float(state.hue), float(state.saturation))
            self._attr_brightness = value_to_brightness(BRIGHTNESS_SCALE, max(state.value, 1))

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness: int | None = kwargs.get(ATTR_BRIGHTNESS)
        try:
            if ATTR_WHITE in kwargs:
                await self._device.set_white(_to_percent(kwargs[ATTR_WHITE]))
            elif ATTR_HS_COLOR in kwargs:
                hue, sat = kwargs[ATTR_HS_COLOR]
                level = brightness if brightness is not None else (self.brightness or 255)
                await self._device.set_hsv(hue, sat, _to_percent(level))
            elif brightness is not None:
                if self._attr_color_mode == ColorMode.WHITE:
                    await self._device.set_white(_to_percent(brightness))
                else:
                    hue, sat = self._attr_hs_color or (0.0, 0.0)
                    await self._device.set_hsv(hue, sat, _to_percent(brightness))
            else:
                await self._device.turn_on()
        except BLEAK_RETRY_EXCEPTIONS as err:
            raise HomeAssistantError(f"Failed to control {self._device.name}: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._device.turn_off()
        except BLEAK_RETRY_EXCEPTIONS as err:
            raise HomeAssistantError(f"Failed to turn off {self._device.name}: {err}") from err

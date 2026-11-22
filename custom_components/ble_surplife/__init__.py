"""The Surplife BLE integration."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .device import SurplifeDevice
from .protocol import parse_advertisement

PLATFORMS: list[Platform] = [Platform.LIGHT]

type SurplifeConfigEntry = ConfigEntry[SurplifeDevice]


async def async_setup_entry(hass: HomeAssistant, entry: SurplifeConfigEntry) -> bool:
    """Set up a Surplife light from a config entry."""
    address: str = entry.unique_id
    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    if service_info is None:
        raise ConfigEntryNotReady(f"Could not find Surplife device with address {address}")
    info = parse_advertisement(service_info.manufacturer_data, service_info.service_data)
    if info is None:
        raise ConfigEntryNotReady(f"Could not parse advertisement from {address}")

    device = SurplifeDevice(service_info.device, info)

    @callback
    def _async_update_ble(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if parsed := parse_advertisement(service_info.manufacturer_data, service_info.service_data):
            device.update_from_advertisement(service_info.device, parsed)

    @callback
    def _async_unavailable(_service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        device.set_available(False)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_ble,
            BluetoothCallbackMatcher({ADDRESS: address}),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(
        bluetooth.async_track_unavailable(hass, _async_unavailable, address, connectable=True)
    )

    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(_event: Event) -> None:
        await device.stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SurplifeConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
    return unload_ok

"""Light entity tests with a mocked BLE client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_HS_COLOR,
    ATTR_WHITE,
    ColorMode,
)
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, CONF_ADDRESS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ble_surplife.const import DOMAIN

from . import ADDRESS, make_service_info

ENTITY_ID = "light.iotbtbb0"
WHITE_STATE_JSON = (
    b'{"code":0,"payload":"EA810000C507'
    b'23241400000000640064000096000000010901009600000000"}'
)


def _notification(cmd_id: int, payload: bytes) -> bytearray:
    n = len(payload)
    return bytearray(bytes([0x04, 0x05, 0x80, 0x00, n >> 8, n & 0xFF, n + 1, cmd_id]) + payload)


@pytest.fixture
def client() -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.mtu_size = 247
    client._backend = None
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    return client


def _payloads(client: MagicMock) -> list[bytes]:
    return [call.args[1][8:] for call in client.write_gatt_char.call_args_list]


async def test_light(hass: HomeAssistant, enable_bluetooth: None, client: MagicMock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS})
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.ble_surplife.bluetooth.async_last_service_info",
            return_value=make_service_info(),
        ),
        patch(
            "custom_components.ble_surplife.device.establish_connection",
            AsyncMock(return_value=client),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_COLOR_MODE] == ColorMode.HS
        assert state.attributes[ATTR_HS_COLOR] == (8.0, 100.0)
        assert state.attributes[ATTR_BRIGHTNESS] == 255

        await hass.services.async_call(LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True)
        assert _payloads(client)[-1] == bytes.fromhex("3b24000000000000000000005f")
        assert hass.states.get(ENTITY_ID).state == STATE_OFF

        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HS_COLOR: (120, 100), ATTR_BRIGHTNESS: 51},
            blocking=True,
        )
        assert _payloads(client) == [
            bytes.fromhex("3b23000000000000000000005e"),
            bytes.fromhex("3ba13c64140000000000000090"),
        ]
        state = hass.states.get(ENTITY_ID)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_HS_COLOR] == (120.0, 100.0)

        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            LIGHT_DOMAIN, "turn_on", {ATTR_ENTITY_ID: ENTITY_ID, ATTR_WHITE: 255}, blocking=True
        )
        assert _payloads(client) == [bytes.fromhex("3b010000640064000000000004")]
        assert hass.states.get(ENTITY_ID).attributes[ATTR_COLOR_MODE] == ColorMode.WHITE

        notify = client.start_notify.call_args.args[1]
        notify(None, _notification(0x0C, WHITE_STATE_JSON))
        await hass.async_block_till_done()
        state = hass.states.get(ENTITY_ID)
        assert state.attributes[ATTR_COLOR_MODE] == ColorMode.WHITE
        assert state.attributes[ATTR_BRIGHTNESS] == 255

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

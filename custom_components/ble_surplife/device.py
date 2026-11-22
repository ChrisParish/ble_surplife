"""BLE connection manager for a Surplife light (no Home Assistant imports)."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
from collections.abc import Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)

from .protocol import (
    CMD_CONTROL,
    CMD_QUERY,
    DeviceInfo,
    Framer,
    LightState,
    Reassembler,
    hsv_command,
    parse_notification_payload,
    parse_state,
    power_command,
    state_query_command,
    white_command,
)
from .protocol.framing import max_frame_length, write_version

_LOGGER = logging.getLogger(__name__)

WRITE_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
STATE_CMD_IDS = {0x0A, 0x0C, 0x16}
DEFAULT_MTU = 23


class SurplifeDevice:
    """A single light: passive advertisement state plus on-demand GATT control."""

    def __init__(self, ble_device: BLEDevice, info: DeviceInfo, idle_timeout: float = 90.0) -> None:
        self._ble_device = ble_device
        self._info = info
        self._idle_timeout = idle_timeout
        self._state: LightState | None = parse_state(info.state)
        self._client: BleakClientWithServiceCache | None = None
        self._framer = Framer(write_version(info.ble_version))
        self._reassembler = Reassembler()
        self._max_frame = max_frame_length(DEFAULT_MTU, self._framer.version)
        self._op_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._disconnect_task: asyncio.Task | None = None
        self._callbacks: list[Callable[[], None]] = []
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        if available != self._available:
            self._available = available
            self._fire()

    @property
    def address(self) -> str:
        return self._ble_device.address

    @property
    def name(self) -> str:
        return self._ble_device.name or self.address

    @property
    def info(self) -> DeviceInfo:
        return self._info

    @property
    def state(self) -> LightState | None:
        return self._state

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.append(callback)
        return lambda: self._callbacks.remove(callback)

    def _fire(self) -> None:
        for callback in list(self._callbacks):
            callback()

    def update_from_advertisement(self, ble_device: BLEDevice, info: DeviceInfo) -> None:
        """Apply a new advertisement (passive state update)."""
        self._ble_device = ble_device
        self._info = info
        self.set_available(True)
        state = parse_state(info.state)
        if state is not None and state != self._state:
            self._state = state
            self._fire()

    async def turn_on(self) -> None:
        await self._send(power_command(True))
        self._optimistic(is_on=True)

    async def turn_off(self) -> None:
        await self._send(power_command(False))
        self._optimistic(is_on=False)

    async def set_hsv(self, hue: float, saturation: float, value: int) -> None:
        await self._ensure_on()
        await self._send(hsv_command(hue, saturation, value))
        self._optimistic(is_on=True, hue=round(hue) % 360, saturation=round(saturation), value=value, white=0)

    async def set_white(self, level: int) -> None:
        await self._ensure_on()
        await self._send(white_command(level))
        self._optimistic(is_on=True, hue=0, saturation=0, value=level, white=level)

    async def query_state(self) -> None:
        await self._send(state_query_command(), CMD_QUERY)

    async def stop(self) -> None:
        self._cancel_disconnect_timer()
        await self._disconnect()

    async def _ensure_on(self) -> None:
        if self._state is None or not self._state.is_on:
            await self._send(power_command(True))

    def _optimistic(self, **changes) -> None:
        if self._state is None:
            return
        self._state = dataclasses.replace(self._state, **changes)
        self._fire()

    async def _send(self, payload: bytes, cmd_id: int = CMD_CONTROL) -> None:
        async with self._op_lock:
            for attempt in range(2):
                try:
                    client = await self._ensure_connected()
                    for frame in self._framer.frames(cmd_id, payload, self._max_frame):
                        await client.write_gatt_char(WRITE_UUID, frame, response=False)
                    return
                except BLEAK_RETRY_EXCEPTIONS as err:
                    if attempt:
                        raise
                    _LOGGER.debug("%s: write failed (%s), reconnecting", self.name, err)
                    await self._disconnect()

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            self._reset_disconnect_timer()
            return self._client
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                self._reset_disconnect_timer()
                return self._client
            _LOGGER.debug("%s: connecting", self.name)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self.name,
                disconnected_callback=self._on_disconnected,
                ble_device_callback=lambda: self._ble_device,
            )
            # BlueZ reports MTU 23 until it is explicitly acquired.
            backend = getattr(client, "_backend", None)
            if backend is not None and hasattr(backend, "_acquire_mtu"):
                with contextlib.suppress(BleakError, AttributeError, NotImplementedError):
                    await backend._acquire_mtu()
            self._max_frame = max_frame_length(client.mtu_size or DEFAULT_MTU, self._framer.version)
            self._reassembler = Reassembler()
            await client.start_notify(NOTIFY_UUID, self._on_notify)
            self._client = client
            self._reset_disconnect_timer()
            return client

    def _on_notify(self, _sender, data: bytearray) -> None:
        message = self._reassembler.feed(bytes(data))
        if message is None or message.cmd_id not in STATE_CMD_IDS:
            return
        state = parse_notification_payload(message.payload)
        if state is not None and state != self._state:
            self._state = state
            self._fire()

    def _on_disconnected(self, _client) -> None:
        _LOGGER.debug("%s: disconnected", self.name)
        self._client = None
        self._cancel_disconnect_timer()

    def _reset_disconnect_timer(self) -> None:
        self._cancel_disconnect_timer()
        loop = asyncio.get_running_loop()
        self._disconnect_timer = loop.call_later(self._idle_timeout, self._idle_disconnect)

    def _cancel_disconnect_timer(self) -> None:
        if self._disconnect_timer is not None:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    def _idle_disconnect(self) -> None:
        self._disconnect_timer = None
        self._disconnect_task = asyncio.get_running_loop().create_task(self._disconnect())

    async def _disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        with contextlib.suppress(*BLEAK_RETRY_EXCEPTIONS):
            await client.stop_notify(NOTIFY_UUID)
        with contextlib.suppress(*BLEAK_RETRY_EXCEPTIONS):
            await client.disconnect()

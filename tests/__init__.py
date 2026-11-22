"""Shared test data for Surplife BLE (captured from a real IOTBT light, product 0xC5)."""

from __future__ import annotations

import time

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

ADDRESS = "E4:98:BB:B3:9B:B0"
NAME = "IOTBTBB0"
SVC_UUID = "00005a02-0000-1000-8000-00805f9b34fb"
MANUFACTURER_DATA = {0x5A02: bytes.fromhex("5b2324015000046464000000009600000001090100960000000000")}
SERVICE_DATA = {SVC_UUID: bytes.fromhex("5b07e498bbb39bb000c52c070102")}


def make_service_info(
    address: str = ADDRESS,
    name: str = NAME,
    manufacturer_data: dict[int, bytes] | None = None,
    service_data: dict[str, bytes] | None = None,
) -> BluetoothServiceInfoBleak:
    manufacturer_data = MANUFACTURER_DATA if manufacturer_data is None else manufacturer_data
    service_data = SERVICE_DATA if service_data is None else service_data
    advertisement = AdvertisementData(
        local_name=name,
        manufacturer_data=manufacturer_data,
        service_data=service_data,
        service_uuids=[],
        tx_power=-127,
        rssi=-60,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data=manufacturer_data,
        service_data=service_data,
        service_uuids=[],
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=advertisement,
        connectable=True,
        time=time.monotonic(),
        tx_power=-127,
    )

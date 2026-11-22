"""Advertisement parsing (mirrors com.zengge.hagallbjarkan.device.ZGHBDevice.newDevice)."""

from __future__ import annotations

from dataclasses import dataclass

MANUFACTURER_HIGH_BYTES = range(0x5A, 0x5F)
AUTH_REQUIRED_HIGH_BYTE = 0x5D


@dataclass(frozen=True)
class DeviceInfo:
    """Identity and state carried in the advertisement."""

    manufacturer: int
    ble_version: int
    mac: str
    product_id: int
    firmware_version: int
    led_version: int
    state: bytes

    @property
    def requires_auth(self) -> bool:
        return self.manufacturer >> 8 == AUTH_REQUIRED_HIGH_BYTE


def _uuid16(uuid: str) -> int | None:
    if len(uuid) == 36 and uuid.endswith("-0000-1000-8000-00805f9b34fb"):
        return int(uuid[4:8], 16)
    return None


def _info_from(raw: bytes) -> tuple[int, int, str, int, int, int]:
    """Device info block; raw includes the 2 little-endian company/uuid bytes."""
    manufacturer = raw[1] << 8 | raw[2]
    ble_version = raw[3]
    mac = ":".join(f"{b:02X}" for b in raw[4:10])
    product_id = raw[10] << 8 | raw[11]
    firmware = raw[12]
    if ble_version >= 6 and len(raw) >= 15:
        firmware |= (raw[14] >> 2) << 8
    return manufacturer, ble_version, mac, product_id, firmware, raw[13]


def parse_advertisement(
    manufacturer_data: dict[int, bytes], service_data: dict[str, bytes]
) -> DeviceInfo | None:
    """Parse bleak-style manufacturer and service data; None if not a supported Zengge device."""
    mfr_raw = next(
        (
            bytes([cid & 0xFF, cid >> 8]) + bytes(data)
            for cid, data in manufacturer_data.items()
            if cid >> 8 in MANUFACTURER_HIGH_BYTES
        ),
        None,
    )
    if mfr_raw is None:
        return None

    svc_raw = None
    for uuid, data in service_data.items():
        u16 = _uuid16(uuid)
        if u16 is not None and u16 >> 8 in MANUFACTURER_HIGH_BYTES and len(data) + 2 in (16, 29):
            svc_raw = bytes([u16 & 0xFF, u16 >> 8]) + bytes(data)
            break

    if svc_raw is not None:
        manufacturer, ble_version, mac, product_id, firmware, led = _info_from(svc_raw)
        if manufacturer >> 8 not in MANUFACTURER_HIGH_BYTES:
            return None
        if ble_version >= 7:
            state = mfr_raw[3:28]
        elif ble_version >= 5:
            state = mfr_raw[3:]
        else:
            state = b""
    else:
        if len(mfr_raw) != 29:
            return None
        manufacturer, ble_version, mac, product_id, firmware, led = _info_from(mfr_raw)
        if manufacturer >> 8 not in MANUFACTURER_HIGH_BYTES:
            return None
        state = mfr_raw[16:27] if ble_version >= 5 else b""

    return DeviceInfo(
        manufacturer=manufacturer,
        ble_version=ble_version,
        mac=mac,
        product_id=product_id,
        firmware_version=firmware,
        led_version=led,
        state=bytes(state),
    )

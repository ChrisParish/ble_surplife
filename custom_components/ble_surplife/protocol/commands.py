"""Application-layer command payloads ("unified command 1.0", 0x3B family)."""

from __future__ import annotations

CMD_QUERY = 0x0A
CMD_CONTROL = 0x0B


def _with_checksum(data: bytes) -> bytes:
    return data + bytes([sum(data) & 0xFF])


def state_query_command() -> bytes:
    return _with_checksum(bytes([0x81, 0x8A, 0x8B]))


def power_command(on: bool) -> bytes:
    return _with_checksum(bytes([0x3B, 0x23 if on else 0x24] + [0] * 10))


def hsv_command(hue: float, saturation: float, value: int) -> bytes:
    """Colour: hue 0-359, saturation 0-100, value (brightness) 0-100."""
    h = round(hue) % 360
    s = max(0, min(100, round(saturation)))
    v = max(0, min(100, int(value)))
    hs = (h << 7) | s
    return _with_checksum(bytes([0x3B, 0xA1, hs >> 8, hs & 0xFF, v, 0, 0, 0, 0, 0, 0, 0]))


def white_command(level: int) -> bytes:
    """White channel at level 0-100 (bright_value_v2 template)."""
    v = max(0, min(100, int(level)))
    return _with_checksum(bytes([0x3B, 0x01, 0, 0, v, 0, v, 0, 0, 0, 0, 0]))

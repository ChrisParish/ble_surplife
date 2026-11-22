"""Surplife / Zengge BLE protocol (no Home Assistant dependencies)."""

from .advertisement import DeviceInfo, parse_advertisement
from .commands import (
    CMD_CONTROL,
    CMD_QUERY,
    hsv_command,
    power_command,
    state_query_command,
    white_command,
)
from .framing import Framer, Reassembler
from .products import Product, get_product
from .state import LightState, parse_notification_payload, parse_state

__all__ = [
    "CMD_CONTROL",
    "CMD_QUERY",
    "DeviceInfo",
    "Framer",
    "LightState",
    "Product",
    "Reassembler",
    "get_product",
    "hsv_command",
    "parse_advertisement",
    "parse_notification_payload",
    "parse_state",
    "power_command",
    "state_query_command",
    "white_command",
]

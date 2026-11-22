"""Device state parsing (wifibleCarrierWaveSymphony / V2 status content)."""

from __future__ import annotations

import json
from dataclasses import dataclass

POWER_ON = 0x23
V2_STATUS_HEAD = b"\xea\x81"
V2_HEAD_LEN = 6
MIN_STATE_LEN = 10


@dataclass(frozen=True)
class LightState:
    """Light state decoded from the 25-byte status content."""

    is_on: bool
    mode: int
    sub_mode: int
    hue: int
    saturation: int
    value: int
    white: int

    @property
    def is_white(self) -> bool:
        return self.white > 0


def parse_state(content: bytes) -> LightState | None:
    """Parse V2 status content (advertisement state or response payload after the head)."""
    if len(content) < MIN_STATE_LEN:
        return None
    return LightState(
        is_on=content[0] == POWER_ON,
        mode=content[1],
        sub_mode=content[2],
        hue=(content[5] << 1) | (content[6] >> 7),
        saturation=content[6] & 0x7F,
        value=min(content[7], 100),
        white=min(content[9], 100),
    )


def parse_notification_payload(payload: bytes) -> LightState | None:
    """Parse a state query response / pushed update.

    Payload is JSON {"code":0,"payload":"EA81....<content>"}; raw status bytes are also accepted.
    """
    raw: bytes = payload
    if payload[:1] == b"{":
        try:
            msg = json.loads(payload)
            if msg.get("code", 0) != 0:
                return None
            raw = bytes.fromhex(msg["payload"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return None
    if raw[:2] == V2_STATUS_HEAD:
        raw = raw[V2_HEAD_LEN:]
    return parse_state(raw)

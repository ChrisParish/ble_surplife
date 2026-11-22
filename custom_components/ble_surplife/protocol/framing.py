"""Transport framing ("ZG BLE" lower transport layer).

Mirrors com.zengge.hagallbjarkan.protocol.zgble.LowerTransportLayerEncoder/Decoder.
"""

from __future__ import annotations

from dataclasses import dataclass

CTRL_SEGMENTED = 0x40
CTRL_PROTECT = 0x20
CTRL_ACK = 0x10
LAST_SEGMENT = 0x8000

# Notification type in ctrl bits 2-3.
TYPE_JSON = 0
TYPE_HEX = 1
TYPE_ACK = 2


def write_version(ble_version: int) -> int:
    """Header version used for a device (ZGHBWriteUtils.getWriteVersion)."""
    return 1 if ble_version >= 8 else 0


def max_frame_length(mtu: int, version: int) -> int:
    """Largest frame for a negotiated ATT MTU (app uses mtu - 4)."""
    return min(mtu - 4, 512 if version == 1 else 255)


@dataclass(frozen=True)
class Message:
    """A reassembled application message."""

    cmd_id: int
    seq: int
    payload: bytes
    msg_type: int
    protect: bool
    ack: bool


class Framer:
    """Builds outgoing frames and tracks the per-device sequence number."""

    def __init__(self, version: int = 0) -> None:
        self.version = version
        self._seq = 0

    def next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def frames(self, cmd_id: int, payload: bytes, max_len: int = 240, protect: bool = False) -> list[bytes]:
        """Split a payload into one or more frames."""
        seq = self.next_seq()
        ctrl = (CTRL_PROTECT if protect else 0) | self.version
        if self.version == 1:
            return _frames_v1(ctrl, seq, cmd_id, payload, max_len)
        return _frames_v0(ctrl, seq, cmd_id, payload, max_len)


def _frames_v0(ctrl: int, seq: int, cmd_id: int, payload: bytes, max_len: int) -> list[bytes]:
    n = len(payload)
    if n <= max_len - 8:
        return [bytes([ctrl, seq, 0x80, 0x00, n >> 8, n & 0xFF, n + 1, cmd_id]) + payload]
    first = max_len - 8
    out = [bytes([ctrl | CTRL_SEGMENTED, seq, 0, 0, n >> 8, n & 0xFF, first + 1, cmd_id]) + payload[:first]]
    pos, idx = first, 1
    while pos < n:
        chunk = payload[pos : pos + max_len - 5]
        pos += len(chunk)
        seg = idx | (LAST_SEGMENT if pos >= n else 0)
        out.append(bytes([ctrl | CTRL_SEGMENTED, seq, seg >> 8, seg & 0xFF, len(chunk)]) + chunk)
        idx += 1
    return out


def _frames_v1(ctrl: int, seq: int, cmd_id: int, payload: bytes, max_len: int) -> list[bytes]:
    n = len(payload)
    if n <= max_len - 9:
        m = n + 1
        return [bytes([ctrl, seq, 0x80, 0x00, n >> 8, n & 0xFF, m >> 8, m & 0xFF, cmd_id]) + payload]
    first = max_len - 9
    m = first + 1
    out = [bytes([ctrl | CTRL_SEGMENTED, seq, 0, 0, n >> 8, n & 0xFF, m >> 8, m & 0xFF, cmd_id]) + payload[:first]]
    pos, idx = first, 1
    while pos < n:
        chunk = payload[pos : pos + max_len - 6]
        pos += len(chunk)
        seg = idx | (LAST_SEGMENT if pos >= n else 0)
        c = len(chunk)
        out.append(bytes([ctrl | CTRL_SEGMENTED, seq, seg >> 8, seg & 0xFF, c >> 8, c & 0xFF]) + chunk)
        idx += 1
    return out


class Reassembler:
    """Reassembles notification frames into messages (both header versions)."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._buf: bytearray | None = None
        self._total = 0
        self._seq = -1
        self._cmd = -1
        self._prev_seg = -1

    def feed(self, data: bytes) -> Message | None:
        """Feed one notification; returns a Message when complete."""
        if not data:
            return None
        ctrl = data[0]
        v1 = ctrl & 0x03 == 1
        hdr = 9 if v1 else 8
        if not ctrl & CTRL_SEGMENTED:
            if len(data) < hdr or (data[2] << 8 | data[3]) != LAST_SEGMENT:
                return None
            total = data[4] << 8 | data[5]
            self._reset()
            return self._message(ctrl, data[1], data[hdr - 1], bytes(data[hdr : hdr + total]))

        seg = (data[2] << 8 | data[3]) & 0x7FFF
        if seg == 0:
            if len(data) < hdr:
                self._reset()
                return None
            self._reset()
            self._seq = data[1]
            self._total = data[4] << 8 | data[5]
            self._cmd = data[hdr - 1]
            self._buf = bytearray(data[hdr:])
            self._prev_seg = 0
            return None

        if self._buf is None or data[1] != self._seq or seg != self._prev_seg + 1:
            self._reset()
            return None
        if v1:
            length = data[4] << 8 | data[5]
            chunk = data[6 : 6 + length]
        else:
            length = data[4]
            chunk = data[5 : 5 + length]
        self._buf += chunk
        self._prev_seg = seg
        if data[2] & 0x80:
            payload = bytes(self._buf[: self._total])
            seq, cmd = self._seq, self._cmd
            self._reset()
            return self._message(ctrl, seq, cmd, payload)
        return None

    @staticmethod
    def _message(ctrl: int, seq: int, cmd_id: int, payload: bytes) -> Message:
        return Message(
            cmd_id=cmd_id,
            seq=seq,
            payload=payload,
            msg_type=(ctrl & 0x0C) >> 2,
            protect=bool(ctrl & CTRL_PROTECT),
            ack=bool(ctrl & CTRL_ACK),
        )

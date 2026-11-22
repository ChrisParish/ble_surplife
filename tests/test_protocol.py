"""Protocol tests using frames captured from a real device."""

from custom_components.ble_surplife.protocol import (
    CMD_CONTROL,
    CMD_QUERY,
    Framer,
    Reassembler,
    get_product,
    hsv_command,
    parse_advertisement,
    parse_notification_payload,
    parse_state,
    power_command,
    state_query_command,
    white_command,
)

from . import MANUFACTURER_DATA, SERVICE_DATA

STATE_JSON = b'{"code":0,"payload":"EA810000C507232401500004646400000000960000000109010096"}'


def test_commands_match_captures() -> None:
    assert power_command(False).hex(" ") == "3b 24 00 00 00 00 00 00 00 00 00 00 5f"
    assert power_command(True).hex(" ") == "3b 23 00 00 00 00 00 00 00 00 00 00 5e"
    assert hsv_command(0, 100, 100).hex(" ") == "3b a1 00 64 64 00 00 00 00 00 00 00 a4"
    assert hsv_command(120, 100, 100).hex(" ") == "3b a1 3c 64 64 00 00 00 00 00 00 00 e0"
    assert hsv_command(240, 100, 20).hex(" ") == "3b a1 78 64 14 00 00 00 00 00 00 00 cc"
    assert white_command(100).hex(" ") == "3b 01 00 00 64 00 64 00 00 00 00 00 04"
    assert state_query_command().hex(" ") == "81 8a 8b 96"


def test_single_frame_v0() -> None:
    framer = Framer(version=0)
    assert framer.frames(CMD_QUERY, state_query_command())[0].hex(" ") == "00 01 80 00 00 04 05 0a 81 8a 8b 96"
    assert framer.frames(CMD_CONTROL, power_command(False))[0].hex(" ") == (
        "00 02 80 00 00 0d 0e 0b 3b 24 00 00 00 00 00 00 00 00 00 00 5f"
    )


def test_segmented_round_trip_v0_and_v1() -> None:
    payload = bytes(range(256)) * 4 + b"tail"
    for version, max_len in ((0, 240), (1, 509), (0, 19)):
        frames = Framer(version=version).frames(CMD_CONTROL, payload, max_len=max_len)
        assert len(frames) > 1
        assert all(len(f) <= max_len for f in frames)
        reassembler = Reassembler()
        results = [reassembler.feed(f) for f in frames]
        assert results[:-1] == [None] * (len(frames) - 1)
        assert results[-1].payload == payload
        assert results[-1].cmd_id == CMD_CONTROL


def test_reassemble_captured_notification() -> None:
    frame = bytes.fromhex("04188000004d4e0a") + STATE_JSON
    message = Reassembler().feed(frame)
    assert message is not None
    assert message.cmd_id == 0x0A
    assert message.payload == STATE_JSON


def test_parse_notification_state() -> None:
    state = parse_notification_payload(STATE_JSON)
    assert state is not None
    assert state.is_on
    assert (state.hue, state.saturation, state.value, state.white) == (8, 100, 100, 0)
    assert not state.is_white


def test_parse_white_state() -> None:
    state = parse_state(bytes.fromhex("23241400000000640064000000960000000109010096000000"))
    assert state is not None
    assert state.is_white
    assert state.white == 100


def test_parse_off_state() -> None:
    payload = STATE_JSON.replace(b"C507232401", b"C507242401")
    state = parse_notification_payload(payload)
    assert state is not None
    assert not state.is_on


def test_parse_advertisement() -> None:
    info = parse_advertisement(MANUFACTURER_DATA, SERVICE_DATA)
    assert info is not None
    assert info.mac == "E4:98:BB:B3:9B:B0"
    assert info.manufacturer == 0x5A5B
    assert info.ble_version == 7
    assert info.product_id == 0x00C5
    assert info.firmware_version == 44
    assert info.led_version == 7
    assert not info.requires_auth
    assert len(info.state) == 25
    state = parse_state(info.state)
    assert state is not None and state.is_on and state.hue == 8
    assert get_product(info.product_id) is not None


def test_parse_advertisement_rejects_other_devices() -> None:
    assert parse_advertisement({0x004C: b"\x12\x02\x6c\x01"}, {}) is None
    assert parse_advertisement({}, {}) is None

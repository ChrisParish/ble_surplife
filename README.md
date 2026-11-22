# Surplife BLE for Home Assistant

Local Bluetooth control of LED lights used with the **Surplife** app (Zengge / MagicHome 2 platform), no cloud required.

## Supported devices

| Advertised name | Product ID | Status |
|---|---|---|
| `IOTBT…` | `0x00C5` (symphony light strip) | Verified |

Other Surplife/Zengge Bluetooth lights are detected but rejected until they have been tested. Devices that require an encrypted connection (manufacturer ID `0x5Dxx`) are not supported yet.

## Features

- On / off
- Colour (hue / saturation) with brightness
- White mode with brightness
- Instant state updates (from advertisements and device notifications, no polling)
- Works with ESPHome Bluetooth proxies

Effects and scenes are planned.

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/ChrisParish/ble_surplife` as type **Integration**.
2. Install **Surplife BLE** and restart Home Assistant.
3. Lights are discovered automatically; or add them via **Settings → Devices & services → Add integration → Surplife BLE**.

Close the Surplife app on your phone first; the light accepts only one Bluetooth connection at a time. The integration disconnects after 90 seconds of inactivity.

## Helping add devices

Open an issue with the device name, the product ID shown on the device page (or in the debug log), and what the light does with each command.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

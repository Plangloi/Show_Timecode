# Show_Timecode
Show time code tracking

# qsys_tc_relay.py — Timecode WebSocket Relay

Bridges **MIDI Time Code (MTC)**, **Q-SYS QRC**, or a **free-run generator** to any number of WebSocket clients (browsers, OSC bridges, etc.).  
Used as the TC source backend for `timecode_cue_sheet.html`.

---

## Requirements

```bash
pip install websockets          # all modes
pip install python-rtmidi       # MTC mode only
```

> **Raspberry Pi / Debian:** add `--break-system-packages` if using system Python.

```bash
pip install websockets python-rtmidi --break-system-packages
```

---

## Modes

### 1. MTC — MIDI Time Code (hardware source)

Decodes MTC quarter-frames and full-frame SysEx from any MIDI input.  
Framerate (24 / 25 / 29.97DF / 30) is **auto-detected** from the MTC stream.

```bash
python3 qsys_tc_relay.py --mtc "MOTU"
```

`--mtc` accepts a **substring** of the MIDI port name (case-insensitive).  
To list available MIDI ports without starting the relay:

```bash
python3 - <<'EOF'
import rtmidi
m = rtmidi.MidiIn()
print(m.get_ports())
EOF
```

**Quarter-frame note:** MTC encodes TC across 8 QF messages spanning 2 frames.  
The relay applies the standard **+2 frame latency compensation** so the displayed TC matches the actual playhead position.

---

### 2. QRC — Q-SYS Core (network source)

Polls a Named Component control on the Q-SYS Core via JSON-RPC 2.0 over TCP (QRC protocol, port 1710). The control must expose the timecode as a string in `HH:MM:SS:FF` format.

```bash
python3 qsys_tc_relay.py \
  --core 192.168.10.10 \
  --component LTC_Reader \
  --control timecode
```

| Argument | Default | Description |
|---|---|---|
| `--core` | required | Q-SYS Core IP address |
| `--port` | `1710` | QRC TCP port |
| `--component` | `LTC_Reader` | Named Component in your design |
| `--control` | `timecode` | Control name exposing TC string |
| `--rate` | `0.1` | Poll interval in seconds (10 Hz) |

**Q-SYS design requirements:**
- A Named Component (LTC Reader, Media Player, or Lua script) that exposes a string control with value `HH:MM:SS:FF`
- QRC access enabled on the Core (default port 1710)
- A NoOp keepalive is sent every 30s automatically — QRC drops the connection after 60s of inactivity

**Example Lua snippet** to expose a TC string from an LTC Reader:

```lua
-- In a Q-SYS Lua script block, Named Component: "LTC_Reader"
-- Control: "timecode" (Text, read-only)
function GetTC()
  local tc = Controls["timecode"]
  -- format from LTC Reader position control
  local s = Controls["position"].Value
  local h = math.floor(s / 3600)
  local m = math.floor((s % 3600) / 60)
  local f = math.floor((s % 1) * 30)
  s = math.floor(s % 60)
  Controls["timecode"].String = string.format("%02d:%02d:%02d:%02d", h, m, f, s)
end
```

---

### 3. Fake — Free-run generator (no hardware needed)

Generates TC from a given start point, incrementing in real time. Useful for testing the cue sheet without any MIDI or Q-SYS hardware.

```bash
python3 qsys_tc_relay.py --fake 01:00:00:00
python3 qsys_tc_relay.py --fake 00:59:50:00 --fps 25
```

| Argument | Default | Description |
|---|---|---|
| `--fake` | — | Start TC `HH:MM:SS:FF` |
| `--fps` | `30` | Framerate for the generator |

The generator broadcasts at **10 Hz** — sufficient for smooth UI updates.

---

## WebSocket output

All modes broadcast to `ws://0.0.0.0:<ws-port>` (default **8765**).

**Message format:** plain JSON, one per frame update:
```json
{"tc": "01:00:23:14"}
```

The cue sheet HTML accepts both plain `"HH:MM:SS:FF"` strings and the JSON wrapper.  
Any other client (Node, Max/MSP, TouchOSC, etc.) can consume the same stream.

| Argument | Default | Description |
|---|---|---|
| `--ws-port` | `8765` | WebSocket server port |

**Multiple clients** are supported simultaneously — the relay broadcasts to all connected sockets concurrently.

---

## Connecting the cue sheet

In `timecode_cue_sheet.html`:

1. Chase bar → **Source: WebSocket**
2. Enter `ws://<Pi IP>:8765`
3. Click **Connect**
4. TC display turns **blue** when the WS feed is active

> If the relay is running on the same machine as the browser, use `ws://localhost:8765`.

---

## Running as a systemd service (Raspberry Pi / Linux)

```bash
sudo tee /etc/systemd/system/tc-relay.service << 'EOF'
[Unit]
Description=Timecode WebSocket Relay
After=network.target

[Service]
WorkingDirectory=/var/www/showcontrol
ExecStart=/usr/bin/python3 /var/www/showcontrol/qsys_tc_relay.py --mtc "MOTU" --ws-port 8765
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now tc-relay

# check status
sudo systemctl status tc-relay
journalctl -u tc-relay -f
```

Change `--mtc "MOTU"` to `--core 192.168.x.x` or `--fake 01:00:00:00` as needed.

---

## Quick reference

| Mode | Command |
|---|---|
| MTC from MOTU interface | `python3 qsys_tc_relay.py --mtc "MOTU"` |
| MTC, custom WS port | `python3 qsys_tc_relay.py --mtc "USB MIDI" --ws-port 9000` |
| Q-SYS Core | `python3 qsys_tc_relay.py --core 192.168.10.10 --component LTC_Reader --control timecode` |
| Q-SYS, faster poll | `python3 qsys_tc_relay.py --core 192.168.10.10 --rate 0.04` |
| Free-run from 1h | `python3 qsys_tc_relay.py --fake 01:00:00:00` |
| Free-run, 25fps | `python3 qsys_tc_relay.py --fake 00:59:50:00 --fps 25` |

---

## Troubleshooting

**`No module named rtmidi`**
```bash
pip install python-rtmidi --break-system-packages
```

**MIDI port not found**
```bash
python3 -c "import rtmidi; print(rtmidi.MidiIn().get_ports())"
# use a substring of the printed port name in --mtc
```

**Browser says WS connection refused**
- Confirm the relay is running: `sudo systemctl status tc-relay`
- Confirm the port is open: `ss -tlnp | grep 8765`
- Confirm no firewall blocking: `sudo ufw allow 8765/tcp`

**TC displayed but frozen in browser**
- MTC source stopped sending — relay freewheels for 2s then freezes
- Check MIDI cable / interface driver
- Check `journalctl -u tc-relay -f` for reconnect attempts

**Q-SYS connection drops every ~60s**
- Confirm NoOp keepalive is reaching the Core (firewall between relay and Core?)
- Verify QRC is enabled on the Core: Designer → File → Settings → Network → Enable External Control

**Web MIDI (in-browser MTC) not working on LAN**
- Chrome requires a **secure context** for Web MIDI (`https://` or `localhost`)
- On plain `http://192.168.x.x`, use the relay instead — connect via WebSocket source in the cue sheet

---

## Architecture summary

```
MTC hardware ──USB/DIN──▶ python-rtmidi
Q-SYS Core   ──TCP:1710──▶ QRC JSON-RPC   ──▶ asyncio broadcast ──▶ ws://host:8765
Free-run generator                                                        │
                                                                ┌─────────┼─────────┐
                                                           Browser 1  Browser 2  Browser N
                                                        (cue sheet HTML, any device on LAN)
```

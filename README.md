# 🎬 Show_Timecode

A **timecode-driven cue sheet for live shows.** Open `timecode_cue_sheet_4.html` in any browser and it shows a big running Show TC clock, the current and next cues, and a full editable cue table. Feed it real timecode — from Horae, a TimeCore, a MIDI interface, or the built-in test generator — and each cue lights up **🟢 Running** automatically the moment its time arrives.

Everything lives in **two small pieces**:

| Piece | What it is | What it does |
|---|---|---|
| `timecode_cue_sheet_4.html` | A single self-contained web page | The cue sheet UI — the table, clocks, markers, filters, import/export |
| `tc_relay.py` | A small Python script | Bridges MIDI/network timecode (or a fake generator) to the browser over WebSocket |

Multiple laptops/tablets on the same WiFi can open the same sheet and stay **live-synced** — edits, status, and markers appear on every screen at once.

## Contents

- [🎬 Quick Start — Running the Show](#-quick-start--running-the-show-zero-tech-experience-needed) — step-by-step for show operators, no tech experience needed
- [🆘 Something's not working?](#-somethings-not-working) — quick fixes during a show
- [Editing the cue sheet](#editing-the-cue-sheet) — adding cues, live sync, status, markers
- [tc_relay.py — Timecode WebSocket Relay](#tc_relaypy--timecode-websocket-relay) — the timecode backend, its modes and options
- [Docker](#docker) / [systemd](#running-as-a-systemd-service-raspberry-pi--linux) — deployment
- [Troubleshooting](#troubleshooting) & [Architecture](#architecture-summary)

---

# 🎬 Quick Start — Running the Show (Zero Tech Experience Needed)

This section is for anyone running the cue sheet who's never touched Docker, Terminal, or MIDI before. Just follow the steps in order, top to bottom. 🙂

> 💡 This walkthrough assumes the show computer is already set up the way iPat configured it (Horae routed to IAC, the auto-start relay service installed). You're just turning things on, not building them.

## ✅ Before the show — one-time checklist

- [ ] 🐳 **Docker Desktop** is installed on this Mac
- [ ] 🎼 **Horae** is installed
- [ ] ⚙️ The **auto-start relay service** has been set up once by iPat (you won't need to touch Terminal for this — it starts itself)

If all three are already true, skip straight to "Show day" below. 👇

---

## 🎭 Show Day — Step by Step

### 1️⃣ Start Docker Desktop

Click the Docker whale icon 🐳 in your Applications folder (or menu bar if it's already running). Wait until the icon in the top menu bar stops animating — that means it's ready.

### 2️⃣ Start the cue sheet website

Open **Terminal**, paste this one line, press Enter:

```bash
cd ~/Documents/Git/Show_Timecode && docker compose up -d cuesheet
```

> ⚠️ Only start `cuesheet` here — **not** `relay`. The timecode relay for this show runs a different way (see step 3), and starting both at once will fight over the same connection.

### 3️⃣ Open Horae and get it talking

1. Open **Horae** 🎼
2. Make sure **`IAC Driver Bus 1`** has a ✅ checkmark in the MTC Destination list on the right
3. Press ▶️ **Play** on the timecode generator

### 4️⃣ Check the relay is running

It should already be running quietly in the background (it auto-starts when you log in). To double check:

```bash
launchctl list | grep tc-relay
```

If you see a line printed back, ✅ you're good — skip to step 5.

If you see **nothing printed**, start it manually:

```bash
cd ~/Documents/Git/Show_Timecode
uv run --with websockets --with python-rtmidi python3 tc_relay.py --mtc "IAC"
```

Leave that Terminal window open in the background while the show runs.

### 5️⃣ Open the cue sheet

In your web browser, go to:

```
http://localhost:8080
```

*(Someone viewing from a different laptop/tablet on the same WiFi? Use the show computer's network address instead of `localhost` — ask iPat for that number if you don't have it.)*

### 6️⃣ Connect it to the timecode

At the top of the cue sheet, in the **Chase** bar:

1. Find the **Source** dropdown → choose **WebSocket**
2. In the box that appears, type: `ws://localhost:8765`
3. Click **Connect**

### 7️⃣ You're live! 🎉

- The big clock at the top should turn **🔵 blue** and start counting, matching Horae's numbers
- As each cue's moment arrives, its **Status** turns **🟢 green "Running"** automatically, then back to **🟡 Standby** when it's done

That's it — you're ready for the show. 🎬✨

---

## 🆘 Something's not working?

| What you see | What it means | What to do |
|---|---|---|
| Cue sheet page won't load at all | Docker isn't running | Go back to Step 1 🐳 |
| Clock stays gray, says `--:--:--:--` | Not connected yet | Redo Step 6 — check you typed `ws://localhost:8765` exactly |
| Clock is blue but numbers aren't moving | Horae isn't sending timecode | In Horae: is ▶️ Play actually pressed? Is `IAC Driver Bus 1` checked? |
| `launchctl list \| grep tc-relay` shows nothing, and manual start doesn't help either | Ask iPat — this needs the one-time setup checked | 📞 |
| Cues never turn green even though the clock is moving | Wrong Act selected | Check the **Act** dropdown next to the ▶️ START button matches the act actually playing |

When in doubt: close the browser tab, reopen `http://localhost:8080`, and redo Steps 5–6. That fixes almost everything. 🔄

---

# tc_relay.py — Timecode WebSocket Relay

Bridges **MIDI Time Code (MTC)** — local, virtual bus, or network (RTP-MIDI) — or a **free-run generator** to any number of WebSocket clients (browsers, OSC bridges, etc.).  
Used as the TC source backend for `timecode_cue_sheet_4.html`.

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

### 1. MTC — MIDI Time Code (local, virtual bus, or network)

Decodes MTC quarter-frames and full-frame SysEx from any MIDI input.  
Framerate (24 / 25 / 29.97DF / 30) is **auto-detected** from the MTC stream.

```bash
python3 tc_relay.py --mtc "MOTU"
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

**MTC over the network (Horae / Visual Productions TimeCore):**  
`tc_relay.py` only ever talks to a named MIDI port — it doesn't care whether that port is local hardware, a virtual bus (IAC), or a network session. To get MTC across the network:

1. Have Horae or a [TimeCore](https://www.visualproductions.nl/products/timecore) send **RTP-MIDI (AppleMIDI)** on the network — TimeCore supports RTP-MIDI natively; in Horae, add an RTP-MIDI destination alongside (or instead of) IAC.
2. Join that RTP-MIDI session at the OS level on the machine running the relay:
   - **macOS:** Audio MIDI Setup → Window → MIDI Studio → *MIDI Network Setup* → connect to the session.
   - **Linux:** `rtpmidid` creates a matching ALSA MIDI port for any RTP-MIDI session it discovers/joins on the network.
   - **Windows:** install the Tobias Erichsen `rtpMIDI` driver and add the session there.
3. Once joined, the session shows up as a normal MIDI port — point `--mtc` at a substring of its name, same as any local port:

```bash
python3 tc_relay.py --mtc "TimeCore"
```

---

### 2. Fake — Free-run generator (no hardware needed)

Generates TC from a given start point, incrementing in real time. Useful for testing the cue sheet without any MIDI hardware or network session.

```bash
python3 tc_relay.py --fake 01:00:00:00
python3 tc_relay.py --fake 00:59:50:00 --fps 25
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

In `timecode_cue_sheet_4.html`:

1. Chase bar → **Source: WebSocket**
2. Enter `ws://<Pi IP>:8765`
3. Click **Connect**
4. TC display turns **blue** when the WS feed is active

> If the relay is running on the same machine as the browser, use `ws://localhost:8765`.

---

## Editing the cue sheet

Everything's editable directly in the table — no re-import needed:

- **Add a cue** — toolbar **＋ Add Cue** (appends to the current/default act), or hover any row and click its **＋** to insert right after it.
- **Delete a cue** — hover a row, click **✕** (confirms first).
- **Rename / edit fields** — click into Cue#, Label/Scene, Trigger, Dept, Device, Action, Fade, or Notes and type. Commits on blur or Enter.
- **Edit Duration** — click the Dur cell, type `HH:MM:SS:FF`. TC In/Out for every following cue ripples forward automatically — same mechanism as drag-reordering.
- All of the above feed the existing **⎌ Undo** button and autosave (localStorage), so none of this is riskier than a drag-reorder.

**Live sync across hosts** — any edit (rename, add/delete/reorder, status, notes, meta fields, TC color) is pushed to every other browser connected via **Source: WebSocket** to the same relay, over that same connection — no separate setup. A browser that joins later gets the current cue sheet immediately (the relay caches the latest snapshot for new connections). The one thing that's deliberately *not* synced is the transient "Running" highlight — each host computes that itself from the shared TC feed, so it stays consistent without fighting over the wire. Hosts using **MTC (Web MIDI)** as their TC source instead of WebSocket aren't on this channel and won't send or receive edits.

**Status** — a dropdown per cue: Standby / Ready / Running / Hold / Done / Cut. While a cue is the one currently under the TC playhead, its Status is **automatically forced to "Running"** (green, pulsing) — this overwrites whatever was set manually. The instant that cue's TC window ends, it reverts to **"Standby"** (not whatever it was before — a cue left on "Hold" or "Cut" will read "Standby" after the playhead passes through it). Driven purely by the chase engine, so it behaves the same regardless of TC source (Manual / WebSocket / MTC).

**Live scene markers** — capture the current live timecode into a named list on the fly, handy for spotting where a moment actually landed during a run.

- **Capture** — click **⚑ MARK** (top, next to the big Show TC), or just tap the **Spacebar** (as long as you're not typing in a field). The marker is stamped with the current live TC and auto-named after the cue that's running at that instant (or "Marker N" if none is).
- **Rename** — click a marker's name and type; commits on blur or Enter.
- **Jump** — click a marker's TC to drop that time into the Chase **TC input** box, ready to Start from there.
- **Remove** — click the **✕** next to a marker.
- Markers autosave and are **live-synced** across all WebSocket-connected hosts, exactly like cue edits. Capturing needs a live TC — start the chase or connect a source first, otherwise you'll get a "No live TC" notice.

---

## Docker

`Dockerfile` + `docker-compose.yml` run the relay and the cue sheet as two containers — `relay` (the WS relay, multi-stage build so the final image only carries the ALSA runtime lib, not the compiler) and `cuesheet` (nginx serving `timecode_cue_sheet_4.html` as a static site).

```bash
docker compose up -d --build
```

- Relay: `ws://<host>:8765` — defaults to the free-run generator from `01:00:00:00`, so it works out of the box with zero hardware/config, good for testing the cue sheet.
- Cue sheet UI: `http://<host>:8080`

**Changing ports** — both are env-var driven (`${RELAY_WS_PORT:-8765}` / `${CUESHEET_PORT:-8080}` in `docker-compose.yml`):

```bash
CUESHEET_PORT=9090 docker compose up -d          # one-off, this run only

cp .env.example .env                              # persistent — compose auto-reads .env
echo "CUESHEET_PORT=9090" >> .env
docker compose up -d

docker compose up -d --force-recreate cuesheet    # already running, just remap (no rebuild)
```

Recreating a container to change its published port is the ceiling of what Docker's port-publishing model allows — there's no true hot remap on a running container.

**Switching modes** — edit `command:` in `docker-compose.yml` for a persistent deployment:

```yaml
command: ["--mtc", "TimeCore"]
```

or override ad hoc without touching the file:

```bash
docker compose run --rm -p 8765:8765 relay --mtc "TimeCore"
```

then `docker compose up -d` to apply.

**Fake mode works anywhere** — generated data, no L2 or USB dependency, so default bridge networking is fine on any Docker host, including Docker Desktop on macOS.

**MTC mode needs Linux + USB/network MIDI passthrough** — MIDI access doesn't cross the Docker Desktop macOS VM boundary cleanly. On a Linux host, uncomment in `docker-compose.yml`:

```yaml
devices:
  - /dev/snd:/dev/snd
group_add:
  - audio
command: ["--mtc", "MOTU"]
```

That covers local/USB MIDI. For an **RTP-MIDI network session** (Horae or TimeCore), join the session with `rtpmidid` on the Linux host first (outside the container) — it creates a regular ALSA MIDI port, which then just needs the same `/dev/snd` passthrough to reach the container.

If the container still can't see the interface after that, `privileged: true` is the blunt fallback — wider blast radius, only reach for it if the device mapping + group approach doesn't resolve ALSA permissions. On macOS, run `tc_relay.py --mtc "..."` natively for MTC (see Requirements above) — Docker isn't the right tool for that mode there.

**vs. systemd** — for a dedicated always-on Pi doing MTC capture, the systemd unit below is still the better fit: direct hardware access, no container/USB passthrough fuss, `journalctl` for logs. Docker's the better fit for Fake mode, or when you want the relay + cue sheet reproducible/portable across machines.

## Running as a systemd service (Raspberry Pi / Linux)

```bash
sudo tee /etc/systemd/system/tc-relay.service << 'EOF'
[Unit]
Description=Timecode WebSocket Relay
After=network.target

[Service]
WorkingDirectory=/var/www/showcontrol
ExecStart=/usr/bin/python3 /var/www/showcontrol/tc_relay.py --mtc "MOTU" --ws-port 8765
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

Change `--mtc "MOTU"` to `--mtc "TimeCore"` (or whatever the RTP-MIDI session/port is named once joined) or `--fake 01:00:00:00` as needed.

---

## Quick reference

| Mode | Command |
|---|---|
| MTC from MOTU interface | `python3 tc_relay.py --mtc "MOTU"` |
| MTC over RTP-MIDI (Horae/TimeCore) | `python3 tc_relay.py --mtc "TimeCore"` |
| MTC, custom WS port | `python3 tc_relay.py --mtc "USB MIDI" --ws-port 9000` |
| Free-run from 1h | `python3 tc_relay.py --fake 01:00:00:00` |
| Free-run, 25fps | `python3 tc_relay.py --fake 00:59:50:00 --fps 25` |

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

**RTP-MIDI session (Horae/TimeCore) not showing up as a MIDI port**
- The relay never talks to the network directly — the OS must join the RTP-MIDI session first (Audio MIDI Setup on macOS, `rtpmidid` on Linux, the Tobias Erichsen driver on Windows)
- Once joined it appears in `rtmidi.MidiIn().get_ports()` like any other port — if it's not there, the session wasn't joined, not a relay problem

**Browser says WS connection refused**
- Confirm the relay is running: `sudo systemctl status tc-relay`
- Confirm the port is open: `ss -tlnp | grep 8765`
- Confirm no firewall blocking: `sudo ufw allow 8765/tcp`

**TC displayed but frozen in browser**
- MTC source stopped sending — relay freewheels for 2s then freezes
- Check MIDI cable / interface driver, or that Horae/TimeCore is still transmitting on the network session

**Web MIDI (in-browser MTC) not working on LAN**
- Chrome requires a **secure context** for Web MIDI (`https://` or `localhost`)
- On plain `http://192.168.x.x`, use the relay instead — connect via WebSocket source in the cue sheet

---

## Architecture summary

```
MTC hardware  ──USB/DIN───────▶ python-rtmidi
MTC network   ──RTP-MIDI──────▶ (OS joins session, appears as a MIDI port)
  (Horae / TimeCore)                          │
Free-run generator                            ▼
                                    asyncio broadcast ──▶ ws://host:8765
                                                                │
                                                     ┌──────────┼──────────┐
                                                Browser 1   Browser 2   Browser N
                                              (cue sheet HTML, any device on LAN)
```

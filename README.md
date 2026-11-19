# Show_Timecode
A cue sheet web page that runs the show clock and sends it to the DOREMiDi MTC-30 (Art-Net timecode) and QLab (OSC).

---

# 🎬 Quick Start — Running the Show (no tech experience needed)

Follow the steps **in order, top to bottom**. Every command is something you copy, paste into **Terminal**, and press **Enter**. 🙂

> 🖥️ **What's Terminal?** An app on every Mac. Press **⌘ + Space**, type `Terminal`, press **Enter**. A window with text opens — that's where you paste commands.

## 🧠 What is all this? (30-second version)

```
                 ┌──────────────────────────────┐
  You press ▶    │  Cue sheet  (web page)       │   http://localhost:8085
  in the browser │  the show's master clock     │
                 └──────────────┬───────────────┘
                                │
                 ┌──────────────▼───────────────┐
                 │  Relay  (tc_relay.py)        │   runs in a Terminal window
                 └──┬─────────────┬──────────┬──┘
                    │             │          │
        Art-Net timecode    OSC "start cue"   OSC remote control (in)
                    ▼             ▼          ▲
           ┌──────────────┐ ┌──────────┐ ┌────────────────────────┐
           │    MTC-30    │ │   QLab   │ │ QLab / Companion / etc │
           │ 10.10.11.226 │ │ this Mac │ │ → /play /stop /next    │
           └──────────────┘ └──────────┘ └────────────────────────┘
```

- **Cue sheet** — the web page with the big clock and the list of cues.
- **Relay** — a small program that takes the clock from the cue sheet and sends it out to the gear.
- **MTC-30** — the DOREMiDi timecode box at `10.10.11.226`. It follows the cue sheet's clock (Art-Net timecode). If its Art-Net output is on, the big clock shows the box's own time.
- **QLab** — when the clock reaches a cue, QLab gets told to **start the cue with the same number**.

---

## ✅ One-time setup (only the very first time on a new Mac)

Skip this whole section if the show Mac is already set up.

1. **Install Docker Desktop** 🐳 — download from <https://www.docker.com/products/docker-desktop/>, open it once, accept the defaults.
2. **Install uv** (runs the relay — no Python setup needed). In Terminal:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Then **close Terminal and open it again**.
3. **Get the project** (skip if `~/Documents/Git/Show_Timecode` already exists):
   ```bash
   mkdir -p ~/Documents/Git && cd ~/Documents/Git && git clone https://github.com/Plangloi/Show_Timecode.git
   ```
   If the Mac asks to install "command line developer tools", click **Install**, wait, then run the line again.
4. **QLab** 🎼 — installed, and in your workspace: **Workspace Settings → Network → OSC access ON**. Number your QLab cues the **same as the Cue# column** in the cue sheet (e.g. `12`).
5. **Network** 🌐 — the Mac must be plugged into the show network (`10.10.11.x`). Check it can see the MTC-30:
   ```bash
   ping -c 3 10.10.11.226
   ```
   ✅ Lines with `time=… ms` = good. ❌ `Request timeout` = wrong network / cable.

---

## 🎭 Show Day — Step by Step

### 1️⃣ Start Docker Desktop 🐳

Open **Docker** from Applications. Wait until the whale icon in the top menu bar **stops moving**.

### 2️⃣ Start the cue sheet page

In Terminal, paste:

```bash
cd ~/Documents/Git/Show_Timecode && docker compose up -d --force-recreate cuesheet && docker stop tc-relay 2>/dev/null; echo READY
```

✅ You should see `READY` at the end.

> ⚠️ This starts **only the cue sheet page** (always the latest version of the file) and makes sure Docker's *test* clock is off — it would block the real relay in the next step.

### 3️⃣ Start the relay (leave this window open!)

In Terminal, paste:

```bash
cd ~/Documents/Git/Show_Timecode && uv run --with websockets python3 tc_relay.py --artnet-out 10.10.11.226 --artnet --artnet-src 10.10.11.226 --qlab 127.0.0.1 --osc-in 9000
```

✅ You should see something like:

```
[qlab] /cue/<cue#>/start → 127.0.0.1:53000
[ws] broadcasting on ws://0.0.0.0:8765
[tc-out] Art-Net 10.10.11.226 · OSC QLab 127.0.0.1:53000 — driven by the cue sheet's Manual transport
[osc-in] listening on udp/9000: ...
[artnet] listening on udp/6454 from 10.10.11.226
[artnet] Manual mode: incoming TC is shown on the page as the device's time ...
```

- 🔒 If the Mac pops up *"Do you want python to accept incoming connections?"* → click **Allow**.
- 🚫 **Do not close this window** during the show — closing it stops the timecode. Minimize it instead.

### 4️⃣ Set the MTC-30 and QLab

- **MTC-30:** set its timecode source to **Art-Net** (reader mode). *Optional:* also turn on its **Art-Net output** — then the big clock shows the box's own time, so you can see it really follows.
- **QLab:** open your show workspace.

### 5️⃣ Open the cue sheet

In Chrome or Safari go to: **<http://localhost:8085>**

### 6️⃣ Connect the cue sheet to the relay

In the **Chase** bar (just under the big clock):

1. **Source** dropdown → choose **Manual**
2. Next to it, the box should already say `ws://localhost:8765` — click **⇢ TC OUT**
3. ✅ The dot turns **🔵 blue** and a message says `TC OUT → Art-Net 10.10.11.226 · OSC QLab …`

### 7️⃣ Run the show 🎉

| To… | Do this |
|---|---|
| Choose the act | **Act** dropdown in the Chase bar |
| Start the clock | Type a start time (e.g. `00:56:00:00`) or leave empty for the act's start → **▶ START** |
| Pause | **❚❚ PAUSE** freezes the clock on that frame (the MTC-30 holds it, the cue stays green) · **▶ RESUME** carries on from there |
| Stop | **■ STOP** ends the run (the MTC-30 holds the last frame) |
| Small jump | **−1s / +1s** |
| Jump to a cue | Click the cue's row (with **✎ Edit: OFF**) — the clock jumps to that cue's start |
| Mark a moment | **⚑ MARK** (or **Space**) — saves the time in the marker list |
| Bigger / smaller clock | Drag the little bar under the big clock · double-click it to reset |

While it runs:
- The big clock counts **🟠 orange**, the **MTC-30** shows the same time.
- The small time just left of **▶ START** is always the cue sheet's own clock (what's being sent out).
- If the MTC-30 sends its time back, the big clock turns **🟢 green** and says **(MTC-30)** — that's the box's own time.
- The current cue turns **🟢 green "Running"**, and **QLab starts the cue with the same number**.
- **NOW** (left) and **NEXT in …** (right) show what's playing and what's coming.

### 8️⃣ After the show

- Click **■ STOP**.
- In the relay's Terminal window press **Ctrl + C** to stop it (or just close the window).
- The cue sheet page can stay running — it costs nothing.

---

## ✏️ Changing the cue sheet

- **✎ Edit** (toolbar) switches between:
  - **OFF** — safe for the show: nothing can be changed by accident, clicking a cue jumps the clock there.
  - **ON** — click any cell to type: Cue#, label, **TC In**, **TC Out**, **Dur**, notes… Press **Enter** to confirm. Times use `HH:MM:SS:FF` (hours:minutes:seconds:frames). Changing a time shifts all the cues after it.
- **⎌ Undo** — undoes the last change.
- **⚙** (top right) — **Import XLSX** / **Export XLSX** (save a copy to Excel) / **Clear saved** (⚠️ resets everything to the default sheet).
- Changes save automatically in the browser. Use **Export XLSX** to keep a real backup file.
- **QLab tip:** put an OSC command in a cue's **Action** column (e.g. `/cue/12/go`) to send that instead of "start".

---

## 📲 Phone view (follow the show + ⚑ MARK + notes)

Follow the show on your phone: big clock, **NOW / NEXT** with their notes, the **Cues** list (with notes) and the markers. Its only buttons are **⚑ MARK** and marker **notes** — nothing on it can play, stop or move the show, so it's safe to hand to anyone on the crew.

1. On the show Mac, the cue sheet must be on **Source → Manual** with **⇢ TC OUT** connected (steps 3️⃣ to 6️⃣).
2. Find the show Mac's address:
   ```bash
   ipconfig getifaddr en8 || ipconfig getifaddr en0
   ```
   (e.g. `10.10.11.209`)
3. On the phone (same network / Wi-Fi as the show Mac), open **`http://<that address>:8085/remote.html`**
4. A popup asks **Who's marking?** — type your name (e.g. `SM`, `LX`) → **Continue**. The phone remembers it; next time just tap **Continue**. Change it any time with the **Marking as … ✎** chip.
5. ✅ The pill at the top turns **🔵 blue** and the clock follows the show. Tip: *Share → Add to Home Screen* to open it like an app.

| Tab | Shows |
|---|---|
| **Show** | Big clock (🟢 playing · 🟠 paused · ⚪ stopped), NOW with progress + note, NEXT with countdown + note — **scroll down** for the markers, newest first, with their names (rename one on the Mac → it updates on the phone) and the **⚑ MARK** button |
| **Cues** | The current act's cues — running 🟢, next 🟠, done faded — with notes |

- **⚑ MARK** on the phone = ⚑ MARK on the Mac: the marker is taken at the show clock, named after the running cue, and shows on every screen. It only works while the clock is running or paused — otherwise the phone says *Not captured*.
- **Notes:** right after ⚑ MARK a sheet asks *add a note?* — type it → **Save note**, or **Skip** (the marker is already taken, typing never delays it). Tap any marker later to add or edit its note. Notes show on every phone and in the Mac's marker panel, where you can also edit them (click *add note…*).
- **Who made it:** the name from the popup. Every marker shows **by …** on the Mac and on the phones: your name, **Mac** for the Mac's own ⚑ MARK / Space, or **device 10.10.11.x** if the phone had no name set. The name is whatever people type — it's a label, not a login.
- Yellow message *"Waiting for the cue sheet"* → on the Mac click **⇢ TC OUT** (and check Source is **Manual**).
- The pill says *offline · retrying* → the relay isn't running (step 3️⃣) or the phone is on another network.
- To **control** the show from a phone or Stream Deck, use OSC (next sections) — e.g. TouchOSC / Companion.

---

## 📱 Other screens (iPad / another laptop)

1. On the show Mac, find its address:
   ```bash
   ipconfig getifaddr en0
   ```
   (e.g. `10.10.11.209`)
2. On the other device, open `http://<that address>:8085`
3. **Source → WebSocket**, type `ws://<that address>:8765`, **Connect** → it follows the show clock and shows the same cue sheet edits.

---

## 🕹️ Remote control from QLab / Companion / Stream Deck (optional)

Send OSC to the show Mac on port **9000** (the relay forwards it to the cue sheet — keep the cue sheet open on **Manual** with **⇢ TC OUT** connected):

| Send | Does |
|---|---|
| `/play` · `/stop` · `/toggle` | Start / stop the clock |
| `/pause` | Pause (hold the frame) · send again to resume |
| `/mark` · `/mark "LX"` | Capture a marker (same as ⚑ MARK) — the optional text is who made it |
| `/act 2` | Switch the Chase act |
| `/next` · `/prev` | Jump to next / previous cue |
| `/cue 12` | Jump to cue 12 |
| `/locate "01:00:00:00"` | Jump to a time |

In QLab: add a **Network** cue → destination = this Mac, port `9000` → message e.g. `/next`.

---

## 🎛️ Other option — the MTC-30 is the master clock (instead of the cue sheet)

Use this when the **MTC-30 generates** the timecode and the cue sheet (and QLab) just follow it.

1. Do steps 1️⃣ and 2️⃣ above.
2. On the **MTC-30**: set it to **generate** timecode and turn on **Art-Net output**.
3. Start the relay in Art-Net listen mode (instead of step 3️⃣):
   ```bash
   cd ~/Documents/Git/Show_Timecode && uv run --with websockets python3 tc_relay.py --artnet --artnet-src 10.10.11.226 --qlab 127.0.0.1
   ```
   ✅ When the MTC-30 runs you'll see `[artnet] timecode from 10.10.11.226 @ 30 fps`.
4. Cue sheet: **Source → WebSocket**, type `ws://localhost:8765`, **Connect**. The clock turns **🔵 blue** and follows the MTC-30. QLab still gets its cues.

> ⚠️ In this mode start/stop the clock **on the MTC-30**. Don't use **⇢ TC OUT** / Manual, and don't add `--artnet-out` — the Mac and the box would send timecode to each other.
>
> 🔌 **RTP-MIDI instead of Art-Net?** If your MTC-30 has RTP-MIDI: **Audio MIDI Setup → Window → Show MIDI Studio → Network**, create a session, connect it to the MTC-30, then run the relay with `uv run --with websockets --with python-rtmidi python3 tc_relay.py --mtc "Session 1" --qlab 127.0.0.1` (use your session's name).

**Back to normal (cue sheet is master):** stop the relay (**Ctrl + C**), set the MTC-30 back to **Art-Net in** (reader), then redo steps 3️⃣ and 6️⃣.

---

## 🎼 Other option — Horae is the master clock (instead of the cue sheet)

Use this only if **Horae** generates the timecode and the cue sheet just follows it.

1. Do steps 1️⃣ and 2️⃣ above.
2. In **Horae**: tick **`IAC Driver Bus 1`** in the MTC Destination list, press ▶️ **Play**.
3. Start the relay in MTC mode (instead of step 3️⃣):
   ```bash
   cd ~/Documents/Git/Show_Timecode && uv run --with websockets --with python-rtmidi python3 tc_relay.py --mtc "IAC" --qlab 127.0.0.1
   ```
4. Cue sheet: **Source → WebSocket**, type `ws://localhost:8765`, **Connect**. The clock turns **🔵 blue** and follows Horae.

---

## 🆘 Something's not working?

| What you see | Why | Fix |
|---|---|---|
| `localhost:8085` won't load | Docker isn't running | Step 1️⃣, then step 2️⃣ again |
| `localhost:8085` shows **404 Not Found** | The page file was replaced (update / edit) and Docker lost it | Step 2️⃣ again, then reload the page |
| Relay says `address already in use` | Docker's test clock is on, or a relay is already running in another window | `docker stop tc-relay`, close other relay windows, then step 3️⃣ again |
| `command not found: uv` | uv not installed, or Terminal not reopened | One-time setup step 2, then **reopen Terminal** |
| **⇢ TC OUT** says *relay unreachable* | Relay window closed / not started | Step 3️⃣ |
| Clock stays `--:--:--:--` | Clock not started | Press **▶ START** (Source must be **Manual**) |
| MTC-30 doesn't follow | Not on the network, not in Art-Net mode, or the box is stuck | `ping -c 3 10.10.11.226` · set MTC-30 source to **Art-Net** · check the TC OUT dot is 🔵 · still nothing? **Turn the MTC-30 off and on again** (fixes a stuck box) |
| QLab doesn't start cues | QLab closed, OSC off, or numbers don't match | QLab open · OSC access ON · QLab cue number = **Cue#** in the cue sheet |
| QLab cue fires but it's the wrong one | Cue numbers differ | Make QLab's cue number exactly the cue sheet's **Cue#** |
| Cues never turn green | Wrong Act selected | **Act** dropdown must match the act you're playing |
| Can't type in the table | Edit is off | Click **✎ Edit: OFF** → it becomes **ON** |
| Clicking a cue doesn't jump | Edit is on, or Source isn't Manual | Turn **✎ Edit** OFF · Source → **Manual** |
| Page looks old after an update | Docker is serving the old file | Step 2️⃣ again, then reload the page (**⌘ + R**) |
| Phone view stuck on *Waiting for the cue sheet* | The Mac's cue sheet isn't sending | On the Mac: **Source → Manual**, click **⇢ TC OUT** |
| Big clock never turns 🟢 green | The MTC-30 doesn't send Art-Net back | Normal — turn on the MTC-30's **Art-Net output** if you want to see its time. The show works either way |

**When in doubt:** reload the page (**⌘ + R**), choose **Source → Manual**, click **⇢ TC OUT**. That fixes almost everything. 🔄

---

# tc_relay.py — Timecode WebSocket Relay

Bridges **MIDI Time Code (MTC)** — local, virtual bus, or network (RTP-MIDI) — **Art-Net Timecode**, or a **free-run generator** to any number of WebSocket clients (browsers, etc.), and speaks **OSC** both ways (TC + cue fires out, remote transport in).  
Used as the TC source backend for `timecode_cue_sheet_4.html`.

---

## Requirements

```bash
pip install websockets          # all modes
pip install python-rtmidi       # MTC mode only (Art-Net needs nothing extra)
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

### 2. Art-Net Timecode — straight off the network (e.g. DOREMiDi MTC-30)

Listens for **ArtTimeCode** (OpCode `0x9700`) on UDP **6454**. No MIDI driver, no session to join — the sender broadcasts one packet per frame to the subnet, the relay just has to be on that subnet. Framerate (24 / 25 / 29.97DF / 30) comes from the packet.

```bash
python3 tc_relay.py --artnet
python3 tc_relay.py --artnet --artnet-src 10.10.11.226   # only this sender (others on the net are ignored)
```

On the **DOREMiDi Timecode Center (MTC-30)**, enable Art-Net TimeCode output — it broadcasts to the subnet (e.g. `10.10.11.255`). The relay logs `[artnet] timecode from <ip> @ <fps> fps` on the first packet, so you know it's hearing it.

- Port 6454 is opened with `SO_REUSEPORT`, so a lighting app on the same machine can still listen to Art-Net.
- The machine running the relay must be on the **same subnet** as the sender (broadcast doesn't cross routers).
- macOS may ask to allow incoming connections for Python the first time — click **Allow**.

---

### 3. Art-Net Timecode OUT — play back from the cue sheet (e.g. to an MTC-30)

The cue sheet's **Manual** transport (▶ START / ■ STOP / ±1s / typed start TC) drives an ArtTimeCode stream that the relay sends to the network, so a reader like the **MTC-30** chases the cue sheet instead of the other way round.

```bash
python3 tc_relay.py --artnet-out 10.10.11.255              # broadcast to the show subnet
python3 tc_relay.py --artnet-out 10.10.11.226              # or unicast to the MTC-30 only
python3 tc_relay.py --artnet-out 10.10.11.226 --artnet --artnet-src 10.10.11.226   # + show the MTC-30's own time
```

In the cue sheet:

1. **Source → Manual** — a **⇢ TC OUT** control appears next to it
2. Check the URL (pre-filled with `ws://<this page's host>:8765`) → click **⇢ TC OUT** (dot turns blue, toast shows the destination)
3. Type a start TC, hit **▶ START** — the relay sends one packet per frame (30 fps, same format as the MTC-30). **■ STOP** holds the last frame, **±1s** and a new start TC locate.

- The browser only sends transport changes; the **relay owns the frame clock**, so packets go out on time regardless of browser timer jitter.
- Nothing is sent until the page sends its first transport — starting the relay never pushes a stray `00:00:00:00`.
- On the MTC-30, set its timecode source to **Art-Net** (reader mode).
- If the relay was started without `--artnet-out` / `--osc-out` / `--osc-in`, the page shows *"relay not started with …"*.
- The same **⇢ TC OUT** connection also carries OSC OUT and OSC IN (see mode 4 below).
- Other screens on **Source → WebSocket** get the show clock straight from the relay (`{"tc": …}` every frame).
- With `--artnet` also on, Art-Net TC from another sender (e.g. the MTC-30's Art-Net output) goes to the page as `{"type": "device_tc"}` and shows in the big clock (🟢 *(MTC-30)*); the cue sheet stays the master. The relay ignores its own Art-Net coming back.
- **On macOS, run this natively, not in Docker** — and stop the Docker `tc-relay` container first (`docker stop tc-relay`), otherwise the native relay fails with `address already in use` on 8765.

---

### 4. OSC — timecode + cue fires OUT, remote transport IN

Plain UDP OSC 1.0, no extra Python packages. Combine freely with any other mode.

```bash
python3 tc_relay.py --artnet-out 10.10.11.226 --osc-out 10.10.11.50:53000      # MTC-30 + OSC to one target
python3 tc_relay.py --mtc "IAC" --osc-out 10.10.11.50:53000 --osc-out 127.0.0.1:9001   # several targets
python3 tc_relay.py --artnet-out 10.10.11.226 --osc-in 9000                    # remote control on udp/9000
```

**OSC OUT — timecode** (`--osc-out IP:PORT`, repeatable)
- `/tc "HH:MM:SS:FF"` once per new frame, from whatever is driving: MTC / Art-Net IN / fake, or the cue sheet's Manual transport via **⇢ TC OUT**.
- Change the address with `--osc-tc-addr /show/tc`.

**OSC OUT — cue fires** (same targets)
- When a cue goes live *while TC is rolling into it*, the cue sheet asks the relay to fire it. Not fired: connecting mid-cue, or locating while stopped. Several open browsers fire a cue only once (the relay de-dupes).
- If the cue's **Action** column starts with `/`, it is sent as-is: `/cue/12/go`, `/exec/1/5 1`, `/scene "Intro"` (numbers become int/float, quotes group words).
- Otherwise it sends `/cue/go "<cue#>" "<label>" "<dept>" "<device>" "<action>"`.
- A page fires only if it's connected to the relay: **Source → WebSocket**, or **Manual** with **⇢ TC OUT** connected.

**QLab** (`--qlab IP[:PORT]`, port 53000 default, repeatable)

```bash
python3 tc_relay.py --artnet-out 10.10.11.226 --qlab 127.0.0.1                  # QLab on this Mac
python3 tc_relay.py --artnet-out 10.10.11.226 --qlab 10.10.11.40 --qlab-pass 1234   # QLab elsewhere, with OSC passcode
```

- When a cue goes live, QLab gets **`/cue/<cue#>/start`**. Number the QLab cues the same as the **Cue#** column (e.g. `12`, `LX12`).
- An **Action** starting with `/` overrides that (e.g. `/cue/12/go`, `/go`, `/cue/SND5/panic`).
- Cues with an empty Cue# don't fire anything.
- QLab gets no `/tc`. QLab can't chase timecode over OSC; it reads MTC/LTC only.
- **In QLab** (Workspace Settings → Network): OSC access must be on. If the workspace has an OSC passcode, pass it with `--qlab-pass`. The relay then sends `/connect` before each fire.
- To have **QLab drive the cue sheet**, add a QLab **Network cue** that sends `/play`, `/stop`, `/cue 12`, etc. to the relay's `--osc-in` port.

**OSC IN — remote transport** (`--osc-in [PORT]`, default 9000)

Drives the cue sheet's **Manual** transport, so the MTC-30 (Art-Net OUT) and OSC OUT follow. Needs a cue sheet open on **Source → Manual** with **⇢ TC OUT** connected — the relay forwards, the page acts.

| OSC address | Does |
|---|---|
| `/play` (or `/start`), `/stop`, `/toggle` | Transport — `/play` resumes from where it stopped |
| `/locate "01:02:03:04"` or `/locate 3723.5` | Jump to a TC (string) or seconds (number) |
| `/nudge -1` | ± seconds |
| `/cue "12"` or `/cue/12` | Locate to cue #12's TC In (current Act first) |
| `/next`, `/prev` | Locate to the next / previous cue in the current Act |

- Any prefix works (`/tc/play`, `/show/next`) — the relay looks at the last part of the address.
- Button releases (`/play 0`, sent by Companion/TouchOSC on key-up) are ignored.
- Docker: publish the UDP port too (`- "9000:9000/udp"`); on macOS run natively as for Art-Net.

---

### 5. Fake — Free-run generator (no hardware needed)

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

The toolbar **✎ Edit** button switches the table between two modes (remembered per browser, **OFF** by default so a stray click during the show can't change anything):

- **Edit: OFF — click to locate.** Clicking a cue row jumps the TC to that cue's **TC In** (and selects its Act in the Chase bar). If Manual is running, the playhead jumps there and keeps rolling. If it's stopped, the cue is parked: the TC box is filled in, Art-Net OUT holds on that frame, and **▶ START** plays from it. With a WebSocket/MTC source the external clock is in charge, so the page only fills in the TC box and shows a warning.
- **Edit: ON** — everything below is editable directly in the table, no re-import needed (**＋ Add Cue** turns Edit on by itself):

- **Add a cue** — toolbar **＋ Add Cue** (appends to the current/default act), or hover any row and click its **＋** to insert right after it.
- **Delete a cue** — hover a row, click **✕** (confirms first).
- **Rename / edit fields** — click into Cue#, Label/Scene, Trigger, Dept, Device, Action, Fade, or Notes and type. Commits on blur or Enter.
- **Edit Duration** — click the Dur cell, type `HH:MM:SS:FF`. TC In/Out for every following cue ripples forward automatically — same mechanism as drag-reordering.
- **Edit TC Out** — sets that cue's duration (its TC In stays put); following cues ripple.
- **Edit TC In** — the *previous* cue's duration stretches/shrinks so this cue starts there and keeps its own length; following cues ripple. On the **first cue of an act** it moves the whole act's start time instead.
- All of the above feed the existing **⎌ Undo** button and autosave (localStorage), so none of this is riskier than a drag-reorder.

**Live sync across hosts** — any edit (rename, add/delete/reorder, status, notes, meta fields, TC color) is pushed to every other browser connected via **Source: WebSocket** to the same relay, over that same connection — no separate setup. A browser that joins later gets the current cue sheet immediately (the relay caches the latest snapshot for new connections). The one thing that's deliberately *not* synced is the transient "Running" highlight — each host computes that itself from the shared TC feed, so it stays consistent without fighting over the wire. Hosts using **MTC (Web MIDI)** as their TC source instead of WebSocket aren't on this channel and won't send or receive edits.

**Status** — a dropdown per cue: Standby / Ready / Running / Hold / Done / Cut. While a cue is the one currently under the TC playhead, its Status is **automatically forced to "Running"** (green, pulsing) — this overwrites whatever was set manually. The instant that cue's TC window ends, it reverts to **"Standby"** (not whatever it was before — a cue left on "Hold" or "Cut" will read "Standby" after the playhead passes through it). Driven purely by the chase engine, so it behaves the same regardless of TC source (Manual / WebSocket / MTC).

---

## Docker

`Dockerfile` + `docker-compose.yml` run the relay and the cue sheet as two containers — `relay` (the WS relay, multi-stage build so the final image only carries the ALSA runtime lib, not the compiler) and `cuesheet` (nginx serving `timecode_cue_sheet_4.html` as a static site).

```bash
docker compose up -d --build
```

- Relay: `ws://<host>:8765` — defaults to the free-run generator from `01:00:00:00`, so it works out of the box with zero hardware/config, good for testing the cue sheet.
- Cue sheet UI: `http://<host>:8085`

**Changing ports** — both are env-var driven (`${RELAY_WS_PORT:-8765}` / `${CUESHEET_PORT:-8085}` in `docker-compose.yml`):

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

**Art-Net mode needs the host's network** — broadcast packets don't reach a container behind Docker's bridge NAT. On a Linux host, add `network_mode: host` to the relay service (and drop its `ports:`, host mode publishes 8765 directly) with `command: ["--artnet"]`. On macOS, run `tc_relay.py --artnet` natively instead.

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
| **Show day (Quick Start step 3️⃣)** | `python3 tc_relay.py --artnet-out 10.10.11.226 --artnet --artnet-src 10.10.11.226 --qlab 127.0.0.1 --osc-in 9000` |
| MTC-30 TC + its own time back in the big clock | `python3 tc_relay.py --artnet-out 10.10.11.226 --artnet --artnet-src 10.10.11.226` |
| MTC from MOTU interface | `python3 tc_relay.py --mtc "MOTU"` |
| MTC over RTP-MIDI (Horae/TimeCore) | `python3 tc_relay.py --mtc "TimeCore"` |
| MTC, custom WS port | `python3 tc_relay.py --mtc "USB MIDI" --ws-port 9000` |
| Art-Net Timecode (MTC-30, etc.) | `python3 tc_relay.py --artnet` |
| Art-Net, one sender only | `python3 tc_relay.py --artnet --artnet-src 10.10.11.226` |
| Art-Net OUT from Manual transport | `python3 tc_relay.py --artnet-out 10.10.11.255` |
| Art-Net OUT, unicast to MTC-30 | `python3 tc_relay.py --artnet-out 10.10.11.226` |
| OSC OUT (TC + cue fires) | `python3 tc_relay.py --artnet-out 10.10.11.226 --osc-out 10.10.11.50:53000` |
| QLab cue fires (QLab on this Mac) | `python3 tc_relay.py --artnet-out 10.10.11.226 --qlab 127.0.0.1` |
| OSC IN remote transport | `python3 tc_relay.py --artnet-out 10.10.11.226 --osc-in 9000` |
| Free-run from 1h | `python3 tc_relay.py --fake 01:00:00:00` |
| Free-run, 25fps | `python3 tc_relay.py --fake 00:59:50:00 --fps 25` |

---

## Troubleshooting

**`OSError: [Errno 48] … address already in use` on 8765**
- Something else owns the WS port — usually the Docker `tc-relay` container (fake mode)
- `lsof -nP -iTCP:8765 -sTCP:LISTEN` to see who; `docker stop tc-relay` to free it, or start the relay with `--ws-port 8766` and connect the cue sheet to that port instead

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

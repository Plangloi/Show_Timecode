#!/usr/bin/env python3
"""
tc_relay.py — Decode MTC (MIDI Time Code), broadcast to WebSocket clients.

Le cue sheet HTML se connecte sur ws://<host>:8765 et reçoit {"tc": "HH:MM:SS:FF"}.

Usage:
    pip install websockets python-rtmidi
    ./tc_relay.py --mtc "Horae"

MTC source can be a local MIDI port, an IAC/virtual bus, or an RTP-MIDI
(AppleMIDI) network session — Horae or a Visual Productions TimeCore feed
an RTP-MIDI session the same way, it just needs to be joined at the OS level
first (see README). Once joined it shows up as a regular MIDI port name.

Test sans matériel (générateur free-run):
    ./tc_relay.py --fake 01:00:00:00
"""
import asyncio, json, argparse, time, sys

clients = set()

async def ws_handler(websocket):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)

async def broadcast(tc: str):
    if not clients:
        return
    msg = json.dumps({"tc": tc})
    await asyncio.gather(*(c.send(msg) for c in list(clients)), return_exceptions=True)

# ---------------------------------------------------------------- MTC source
async def mtc_source(port_filter: str):
    """Decode MIDI Time Code (quarter-frame + full-frame) from a MIDI input.
    pip install python-rtmidi"""
    import rtmidi
    RATES = [24, 25, 29.97, 30]
    midiin = rtmidi.MidiIn()
    ports = midiin.get_ports()
    idx = next((i for i, p in enumerate(ports) if port_filter.lower() in p.lower()), None)
    if idx is None:
        print(f"[mtc] no MIDI input matching '{port_filter}'. Available: {ports}")
        sys.exit(1)
    midiin.open_port(idx)
    midiin.ignore_types(sysex=False, timing=False)
    print(f"[mtc] listening on '{ports[idx]}'")

    qf = [None] * 8
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def cb(event, _):
        msg, _delta = event
        if msg[0] == 0xF1:                          # quarter-frame
            piece, val = msg[1] >> 4, msg[1] & 0x0F
            qf[piece] = val
            if piece == 7 and all(v is not None for v in qf):
                ff = qf[0] | (qf[1] << 4); ss = qf[2] | (qf[3] << 4)
                mm = qf[4] | (qf[5] << 4); hh = qf[6] | ((qf[7] & 0x1) << 4)
                fps = RATES[(qf[7] >> 1) & 0x3]
                sec = hh * 3600 + mm * 60 + ss + (ff + 2) / fps  # +2fr QF latency comp
                for i in range(8): qf[i] = None
                loop.call_soon_threadsafe(queue.put_nowait, (sec, fps))
        elif len(msg) >= 9 and msg[0] == 0xF0 and msg[1] == 0x7F and msg[3] == 0x01 and msg[4] == 0x01:
            fps = RATES[(msg[5] >> 5) & 0x3]        # full-frame sysex
            sec = (msg[5] & 0x1F) * 3600 + msg[6] * 60 + msg[7] + msg[8] / fps
            loop.call_soon_threadsafe(queue.put_nowait, (sec, fps))

    midiin.set_callback(cb)
    while True:
        sec, fps = await queue.get()
        hh, rem = divmod(int(sec), 3600); mm, ss = divmod(rem, 60)
        ff = int((sec % 1) * fps)
        await broadcast(f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}")

# ---------------------------------------------------------------- fake source
async def fake_source(start_tc: str, fps: int):
    h, m, s, f = (list(map(int, start_tc.split(":"))) + [0, 0, 0, 0])[:4]
    base = h * 3600 + m * 60 + s + f / fps
    t0 = time.monotonic()
    while True:
        t = base + (time.monotonic() - t0)
        hh, rem = divmod(int(t), 3600)
        mm, ss = divmod(rem, 60)
        ff = int((t % 1) * fps)
        await broadcast(f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}")
        await asyncio.sleep(1 / 10)  # 10 Hz suffit pour l'UI

# ---------------------------------------------------------------- main
async def main():
    import websockets
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws-port", type=int, default=8765)
    ap.add_argument("--fake", metavar="HH:MM:SS:FF", help="Free-run generator (no hardware needed)")
    ap.add_argument("--mtc", metavar="PORT_NAME", help="Decode MTC from MIDI input (substring match)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    if not (args.fake or args.mtc):
        ap.error("--mtc or --fake required")

    if args.fake:
        src = fake_source(args.fake, args.fps)
    else:
        src = mtc_source(args.mtc)

    async with websockets.serve(ws_handler, "0.0.0.0", args.ws_port):
        print(f"[ws] broadcasting on ws://0.0.0.0:{args.ws_port}")
        await src

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

#!/usr/bin/env python3
"""
tc_relay.py — Decode MTC (MIDI Time Code) or Art-Net Timecode, broadcast to WebSocket clients.

Le cue sheet HTML se connecte sur ws://<host>:8765 et reçoit {"tc": "HH:MM:SS:FF"}.
Cue-sheet edits sent back over the same socket (type "cuesheet_sync") are relayed
to every other connected browser, and the latest one is replayed to new joiners.

Usage:
    pip install websockets python-rtmidi
    ./tc_relay.py --mtc "Horae"

MTC source can be a local MIDI port, an IAC/virtual bus, or an RTP-MIDI
(AppleMIDI) network session — Horae or a Visual Productions TimeCore feed
an RTP-MIDI session the same way, it just needs to be joined at the OS level
first (see README). Once joined it shows up as a regular MIDI port name.

Art-Net Timecode (ArtTimeCode, UDP 6454) — e.g. DOREMiDi Timecode Center MTC-30,
no MIDI driver or session to join, just be on the same subnet:
    ./tc_relay.py --artnet
    ./tc_relay.py --artnet --artnet-src 10.10.11.214   # ignore other Art-Net TC senders

Art-Net Timecode OUT — the cue sheet's Manual transport (START/STOP/±1s) drives
an ArtTimeCode stream generated here, e.g. to make an MTC-30 chase it:
    ./tc_relay.py --artnet-out 10.10.11.255            # subnet broadcast
    ./tc_relay.py --artnet --artnet-out 10.10.11.214   # unicast, and keep listening

Test sans matériel (générateur free-run):
    ./tc_relay.py --fake 01:00:00:00
"""
import asyncio, json, argparse, time, sys, socket

clients = set()
last_cue_sync = None  # most recent cuesheet_sync payload, replayed to newly-joined clients
artnet_out = None     # ArtnetOut when started with --artnet-out

async def ws_handler(websocket):
    global last_cue_sync
    clients.add(websocket)
    try:
        if last_cue_sync is not None:
            await websocket.send(last_cue_sync)
        async for message in websocket:
            try:
                msg = json.loads(message)
                kind = msg.get("type")
            except (json.JSONDecodeError, AttributeError):
                msg, kind = None, None
            if kind == "tc_out":             # transport for Art-Net OUT — handled here, not relayed
                if not artnet_out:
                    status = {"ok": False, "msg": "relay not started with --artnet-out"}
                else:
                    try:
                        artnet_out.update(msg)
                        status = {"ok": True, "dest": artnet_out.dest}
                    except (TypeError, ValueError):
                        status = {"ok": False, "msg": "bad tc_out message"}
                await websocket.send(json.dumps({"type": "tc_out_status", **status}))
                continue
            if kind == "cuesheet_sync":
                last_cue_sync = message
            await broadcast_raw(message)
    finally:
        clients.discard(websocket)

async def broadcast_raw(msg: str):
    if not clients:
        return
    await asyncio.gather(*(c.send(msg) for c in list(clients)), return_exceptions=True)

async def broadcast(tc: str):
    await broadcast_raw(json.dumps({"tc": tc}))

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

# ---------------------------------------------------------------- Art-Net source
async def artnet_source(port, src_filter=None):
    """Decode Art-Net Timecode (OpCode 0x9700, OpTimeCode). Senders broadcast
    one packet per frame on UDP 6454 — no extra deps, plain socket."""
    RATES = [24, 25, 29.97, 30]
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            if src_filter and addr[0] != src_filter:
                return
            # "Art-Net\0" | OpCode LE | ProtVer | Filler1 | StreamId | Frames Secs Mins Hours Type
            if len(data) < 19 or data[:8] != b"Art-Net\0" or data[8:10] != b"\x00\x97":
                return
            ff, ss, mm, hh, typ = data[14:19]
            queue.put_nowait((f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}", RATES[typ & 0x3], addr[0]))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):  # share 6454 with a lighting app on the same host
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("0.0.0.0", port))
    await loop.create_datagram_endpoint(Proto, sock=sock)
    print(f"[artnet] listening on udp/{port}" + (f" from {src_filter}" if src_filter else ""))

    last, seen = None, None
    while True:
        tc, fps, src = await queue.get()
        if seen != (src, fps):
            seen = (src, fps)
            print(f"[artnet] timecode from {src} @ {fps} fps")
        if tc != last:                       # sender repeats the frame while stopped
            last = tc
            await broadcast(tc)

# ---------------------------------------------------------------- Art-Net OUT
class ArtnetOut:
    """Generate ArtTimeCode from a play/stop/locate transport sent by the page.
    The relay owns the frame clock so packets go out one per frame on time,
    whatever the browser's timer jitter."""
    TYPES = {24: 0, 25: 1, 30: 3}

    def __init__(self, dest, port=6454):
        self.dest, self.port = dest, port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.playing, self.base_sec, self.base_t, self.fps = False, 0.0, 0.0, 30
        self.wake = asyncio.Event()

    def update(self, msg):
        fps = int(msg.get("fps") or 30)
        self.fps = fps if fps in self.TYPES else 30
        self.base_sec, self.base_t = float(msg.get("sec") or 0), time.monotonic()
        self.playing = msg.get("state") == "play"
        self.wake.set()

    def now(self):
        return self.base_sec + (time.monotonic() - self.base_t if self.playing else 0)

    def send(self, frame):
        fps = self.fps
        hh, rem = divmod(frame // fps, 3600); mm, ss = divmod(rem, 60)
        pkt = b"Art-Net\0" + b"\x00\x97" + b"\x00\x0e" + b"\x00\x00" + bytes(
            [frame % fps, ss, mm, hh % 24, self.TYPES[fps]])
        try:
            self.sock.sendto(pkt, (self.dest, self.port))
        except OSError as e:                 # e.g. not on that subnet yet — keep running
            print(f"[artnet-out] send failed: {e}")

    async def run(self):
        print(f"[artnet-out] sending to {self.dest}:{self.port} on transport from the cue sheet")
        await self.wake.wait()               # silent until the page sends a transport — never blast 00:00:00:00
        while True:
            self.wake.clear()
            if not self.playing:
                frame = int(self.now() * self.fps)
                for _ in range(3):           # stop/locate: repeat the held frame, like the MTC-30 does
                    self.send(frame)
                await self.wake.wait()
                continue
            frame = int(self.now() * self.fps)
            self.send(frame)
            next_at = (frame + 1) / self.fps
            try:                             # sleep to the next frame edge, or until the transport changes
                await asyncio.wait_for(self.wake.wait(), max(0.0, next_at - self.now()))
            except asyncio.TimeoutError:
                pass

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
    ap.add_argument("--artnet", action="store_true", help="Decode Art-Net Timecode (UDP broadcast)")
    ap.add_argument("--artnet-port", type=int, default=6454)
    ap.add_argument("--artnet-src", metavar="IP", help="Only accept Art-Net TC from this sender")
    ap.add_argument("--artnet-out", metavar="IP", help="Send Art-Net TC driven by the cue sheet's Manual transport "
                                                       "(subnet broadcast like 10.10.11.255, or a device IP)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    n_src = sum(map(bool, (args.fake, args.mtc, args.artnet)))
    if n_src > 1 or (n_src == 0 and not args.artnet_out):
        ap.error("one of --mtc, --artnet or --fake required (or --artnet-out alone)")

    global artnet_out
    tasks = []
    if args.artnet_out:
        artnet_out = ArtnetOut(args.artnet_out)
        tasks.append(artnet_out.run())

    if not n_src:
        src = None
    elif args.fake:
        src = fake_source(args.fake, args.fps)
    elif args.artnet:
        src = artnet_source(args.artnet_port, args.artnet_src)
    else:
        src = mtc_source(args.mtc)

    async with websockets.serve(ws_handler, "0.0.0.0", args.ws_port):
        print(f"[ws] broadcasting on ws://0.0.0.0:{args.ws_port}")
        if src:
            tasks.append(src)
        await (asyncio.gather(*tasks) if tasks else asyncio.Future())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

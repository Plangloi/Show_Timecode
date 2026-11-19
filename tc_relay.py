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
    ./tc_relay.py --artnet --artnet-src 10.10.11.226   # ignore other Art-Net TC senders

Art-Net Timecode OUT — the cue sheet's Manual transport (START/STOP/±1s) drives
an ArtTimeCode stream generated here, e.g. to make an MTC-30 chase it:
    ./tc_relay.py --artnet-out 10.10.11.255            # subnet broadcast
    ./tc_relay.py --artnet --artnet-out 10.10.11.226   # unicast, and keep listening

OSC — send TC + cue fires out, take remote transport in (no extra deps):
    ./tc_relay.py --artnet-out 10.10.11.226 --osc-out 10.10.11.50:53000   # /tc + /cue/go
    ./tc_relay.py --fake 01:00:00:00 --osc-out 127.0.0.1:9001 --osc-out 10.10.11.60:8000
    ./tc_relay.py --artnet-out 10.10.11.226 --osc-in 9000   # /play /stop /locate /cue /next /prev
    ./tc_relay.py --artnet-out 10.10.11.226 --qlab 127.0.0.1   # cue goes live → QLab /cue/<cue#>/start

Test sans matériel (générateur free-run):
    ./tc_relay.py --fake 01:00:00:00
"""
import asyncio, json, argparse, time, sys, socket, struct, shlex

clients = set()
last_cue_sync = None  # most recent cuesheet_sync payload, replayed to newly-joined clients
last_transport = None # most recent Manual transport state (play/stop/paused/act), for phones
manual_out = None     # ManualOut when started with --artnet-out / --osc-out / --osc-in
osc_out = None        # OscOut when started with --osc-out

# ---------------------------------------------------------------- OSC codec (OSC 1.0, no deps)
def _osc_str(x: str) -> bytes:
    b = x.encode() + b"\0"
    return b + b"\0" * (-len(b) % 4)

def osc_encode(addr: str, args=()) -> bytes:
    tags, data = ",", b""
    for a in args:
        if isinstance(a, bool) or a is None:
            tags += "T" if a else ("F" if a is False else "N")
        elif isinstance(a, int):
            tags += "i"; data += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"; data += struct.pack(">f", a)
        else:
            tags += "s"; data += _osc_str(str(a))
    return _osc_str(addr) + _osc_str(tags) + data

def _osc_read_str(buf, i):
    end = buf.index(b"\0", i)
    return buf[i:end].decode(errors="replace"), (end + 4) & ~3

def osc_decode(buf: bytes):
    """Yield (address, [args]) for a message or (nested) bundle."""
    if buf.startswith(b"#bundle\0"):
        i = 16
        while i + 4 <= len(buf):
            (n,) = struct.unpack(">i", buf[i:i + 4]); i += 4
            yield from osc_decode(buf[i:i + n]); i += n
        return
    addr, i = _osc_read_str(buf, 0)
    tags, i = _osc_read_str(buf, i) if i < len(buf) else (",", i)
    args = []
    for t in tags[1:]:
        if t == "i":   args.append(struct.unpack(">i", buf[i:i + 4])[0]); i += 4
        elif t == "f": args.append(struct.unpack(">f", buf[i:i + 4])[0]); i += 4
        elif t == "d": args.append(struct.unpack(">d", buf[i:i + 8])[0]); i += 8
        elif t == "h": args.append(struct.unpack(">q", buf[i:i + 8])[0]); i += 8
        elif t == "s": v, i = _osc_read_str(buf, i); args.append(v)
        elif t == "T": args.append(True)
        elif t == "F": args.append(False)
        elif t == "N": args.append(None)
        else: break                              # blobs / exotic types: not needed here
    yield addr, args

def _hostport(s):
    host, _, port = s.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError(f"expected IP:PORT, got {s!r}")
    return host, int(port)

def _num(tok: str):
    try: return int(tok)
    except ValueError:
        try: return float(tok)
        except ValueError: return tok

class OscOut:
    """Send /tc on every new frame and cue fires to OSC targets.
    Generic targets (--osc-out) get /tc + /cue/go; QLab targets (--qlab) get
    /cue/<cue#>/start only — QLab has no OSC timecode input."""
    def __init__(self, targets, qlab=(), tc_addr="/tc", qlab_pass=None):
        self.targets, self.qlab, self.tc_addr, self.qlab_pass = list(targets), list(qlab), tc_addr, qlab_pass
        self.last_tc, self.fired = None, {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def describe(self):
        return ", ".join([f"{h}:{p}" for h, p in self.targets] + [f"QLab {h}:{p}" for h, p in self.qlab])

    def _sendto(self, targets, addr, args=()):
        pkt = osc_encode(addr, args)
        for t in targets:
            try:
                self.sock.sendto(pkt, t)
            except OSError as e:
                print(f"[osc-out] send to {t[0]}:{t[1]} failed: {e}")

    def send(self, addr, args=()):
        self._sendto(self.targets, addr, args)

    def send_tc(self, tc: str):
        if self.targets and tc != self.last_tc:   # one message per new frame, even if two paths report it
            self.last_tc = tc
            self.send(self.tc_addr, [tc])

    def cue_go(self, msg):
        key = (str(msg.get("cue", "")), str(msg.get("label", "")), str(msg.get("tc", "")))
        now = time.monotonic()
        if now - self.fired.get(key, -99) < 2:   # several browsers report the same cue — fire once
            return
        self.fired = {k: v for k, v in self.fired.items() if now - v < 10}
        self.fired[key] = now
        action = str(msg.get("action") or "").strip()
        raw = None
        if action.startswith("/"):           # Action column holds a raw OSC command, e.g. /cue/12/go
            try: toks = shlex.split(action)
            except ValueError: toks = action.split()
            raw = (toks[0], [_num(t) for t in toks[1:]])
        if self.targets:
            addr, args = raw or ("/cue/go", [str(msg.get(k) or "") for k in ("cue", "label", "dept", "device", "action")])
            print(f"[osc-out] cue {key[0] or '?'} @ {key[2]} → {addr} {args}")
            self.send(addr, args)
        if self.qlab:
            cue = key[0].strip()
            if raw:
                addr, args = raw
            elif cue:
                addr, args = f"/cue/{cue}/start", []
            else:
                print(f"[qlab] cue without a number @ {key[2]} — nothing to start")
                return
            if self.qlab_pass:               # QLab's UDP "connection" lapses after 61s idle — reconnect each time
                self._sendto(self.qlab, "/connect", [self.qlab_pass])
            print(f"[qlab] cue {cue or '?'} @ {key[2]} → {addr} {args}")
            self._sendto(self.qlab, addr, args)

async def ws_handler(websocket):
    global last_cue_sync, last_transport
    clients.add(websocket)
    try:
        if last_cue_sync is not None:
            await websocket.send(last_cue_sync)
        if last_transport is not None:
            await websocket.send(last_transport)
        async for message in websocket:
            try:
                msg = json.loads(message)
                kind = msg.get("type")
            except (json.JSONDecodeError, AttributeError):
                msg, kind = None, None
            if kind == "tc_out":             # Manual transport for TC OUT — handled here, not relayed
                if not manual_out:
                    status = {"ok": False, "msg": "relay not started with --artnet-out / --osc-out / --osc-in"}
                else:
                    try:
                        manual_out.update(msg)
                        status = {"ok": True, "dest": manual_out.describe()}
                        last_transport = json.dumps({"type": "transport", "state": msg.get("state"),
                                                     "paused": bool(msg.get("paused")), "act": msg.get("act"),
                                                     "sec": msg.get("sec"), "fps": manual_out.fps})
                        await broadcast_raw(last_transport)   # phones show PLAY / PAUSE / STOP right
                    except (TypeError, ValueError):
                        status = {"ok": False, "msg": "bad tc_out message"}
                await websocket.send(json.dumps({"type": "tc_out_status", **status}))
                continue
            if kind == "cue_go":             # a cue went live in a browser — fire OSC, not relayed
                if osc_out:
                    osc_out.cue_go(msg)
                continue
            if kind == "cuesheet_sync":
                last_cue_sync = message
            await broadcast_raw(message)
    except Exception as e:                   # browser reloaded / tab closed / Wi-Fi dropped — normal, not a crash
        if type(e).__name__ not in ("ConnectionClosedError", "ConnectionClosedOK"):
            raise
    finally:
        clients.discard(websocket)

async def broadcast_raw(msg: str):
    if not clients:
        return
    await asyncio.gather(*(c.send(msg) for c in list(clients)), return_exceptions=True)

async def broadcast(tc: str):
    if osc_out:
        osc_out.send_tc(tc)
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

    if manual_out:
        print("[artnet] Manual mode: incoming TC is shown on the page as the device's time (big clock), "
              "the cue sheet stays the master")
    last, seen, last_sent = None, set(), 0.0
    while True:
        tc, fps, src = await queue.get()
        if manual_out and src == manual_out.local_ip:
            continue                         # our own Art-Net OUT coming back — screens already get it directly
        if (src, fps) not in seen:
            seen.add((src, fps))
            print(f"[artnet] timecode from {src} @ {fps} fps")
        if manual_out:                       # with --artnet-out: the box's TC is feedback, not the show clock
            now = time.monotonic()
            if tc != last or now - last_sent > 0.25:   # keep a held frame alive so the page knows it's live
                last, last_sent = tc, now
                await broadcast_raw(json.dumps({"type": "device_tc", "dtc": tc, "src": src}))
            continue
        if tc != last:                       # sender repeats the frame while stopped
            last = tc
            await broadcast(tc)

# ---------------------------------------------------------------- Manual OUT (Art-Net and/or OSC)
class ManualOut:
    """Generate TC from a play/stop/locate transport sent by the page — as
    ArtTimeCode (--artnet-out) and/or OSC /tc (--osc-out). The relay owns the
    frame clock so packets go out one per frame on time, whatever the
    browser's timer jitter."""
    TYPES = {24: 0, 25: 1, 30: 3}

    def __init__(self, dest=None, port=6454):
        self.dest, self.port = dest, port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.playing, self.base_sec, self.base_t, self.fps = False, 0.0, 0.0, 30
        self.wake = asyncio.Event()
        self.local_ip = None                 # our own address toward dest — to ignore our own Art-Net echo
        if dest:
            try:
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                probe.connect((dest, port))
                self.local_ip = probe.getsockname()[0]
                probe.close()
            except OSError:
                pass

    def update(self, msg):
        fps = int(msg.get("fps") or 30)
        self.fps = fps if fps in self.TYPES else 30
        self.base_sec, self.base_t = float(msg.get("sec") or 0), time.monotonic()
        self.playing = msg.get("state") == "play"
        self.wake.set()

    def now(self):
        return self.base_sec + (time.monotonic() - self.base_t if self.playing else 0)

    def describe(self):
        parts = [f"Art-Net {self.dest}"] if self.dest else []
        if osc_out:
            parts.append(f"OSC {osc_out.describe()}")
        return " · ".join(parts) or "remote only (no TC output)"

    def send(self, frame):
        fps = self.fps
        hh, rem = divmod(frame // fps, 3600); mm, ss = divmod(rem, 60)
        tc = f"{hh % 24:02d}:{mm:02d}:{ss:02d}:{frame % fps:02d}"
        if osc_out:
            osc_out.send_tc(tc)
        if clients:                          # other screens on Source → WebSocket follow the show clock
            asyncio.get_running_loop().create_task(broadcast_raw(json.dumps({"tc": tc})))
        if not self.dest:
            return
        pkt = b"Art-Net\0" + b"\x00\x97" + b"\x00\x0e" + b"\x00\x00" + bytes(
            [frame % fps, ss, mm, hh % 24, self.TYPES[fps]])
        try:
            self.sock.sendto(pkt, (self.dest, self.port))
        except OSError as e:                 # e.g. not on that subnet yet — keep running
            print(f"[artnet-out] send failed: {e}")

    async def run(self):
        print(f"[tc-out] {self.describe()} — driven by the cue sheet's Manual transport")
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

# ---------------------------------------------------------------- OSC IN (remote transport)
REMOTE_CMDS = {"play", "start", "stop", "pause", "mark", "act", "toggle", "locate", "nudge", "cue", "next", "prev"}

async def osc_in(port):
    """Remote-control the cue sheet's Manual transport. Commands are forwarded to
    the browsers as {"type":"remote"}; a page in Source → Manual applies them, and
    its TC OUT connection carries the result back to Art-Net/OSC OUT."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    class Proto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            try:
                for a, args in osc_decode(data):
                    queue.put_nowait((a, args, addr[0]))
            except (ValueError, struct.error, IndexError):
                pass

    await loop.create_datagram_endpoint(Proto, local_addr=("0.0.0.0", port))
    print(f"[osc-in] listening on udp/{port}: /play /stop /pause /toggle /mark /act <n> /locate <tc|sec> /nudge <sec> /cue <#> /next /prev")
    while True:
        addr, args, src = await queue.get()
        parts = [p for p in addr.lower().split("/") if p]
        cmd = parts[-1] if parts else ""
        if parts[-2:-1] == ["cue"] and cmd not in REMOTE_CMDS:   # /cue/12 → /cue "12"
            cmd, args = "cue", [addr.split("/")[-1]]
        if cmd not in REMOTE_CMDS:
            print(f"[osc-in] ignored {addr} {args} from {src}")
            continue
        if cmd in ("play", "start", "stop", "toggle", "next", "prev") and args and args[0] in (0, 0.0, False):
            continue                          # button release (Companion/TouchOSC send 1 then 0)
        cmd = "play" if cmd == "start" else cmd
        arg = args[0] if args else None
        print(f"[osc-in] {cmd}" + (f" {arg}" if arg is not None else "") + f" from {src}"
              + ("" if clients else "  (no cue sheet connected — nothing to drive)"))
        await broadcast_raw(json.dumps({"type": "remote", "cmd": cmd, "arg": arg}))

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
    ap.add_argument("--osc-out", metavar="IP:PORT", type=_hostport, action="append",
                    help="Send OSC /tc + cue fires to this target (repeatable)")
    ap.add_argument("--osc-tc-addr", default="/tc", help="OSC address for timecode (default /tc)")
    ap.add_argument("--qlab", metavar="IP[:PORT]", action="append",
                    type=lambda v: _hostport(v if ":" in v else v + ":53000"),
                    help="Fire QLab cues: /cue/<cue#>/start when a cue goes live (port 53000 default, repeatable)")
    ap.add_argument("--qlab-pass", metavar="PASSCODE", help="QLab workspace OSC passcode, if one is set")
    ap.add_argument("--osc-in", metavar="PORT", type=int, nargs="?", const=9000,
                    help="Listen for OSC remote transport (default port 9000)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    n_src = sum(map(bool, (args.fake, args.mtc, args.artnet)))
    manual = bool(args.artnet_out or args.osc_out or args.osc_in or args.qlab)
    if n_src > 1 or (n_src == 0 and not manual):
        ap.error("one of --mtc, --artnet or --fake required (or --artnet-out / --osc-out / --qlab / --osc-in alone)")

    global manual_out, osc_out
    tasks = []
    if args.osc_out or args.qlab:
        osc_out = OscOut(args.osc_out or [], args.qlab or [], args.osc_tc_addr, args.qlab_pass)
        if args.osc_out:
            print(f"[osc-out] {args.osc_tc_addr} + cue fires → {', '.join(f'{h}:{p}' for h, p in args.osc_out)}")
        if args.qlab:
            print(f"[qlab] /cue/<cue#>/start → {', '.join(f'{h}:{p}' for h, p in args.qlab)}"
                  + (" (with passcode)" if args.qlab_pass else ""))
    if manual:
        manual_out = ManualOut(args.artnet_out)
        tasks.append(manual_out.run())
    if args.osc_in:
        tasks.append(osc_in(args.osc_in))

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

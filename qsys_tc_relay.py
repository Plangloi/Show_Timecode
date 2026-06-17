#!/usr/bin/env python3
"""
qsys_tc_relay.py — Poll Q-SYS Core timecode via QRC, broadcast to WebSocket clients.

Le cue sheet HTML se connecte sur ws://<host>:8765 et reçoit {"tc": "HH:MM:SS:FF"}.

Usage:
    pip install websockets
    ./qsys_tc_relay.py --core 192.168.10.10 --component LTC_Reader --control timecode

Adapte --component/--control au named component de ton design Q-SYS
(ex: un LTC Reader, un Q-SYS Media Player position, ou un script qui expose le TC).

Test sans Core (générateur free-run):
    ./qsys_tc_relay.py --fake 01:00:00:00
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

# ---------------------------------------------------------------- QRC poll
async def qrc_source(host: str, port: int, component: str, control: str, rate: float):
    """JSON-RPC 2.0 over TCP, NULL-terminated frames (QRC protocol)."""
    while True:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            print(f"[qrc] connected {host}:{port}")
            rpc_id = 0

            async def send(obj):
                writer.write(json.dumps(obj).encode() + b"\x00")
                await writer.drain()

            # NoOp keepalive obligatoire (<60s) — QRC ferme sinon
            async def keepalive():
                while True:
                    await asyncio.sleep(30)
                    await send({"jsonrpc": "2.0", "method": "NoOp", "params": {}})

            ka = asyncio.create_task(keepalive())
            buf = b""
            try:
                while True:
                    rpc_id += 1
                    await send({"jsonrpc": "2.0", "id": rpc_id, "method": "Component.Get",
                                "params": {"Name": component,
                                           "Controls": [{"Name": control}]}})
                    # read one frame
                    while b"\x00" not in buf:
                        chunk = await reader.read(4096)
                        if not chunk:
                            raise ConnectionError("QRC closed")
                        buf += chunk
                    frame, _, buf = buf.partition(b"\x00")
                    try:
                        resp = json.loads(frame)
                        ctrls = resp.get("result", {}).get("Controls", [])
                        if ctrls:
                            tc = str(ctrls[0].get("String") or ctrls[0].get("Value", ""))
                            if tc:
                                await broadcast(tc)
                    except json.JSONDecodeError:
                        pass
                    await asyncio.sleep(rate)
            finally:
                ka.cancel()
        except (OSError, ConnectionError) as e:
            print(f"[qrc] {e} — retry in 3s")
            await asyncio.sleep(3)

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
    ap.add_argument("--core", help="Q-SYS Core IP")
    ap.add_argument("--port", type=int, default=1710, help="QRC port (default 1710)")
    ap.add_argument("--component", default="LTC_Reader", help="Named component")
    ap.add_argument("--control", default="timecode", help="Control name exposing TC string")
    ap.add_argument("--rate", type=float, default=0.1, help="Poll interval s (default 0.1)")
    ap.add_argument("--ws-port", type=int, default=8765)
    ap.add_argument("--fake", metavar="HH:MM:SS:FF", help="Free-run generator (no Core needed)")
    ap.add_argument("--mtc", metavar="PORT_NAME", help="Decode MTC from MIDI input (substring match)")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    if not (args.fake or args.core or args.mtc):
        ap.error("--core, --mtc or --fake required")

    if args.fake:
        src = fake_source(args.fake, args.fps)
    elif args.mtc:
        src = mtc_source(args.mtc)
    else:
        src = qrc_source(args.core, args.port, args.component, args.control, args.rate)

    async with websockets.serve(ws_handler, "0.0.0.0", args.ws_port):
        print(f"[ws] broadcasting on ws://0.0.0.0:{args.ws_port}")
        await src

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)

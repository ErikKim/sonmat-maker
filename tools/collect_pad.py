"""What does the pad really do, and who asked for it?  (maker tool, Windows PC with the pad connected)

    python tools/collect_pad.py [minutes=20] [out=collect_pad.log]

Three time-stamped streams into one file, while hapticsd.py and the game run:
    a <t> <shake> <n>     the pad's own accelerometer (USB input report 0x01, bytes 22-27), 20 ms windows:
                          standard deviation of the acceleration magnitude = how hard the pad is shaking now
    p <t> <json>          every vibration hapticsd.py starts (its monitor messages, UDP 47800 - so the app
                          window must be closed), including the ones its log leaves out (footsteps)
    b <t> <buttons hex>   buttons, to line things up with what the player did
Shaking with no "p" near it = something other than our engine is driving the pad (the game itself).
"""
import json, os, socket, struct, sys, threading, time
import hid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 20
out = open(os.path.join(HERE, sys.argv[2] if len(sys.argv) > 2 else "collect_pad.log"), "a", encoding="utf-8")
lock = threading.Lock()
def put(s):
    with lock:
        out.write(s + "\n")

def plays():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", 47800))
    except OSError as e:
        put(f"# cannot listen for engine plays: {e}"); return
    while True:
        d, _ = s.recvfrom(4096)
        put(f"p {time.time():.3f} {d.decode('utf-8', 'replace')}")

threading.Thread(target=plays, daemon=True).start()
devs = [d for d in hid.enumerate(0x054C, 0x0CE6)]
put(f"# start {time.strftime('%Y-%m-%d %H:%M:%S')} pads={len(devs)}")
if not devs:
    put("# no pad"); out.close(); sys.exit(1)
h = hid.device(); h.open_path(devs[0]["path"])
end, win, t0, btn = time.time() + minutes * 60, [], time.time(), None
while time.time() < end:
    r = h.read(64, 200)
    if not r or r[0] != 0x01 or len(r) < 28:
        continue
    ax, ay, az = struct.unpack_from("<hhh", bytes(r), 22)
    win.append((ax * ax + ay * ay + az * az) ** 0.5)
    b = bytes(r[8:11]).hex()
    now = time.time()
    if b != btn:
        btn = b; put(f"b {now:.3f} {b}")
    if now - t0 >= 0.02:
        m = sum(win) / len(win)
        sd = (sum((x - m) ** 2 for x in win) / len(win)) ** 0.5
        put(f"a {now:.3f} {sd:.0f} {len(win)}")
        win, t0 = [], now
        if int(now * 50) % 100 == 0: out.flush()
put("# end"); out.close()

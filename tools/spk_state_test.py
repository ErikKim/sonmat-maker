"""Pad speaker "comes and goes": one thing changed at a time, judged by ear. Run with the engine OFF and no game.

    python tools\\spk_state_test.py <step> [seconds=60]

Plays the real Wukong charge sounds (sounds/wukong/charge) every 2 s on ONE stream, the way the engine does, with a faint
vibration pattern under it (does the vibration drop out too?). No test tones, no pad microphone unless the step says so.
Steps (plan: _workspace/spk_hunt/05_verdict.md):
  base    nothing written to the pad (do this right after switching the pad off and on)
  lop     what Lies of P leaves behind when it quits: audio control on, [8]=0x00
  a30 a08 a38 a0c   audio control on, [8] = that value (0x30 = what the engine sends now)
  pwr0 pwrf         power-save byte [10] = 0x00 / 0x0f
  mic     open and close the pad microphone 7 times, then keep playing (does a state stay behind?)
  vol     pad volume 0x64 <-> 0x30 every 3 s (is this what the 10-09 test sounded like?)
  stream2 a second output stream opened and closed 7 times
  keep    an empty report every 0.5 s        enum   hid.enumerate every 3 s
"""
import sys, time, threading, wave, os, numpy as np, sounddevice as sd, hid
SR = 48000
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
step = sys.argv[1] if len(sys.argv) > 1 else "base"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60

def clip(i):
    w = wave.open(os.path.join(HERE, "sounds", "wukong", "charge", f"{i}.wav")); x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
    return (x.reshape(-1, w.getnchannels()).mean(1) if w.getnchannels() > 1 else x) * 0.5
clips = [clip(i) for i in (665805262, 800210353, 886119136)]
n = int(SR * secs); buf = np.zeros((n, 4), np.float32); t = np.arange(int(SR * 0.2)) / SR
for k in range(int(secs // 2)):
    c = clips[k % 3]; o = k * 2 * SR; c = c[:n - o]; buf[o:o + len(c), 0] += c
    h = (0.15 * np.sin(2 * np.pi * 60 * t)).astype(np.float32); o += SR; h = h[:max(0, n - o)]; buf[o:o + len(h), 2] += h
buf[:, 1] = buf[:, 0]; buf[:, 3] = buf[:, 2]

api = next(i for i, h in enumerate(sd.query_hostapis()) if h["name"] == "Windows WASAPI")
ds = [(i, d) for i, d in enumerate(sd.query_devices()) if d["hostapi"] == api and "DualSense" in d["name"]]
out = next(i for i, d in ds if d["max_output_channels"] == 4)
devs = []
for d in hid.enumerate(0x054C, 0x0CE6):
    h = hid.device(); h.open_path(d["path"]); devs.append(h)
def write(**kv):
    rep = bytearray(48); rep[0] = 0x02
    for k, v in kv.items(): rep[int(k[1:])] = v
    for h in devs: h.write(bytes(rep))
    print(time.strftime("%H:%M:%S"), "wrote", {k: hex(v) for k, v in kv.items()}, flush=True)

pos = [0]; done = threading.Event()
def cb(o, frames, ti, status):
    c = buf[pos[0]:pos[0] + frames]; o[:len(c)] = c; o[len(c):] = 0; pos[0] += frames
    if pos[0] >= n: done.set()

def side():
    time.sleep(6)                                   # three clean sounds first, then the change
    if step == "lop": write(b1=0x80, b8=0x00)
    elif step in ("a30", "a08", "a38", "a0c"): write(b1=0x80, b8=int(step[1:], 16))
    elif step == "pwr0": write(b2=0x02, b10=0x00)
    elif step == "pwrf": write(b2=0x02, b10=0x0F)
    elif step == "mic":
        mic = next(i for i, d in ds if d["max_input_channels"] > 0)
        for k in range(7):
            with sd.InputStream(device=mic, samplerate=SR, channels=1, dtype="float32", callback=lambda *a: None): time.sleep(0.8)
            print(time.strftime("%H:%M:%S"), "mic opened and closed", k + 1, flush=True); time.sleep(0.4)
    elif step == "vol":
        v = 0x30
        while not done.is_set(): write(b1=0x20, b6=v); v = 0x64 if v == 0x30 else 0x30; time.sleep(3)
        write(b1=0x20, b6=0x64)
    elif step == "stream2":
        for k in range(7):
            with sd.OutputStream(device=out, samplerate=SR, channels=4, dtype="float32", blocksize=480, latency=0.05, callback=lambda o, *a: o.fill(0)): time.sleep(0.8)
            print(time.strftime("%H:%M:%S"), "second stream opened and closed", k + 1, flush=True); time.sleep(0.4)
    elif step == "keep":
        while not done.is_set(): write(); time.sleep(0.5)
    elif step == "enum":
        while not done.is_set(): hid.enumerate(0x054C, 0x0CE6); print(time.strftime("%H:%M:%S"), "enumerate", flush=True); time.sleep(3)

print(time.strftime("%H:%M:%S"), "step", step, "-", secs, "s. First 6 s = unchanged, then the change.", flush=True)
threading.Thread(target=side, daemon=True).start()
with sd.OutputStream(device=out, samplerate=SR, channels=4, dtype="float32", blocksize=480, latency=0.05, callback=cb):
    done.wait()
print(time.strftime("%H:%M:%S"), "end", flush=True)

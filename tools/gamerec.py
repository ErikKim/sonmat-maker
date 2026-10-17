"""Record what the game plays on the PC's default speakers while it runs (maker tool, Windows).

    python tools/gamerec.py [minutes=60] [process name fragment=LOP-Win64] [out dir]

WASAPI loopback of the default output device, 48 kHz stereo, in 30 s wav files named by the clock time
of their first sample (rec_<epoch>.wav), so a moment in hapticsd's collect_<game>.log can be cut out
afterwards: the phone bell in Lies of P, the perfect-guard clang. Recordings stay on this PC.
"""
import os, subprocess, sys, time, wave
import numpy as np
import soundcard as sc

minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 60
proc = sys.argv[2] if len(sys.argv) > 2 else "LOP-Win64"
out = sys.argv[3] if len(sys.argv) > 3 else r"C:\Users\Public\dshaptics\gamerec"
SR, CHUNK = 48000, 30
os.makedirs(out, exist_ok=True)
log = open(os.path.join(out, "gamerec.log"), "a", encoding="utf-8")
def say(*a):
    log.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n"); log.flush()

def running():
    o = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace").stdout
    return proc.lower() in o.lower()

spk = sc.default_speaker()
mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
say("recording", spk.name, "for", minutes, "min while", proc, "runs")
end = time.time() + minutes * 60
try:
    with mic.recorder(samplerate=SR, channels=2, blocksize=4800) as r:
        while time.time() < end and running():
            t0 = time.time()
            a = np.concatenate([r.record(numframes=4800) for _ in range(CHUNK * 10)])
            name = os.path.join(out, f"rec_{t0:.2f}.wav")
            w = wave.open(name, "w"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
            say("saved", os.path.basename(name), "peak", float(np.abs(a).max().round(3)))
except Exception as e:
    say("recorder error", repr(e))
say("end")

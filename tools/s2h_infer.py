"""Run the Sound2Hap model (CHI '26, github.com/Iris1215/Sound2Hap) over a folder of game SFX.

usage: python3 s2h_infer.py <Sound2Hap_Models dir> <model .pth> <out dir> <in dir> [<in dir> ...]

Writes <out>/<name>.wav: model vibration, band-limited 20-400 Hz, 48 kHz mono, peak-normalised
(the model normalises every input, so loudness is restored later from <out>/levels.json, which
holds each source clip's original peak and RMS).
"""
import glob, json, os, sys, types, wave
import numpy as np
import torch
from scipy.signal import butter, sosfilt, resample_poly

models_dir, weights, out_dir, in_dirs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
sys.modules.setdefault("torchaudio", types.ModuleType("torchaudio"))   # encodec imports it only for file I/O helpers
sys.path.insert(0, os.path.join(models_dir, "encodec"))
from encodec.model import EncodecModel
from encodec.modules.seanet import SEANetDecoder

model = EncodecModel.encodec_model_24khz()
model.set_target_bandwidth(6.0)
old = model.decoder
model.decoder = SEANetDecoder(channels=1, dimension=old.dimension, n_filters=old.n_filters,
                              n_residual_layers=old.n_residual_layers, ratios=old.ratios,
                              activation="LeakyReLU", activation_params={"negative_slope": 0.2},
                              final_activation=None, norm="weight_norm", lstm=2)
# checkpoint metadata (epoch, losses) holds numpy scalars: allow just those types, keep weights_only loading
# (saved with numpy 1.x, so the pickle names the old "numpy.core" path)
torch.serialization.add_safe_globals([(np._core.multiarray.scalar, "numpy.core.multiarray.scalar"), np.dtype,
                                      type(np.dtype("float64")), type(np.dtype("float32")), type(np.dtype("int64"))])
ck = torch.load(weights, map_location="cpu")
model.load_state_dict(ck["model_state"] if isinstance(ck, dict) and "model_state" in ck else ck)
model.eval()

HP = butter(2, 20, "high", fs=24000, output="sos")
LP = butter(2, 400, "low", fs=24000, output="sos")

def load(path):
    w = wave.open(path)
    ch, sr = w.getnchannels(), w.getframerate()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch).astype(np.float32).mean(axis=1) / 32768
    return a, sr

os.makedirs(out_dir, exist_ok=True)
levels = {}
files = [f for d in in_dirs for f in sorted(glob.glob(os.path.join(d, "*.wav")))]
for n, f in enumerate(files):
    name = os.path.basename(f)
    if name in levels:
        continue
    a, sr = load(f)
    levels[name] = {"peak": float(np.abs(a).max()), "rms": float(np.sqrt(np.mean(a ** 2)))}
    x = resample_poly(a, 24000, sr).astype(np.float32) if sr != 24000 else a
    if np.abs(x).max() < 1e-5:
        continue
    x = x / np.abs(x).max()
    with torch.no_grad():
        t = torch.from_numpy(x)[None, None]
        z = model.encoder(t)
        q = model.quantizer(z, frame_rate=model.frame_rate).quantized
        v = model.decoder(q)[0, 0].numpy()[: len(x)]
    v = np.tanh(sosfilt(LP, sosfilt(HP, v)))
    v = resample_poly(v, 2, 1).astype(np.float32)            # 24k -> 48k
    v /= max(np.abs(v).max(), 1e-6)
    o = wave.open(os.path.join(out_dir, name), "w")
    o.setnchannels(1); o.setsampwidth(2); o.setframerate(48000)
    o.writeframes((v * 32767).astype(np.int16).tobytes()); o.close()
    if n % 50 == 0:
        print(f"{n}/{len(files)}", flush=True)
json.dump(levels, open(os.path.join(out_dir, "levels.json"), "w"))
print("done", len(levels))

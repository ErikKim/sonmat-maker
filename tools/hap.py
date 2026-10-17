import sys, numpy as np, sounddevice as sd
name, mode = sys.argv[1], sys.argv[2]   # name: "3-" or "4-", mode: haptic|speaker
dev = [i for i,d in enumerate(sd.query_devices()) if name in d['name'] and 'DualSense' in d['name']
       and d['max_output_channels']==4 and sd.query_hostapis(d['hostapi'])['name']=='Windows WASAPI'][0]
sr = 48000; t = np.arange(int(sr*2.0))/sr
if mode == 'haptic':   # 3 pulses of 80Hz on ch3/4
    sig = np.sin(2*np.pi*80*t) * ((t % 0.66) < 0.33) * 0.9
    out = np.zeros((len(t),4), np.float32); out[:,2] = sig; out[:,3] = sig
else:                  # 880Hz beep on ch1/2
    sig = np.sin(2*np.pi*880*t) * ((t % 0.5) < 0.15) * 0.5
    out = np.zeros((len(t),4), np.float32); out[:,0] = sig; out[:,1] = sig
sd.play(out, sr, device=dev, blocking=True)
print('played', mode, 'on', sd.query_devices(dev)['name'])

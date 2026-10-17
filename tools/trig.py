import sys, time, hid
key = sys.argv[1].lower()          # HID instance fragment, e.g. a&2ab5e2dd
mode = sys.argv[2] if len(sys.argv) > 2 else 'hard'
devs = [d for d in hid.enumerate(0x054C, 0x0CE6) if key in d['path'].decode().lower()]
print([d['path'] for d in devs])
h = hid.device(); h.open_path(devs[0]['path'])
def send(r2, l2):
    rep = bytearray(48); rep[0] = 0x02; rep[1] = 0x0C   # flags: R2 + L2 trigger effects
    rep[11:11+len(r2)] = bytes(r2); rep[22:22+len(l2)] = bytes(l2)
    print('wrote', h.write(bytes(rep)))
if mode == 'hard':   send([0x01, 0x00, 0xFF], [0x01, 0x00, 0xFF])        # full resistance from start
elif mode == 'weapon': send([0x25, 0x90, 0x00, 0x07], [0x25, 0x90, 0x00, 0x07])  # zone4..7 wall then snap release
elif mode == 'bow':  send([0x02, 0x40, 0xA0, 0xFF], [0x02, 0x40, 0xA0, 0xFF])  # wall in mid section
else:                send([0x05], [0x05])                                   # off
if mode != 'off':
    time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 15); send([0x05], [0x05])

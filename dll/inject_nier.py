import sys, os, subprocess, re, time
sys.path.insert(0, os.environ.get("DSHAPTICS_DIR", "."))
import hapticsd as h
out = subprocess.run(["tasklist", "/fi", "imagename eq NieRAutomata.exe", "/fo", "csv", "/nh"], capture_output=True, text=True, errors="replace").stdout
pid = int(re.search(r'"NieRAutomata.exe","(\d+)"', out).group(1))
if hasattr(h, "enable_debug_privilege"): print("debug privilege", h.enable_debug_privilege())
size0 = os.path.getsize(r"C:\Users\Public\dshaptics\events.log") if os.path.exists(r"C:\Users\Public\dshaptics\events.log") else 0
print("pid", pid, "inject", h.inject(pid, r"C:\Users\Public\dshaptics\nier\dshaptics_wwise_wide.dll"), "log size before", size0)
time.sleep(8)
print(open(r"C:\Users\Public\dshaptics\nier\dshaptics_wwise.log").read())
print("log grew by", os.path.getsize(r"C:\Users\Public\dshaptics\events.log") - size0)
open(r"C:\Users\Public\dshaptics\nier\start_offset.txt", "w").write(str(size0))

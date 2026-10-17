"""usage: python inject.py <dll path> [exe name]  - LoadLibraryW the DLL into the running game."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dshaptics as d
exe = sys.argv[2] if len(sys.argv) > 2 else d.GAME_EXE
d.GAME_EXE = exe
pid = d.game_pid()
print("pid", pid, "inject", d.inject(pid, os.path.abspath(sys.argv[1])) if pid else None)

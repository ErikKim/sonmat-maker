"""Shared by both ends of tools/deploy_pc.sh (run on the Mac and, over ssh, on the Windows PC).

    python pc_sync.py manifest <root>            -> json {relative path: [sha1, mtime]} of the code files
    python pc_sync.py backup <root> <list.txt>   -> zips the listed files that exist into _backup/<stamp>.zip
    python pc_sync.py build <root>               -> fetches the parts (hook DLLs, loader: tools/download/partfetch.py) and builds paktool

"Code files" = what the Mac owns. Sound folders (sounds/, the old pad_sfx*), built DLLs, parts/, logs and dll/sigs*.txt belong to
the PC and are never listed, so a deploy cannot overwrite them.
"""
import glob, hashlib, json, os, subprocess, sys, time, zipfile

INCLUDE = ["*.py", "*.bat", "*.ico", "README.md", "ROADMAP.md", "profiles/**", "data/**", "tools/**", "mods/**", "docs/**",
           "app/src/**", "app/profiles/**", "app/mock/**"]
SKIP = ("__pycache__", "/bin/", "/obj/", ".DS_Store", ".bak", "/._")
# the old daemons were removed from the PC on 2026-10-07: never send them
# local to each machine (keys, folders) and tools fetched on that machine: never synced
SKIP += ("/tools/config.json", "/tools/fetched/")
SKIP += ("/dshaptics.py", "/ue4haptics.py", "/run.bat", "/run_ue4.bat", "/tclick.py", "/tvib.py")

def files(root):
    out = set()
    for pat in INCLUDE:
        for p in glob.glob(os.path.join(root, pat), recursive=True):
            rel = os.path.relpath(p, root).replace("\\", "/")
            if os.path.isfile(p) and not any(s in "/" + rel for s in SKIP):
                out.add(rel)
    return sorted(out)

def manifest(root):
    return {r: [hashlib.sha1(open(os.path.join(root, r), "rb").read()).hexdigest(), int(os.path.getmtime(os.path.join(root, r)))]
            for r in files(root)}

def backup(root, listing):
    names = [l.strip() for l in open(listing, encoding="utf-8") if l.strip()]
    have = [n for n in names if os.path.isfile(os.path.join(root, n))]
    if not have:
        print("backup: nothing to save"); return
    os.makedirs(os.path.join(root, "_backup"), exist_ok=True)
    z = os.path.join(root, "_backup", time.strftime("%Y%m%d_%H%M%S") + ".zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for n in have:
            f.write(os.path.join(root, n), n)
    print(f"backup: {len(have)} files -> {z}")

def build(root):
    def run(title, cmd, cwd):
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace", shell=True)
            tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-6:]
            print(f"== {title}: {'OK' if r.returncode == 0 else 'FAILED (%d)' % r.returncode}")
            for l in tail: print("   " + l)
        except Exception as e:
            print(f"== {title}: could not run ({e})")
    # the hook DLLs and the loader are parts now (sonmat-loader, sonmat-hook-*: each its own repo, 10-21); private repos
    # need SONMAT_GITHUB_TOKEN on the PC. A PC copy that still has its own dll/ keeps using it when no part is there
    run("parts (tools/download partfetch all)", f'"{sys.executable}" tools/download partfetch all', root)
    run("paktool (dotnet build)", "dotnet build -c Release -nologo -v q", os.path.join(root, "tools", "paktool"))
    run("app (dotnet build)", "dotnet build -c Release -nologo -v q", os.path.join(root, "app", "src"))
    run("hapticsd imports", f'"{sys.executable}" -c "import numpy, sounddevice, hid, scipy; print(1)"', root)

if __name__ == "__main__":
    cmd, root = sys.argv[1], sys.argv[2]
    if cmd == "manifest": print(json.dumps(manifest(root)))
    elif cmd == "backup": backup(root, sys.argv[3])
    elif cmd == "build": build(root)

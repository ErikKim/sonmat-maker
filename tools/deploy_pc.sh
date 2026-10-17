#!/bin/sh
# Copy the Mac's code to the Windows PC and build there. Clip folders, built DLLs and sigs stay untouched.
#   tools/deploy_pc.sh          report only: what differs, what the PC has that is newer
#   tools/deploy_pc.sh --go     backup on the PC (_backup/<stamp>.zip) -> copy -> build loader, paktool, app
# Needs the PC on and reachable (ssh key already registered). Does not touch the scheduled tasks.
set -e
PC="${PC:?set PC=user@host}"
DST="${DST:?set DST=<folder on the PC>}"
PY='C:\Python314\python.exe'
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
ssh -o ConnectTimeout=5 "$PC" "echo ok" >/dev/null || { echo "PC 에 연결할 수 없습니다 ($PC)"; exit 1; }
scp -q "$HERE/tools/pc_sync.py" "$PC:pc_sync.py"
python3 "$HERE/tools/pc_sync.py" manifest "$HERE" > "$TMP/mac.json"
ssh "$PC" "$PY pc_sync.py manifest $DST" > "$TMP/pc.json"
python3 - "$TMP" <<'PY'
import json, sys, os
t = sys.argv[1]
mac, pc = json.load(open(t + "/mac.json")), json.load(open(t + "/pc.json"))
send = [f for f in mac if f not in pc or pc[f][0] != mac[f][0]]
newer = [f for f in send if f in pc and pc[f][1] > mac[f][1]]
only_pc = [f for f in pc if f not in mac]
open(t + "/send.txt", "w").write("\n".join(send) + "\n")
print(f"보낼 파일 {len(send)}개 (새 파일 {sum(f not in pc for f in send)}, 바뀐 파일 {sum(f in pc for f in send)})")
for f in send: print("  ", "+" if f not in pc else "~", f)
if newer:
    print(f"\n주의: PC 쪽이 더 최근에 고쳐진 파일 {len(newer)}개 (덮어쓰면 PC 수정이 사라집니다. 백업 zip 에는 남습니다)")
    for f in newer: print("   !", f)
if only_pc:
    print(f"\nPC 에만 있는 코드 파일 {len(only_pc)}개 (건드리지 않습니다)")
    for f in only_pc[:40]: print("   ?", f)
PY
[ "$1" = "--go" ] || { echo; echo "여기까지는 확인만 했습니다. 실제로 보내려면: tools/deploy_pc.sh --go"; exit 0; }
[ -s "$TMP/send.txt" ] || { echo "보낼 것이 없습니다"; exit 0; }
scp -q "$TMP/send.txt" "$PC:send.txt"
ssh "$PC" "$PY pc_sync.py backup $DST send.txt"
(cd "$HERE" && COPYFILE_DISABLE=1 tar --no-xattrs -cf "$TMP/code.tar" -T "$TMP/send.txt")
scp -q "$TMP/code.tar" "$PC:code.tar"
ssh "$PC" "tar -xf code.tar -C $DST && del code.tar send.txt"
echo "복사 끝. 빌드:"
ssh "$PC" "$PY pc_sync.py build $DST" | iconv -f CP949 -t UTF-8 2>/dev/null || true

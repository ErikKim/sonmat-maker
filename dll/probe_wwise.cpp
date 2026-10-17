// probe_wwise.dll - find which candidate function is AK::SoundEngine::PostEvent(ID, ...) / SetSwitch.
//
// Hooks every RVA listed in <dll name>_cands.txt (from find_ak.py) and records the first three integer
// arguments of each call to <dll name>.log ("<cand> <a> <b> <c>"). The candidate whose first argument
// is a known event ID (dll/event_ids.json) is PostEvent. Hooks only store integers into a ring
// buffer (no CRT, no SSE), so float arguments in xmm registers reach the original untouched.

#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
#include "MinHook.h"

using Fn = uint64_t(*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);

constexpr int MAX_CANDS = 256;
constexpr int RING = 1 << 16;
struct Rec { volatile LONG64 seq; uint64_t cand, a, b, c; };
static Rec g_ring[RING];
static volatile LONG64 g_head = 0;
static Fn g_orig[MAX_CANDS];

template <int N>
static uint64_t hk(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h) {
    LONG64 s = InterlockedIncrement64(&g_head);
    Rec& r = g_ring[s & (RING - 1)];
    r.cand = N; r.a = a; r.b = b; r.c = c;
    InterlockedExchange64(&r.seq, s);
    return g_orig[N](a, b, c, d, e, f, g, h);
}

template <int... I> struct Table { static constexpr void* v[] = { (void*)&hk<I>... }; };
template <int N, int... I> struct Make : Make<N - 1, N - 1, I...> {};
template <int... I> struct Make<0, I...> { using type = Table<I...>; };
using Hooks = Make<MAX_CANDS>::type;

// Files are named after the DLL itself, so several copies (probe_wwise.dll, probe2_wwise.dll ...) can
// be loaded side by side: <name>_cands.txt in, <name>_status.log and <name>.log out.
static std::string dll_stem(HMODULE self) {
    char path[MAX_PATH]; GetModuleFileNameA(self, path, MAX_PATH);
    std::string s(path); return s.substr(0, s.find_last_of('.'));
}

static DWORD WINAPI init(LPVOID self) {
    std::string stem = dll_stem((HMODULE)self);
    FILE* status = fopen((stem + "_status.log").c_str(), "w");
    FILE* list = fopen((stem + "_cands.txt").c_str(), "r");
    auto base = (uint8_t*)GetModuleHandleW(nullptr);
    if (MH_Initialize() != MH_OK) { if (status) fputs("MinHook init failed\n", status); return 0; }
    int n = 0; char line[128];
    while (list && n < MAX_CANDS && fgets(line, sizeof line, list)) {
        unsigned long long rva = strtoull(line, nullptr, 16);
        if (!rva) continue;
        void* at = base + rva;
        bool ok = MH_CreateHook(at, Hooks::v[n], (void**)&g_orig[n]) == MH_OK && MH_EnableHook(at) == MH_OK;
        if (status) { fprintf(status, "%d %llx %s\n", n, rva, ok ? "hooked" : "FAILED"); fflush(status); }
        n++;
    }
    if (list) fclose(list);
    if (status) fclose(status);

    FILE* out = fopen((stem + ".log").c_str(), "w");
    LONG64 tail = 0; int counts[MAX_CANDS] = {};
    for (;;) {
        Sleep(50);
        LONG64 head = g_head;
        if (head - tail > RING) tail = head - RING;           // fell behind: drop the oldest
        for (; tail < head; tail++) {
            Rec& r = g_ring[(tail + 1) & (RING - 1)];
            if (r.seq != tail + 1) continue;
            if (counts[r.cand]++ >= 3000) continue;           // enough samples per candidate
            fprintf(out, "%llu %llu %llu %llu\n", r.cand, r.a, r.b, r.c);
        }
        fflush(out);
    }
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        CreateThread(nullptr, 0, init, h, 0, nullptr);
    }
    return TRUE;
}

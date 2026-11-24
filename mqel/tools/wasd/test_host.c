/* Test host for xinput9_1_0.dll: loads it like the game does (from its own
   folder), prints the controller state for a few seconds and keeps the
   control endpoint running. Usage: test_host.exe [seconds] */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { WORD b; BYTE lt, rt; SHORT lx, ly, rx, ry; } XPAD;
typedef struct { DWORD packet; XPAD pad; } XSTATE;
typedef struct { BYTE Type, SubType; WORD Flags; XPAD pad; WORD l, r; } XCAPS;
typedef DWORD (WINAPI *PGetState)(DWORD, XSTATE *);
typedef DWORD (WINAPI *PGetCaps)(DWORD, DWORD, XCAPS *);

int main(int argc, char **argv)
{
    int secs = argc > 1 ? atoi(argv[1]) : 5, i;
    HMODULE h = LoadLibraryA("xinput9_1_0.dll");
    PGetState gs;
    PGetCaps gc;
    XCAPS caps;
    XSTATE st;
    if (!h) { printf("load failed %lu\n", GetLastError()); return 1; }
    gs = (PGetState)GetProcAddress(h, "XInputGetState");
    gc = (PGetCaps)GetProcAddress(h, "XInputGetCapabilities");
    printf("exports: %p %p %p\n", (void *)gs, (void *)gc, (void *)GetProcAddress(h, "XInputSetState"));
    printf("caps(0) = %lu type=%d\n", gc(0, 0, &caps), caps.Type);
    printf("caps(1) = %lu\n", gc(1, 0, &caps));
    for (i = 0; i < secs * 4; i++) {
        DWORD r = gs(0, &st);
        printf("state r=%lu packet=%lu lx=%d ly=%d\n", r, st.packet, st.pad.lx, st.pad.ly);
        fflush(stdout);
        Sleep(250);
    }
    return 0;
}

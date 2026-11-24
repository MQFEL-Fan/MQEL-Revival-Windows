/* Message-rewrite test for xinput9_1_0.dll (WASD.ini ForceKeys=1,
   AttackOnly=0): while WASD steers, "real" mouse moves posted to the game
   window must arrive with the WASD target's coordinates. No input is
   simulated. */
#include <windows.h>
#include <stdio.h>

static int moves, rewritten;
static LRESULT CALLBACK proc(HWND w, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_MOUSEMOVE) {
        moves++;
        if ((short)LOWORD(lp) != 77 || (short)HIWORD(lp) != 66) rewritten++;
        if (moves <= 3 || moves % 50 == 0) printf("  WM_MOUSEMOVE at (%d,%d) wp=%d\n", (short)LOWORD(lp), (short)HIWORD(lp), (int)wp);
    }
    return DefWindowProcA(w, m, wp, lp);
}

int main(void)
{
    WNDCLASSA wc;
    HWND w;
    MSG msg;
    DWORD end;
    HMODULE h = LoadLibraryA("xinput9_1_0.dll");
    if (!h) { printf("dll missing\n"); return 1; }
    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = proc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "wasdsub";
    RegisterClassA(&wc);
    w = CreateWindowExA(0, "wasdsub", "wasd subclass test", WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_MINIMIZE,
                        100, 100, 800, 600, NULL, NULL, wc.hInstance, NULL);
    ShowWindow(w, SW_SHOWNOACTIVATE);
    end = GetTickCount() + 1500;
    while (GetTickCount() < end) {
        PostMessageA(w, WM_MOUSEMOVE, 0, MAKELPARAM(77, 66)); /* the "real" mouse */
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) DispatchMessageA(&msg);
        Sleep(5);
    }
    printf("mouse moves seen: %d, not at the real position: %d\n", moves, rewritten);
    DestroyWindow(w);
    return 0;
}

/* Movement test for xinput9_1_0.dll: a window that polls XInput every frame
   like the game, presses W (SendInput) while it has focus and logs the mouse
   messages it gets plus what GetCursorPos / GetKeyState(VK_LBUTTON) return
   (both go through this exe's import table, which the DLL hooks).
   Needs "attack" mode: run with the DLL's AttackOnly=0 or POST /attack 1. */
#include <windows.h>
#include <stdio.h>

typedef DWORD (WINAPI *PGetState)(DWORD, void *);
static int downs, ups, moves;
__declspec(noinline) static void set_cursor(int x, int y) { SetCursorPos(x, y); }
static POINT last_msg;

static LRESULT CALLBACK proc(HWND w, UINT m, WPARAM wp, LPARAM lp)
{
    if (m == WM_LBUTTONDOWN) { downs++; last_msg.x = (short)LOWORD(lp); last_msg.y = (short)HIWORD(lp); }
    if (m == WM_LBUTTONUP) ups++;
    if (m == WM_MOUSEMOVE && (wp & MK_LBUTTON)) moves++;
    return DefWindowProcA(w, m, wp, lp);
}

static void key(WORD vk, BOOL up)
{
    INPUT in;
    memset(&in, 0, sizeof(in));
    in.type = INPUT_KEYBOARD;
    in.ki.wVk = vk;
    in.ki.dwFlags = up ? KEYEVENTF_KEYUP : 0;
    SendInput(1, &in, sizeof(in));
}

static void frames(PGetState gs, int n, const char *label)
{
    BYTE st[16];
    MSG msg;
    int i;
    for (i = 0; i < n; i++) {
        gs(0, st);
        while (PeekMessageA(&msg, NULL, 0, 0, PM_REMOVE)) DispatchMessageA(&msg);
        Sleep(16);
    }
    {
        POINT p; RECT rc; HWND w = GetForegroundWindow();
        GetCursorPos(&p);
        ScreenToClient(w, &p);
        GetClientRect(w, &rc);
        printf("%s: down=%d up=%d moves=%d lastDown=(%ld,%ld) cursor(client)=(%ld,%ld) LBUTTON=%d client=%ldx%ld\n",
               label, downs, ups, moves, last_msg.x, last_msg.y, p.x, p.y,
               (GetKeyState(VK_LBUTTON) & 0x8000) ? 1 : 0, rc.right, rc.bottom);
    }
}

int main(int argc, char **argv)
{
    WNDCLASSA wc;
    HWND w;
    HMODULE h = LoadLibraryA("xinput9_1_0.dll");
    PGetState gs = h ? (PGetState)GetProcAddress(h, "XInputGetState") : NULL;
    if (!gs) { printf("dll missing\n"); return 1; }
    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = proc;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "wasdtest";
    RegisterClassA(&wc);
    w = CreateWindowExA(0, "wasdtest", "wasd test", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 100, 100, 800, 600, NULL, NULL, wc.hInstance, NULL);
    key(VK_MENU, FALSE); key(VK_MENU, TRUE); /* lets SetForegroundWindow work */
    SetForegroundWindow(w);
    printf("foreground is test window: %d\n", GetForegroundWindow() == w);
    { POINT c = {150, 450}; ClientToScreen(w, &c); SetCursorPos(c.x, c.y); } /* real cursor over the window */
    frames(gs, 20, "idle   ");
    if (argc > 1) { /* click held first, then WASD steers, then back to the click */
        INPUT in; memset(&in, 0, sizeof(in)); in.type = INPUT_MOUSE;
        in.mi.dwFlags = MOUSEEVENTF_LEFTDOWN; SendInput(1, &in, sizeof(in));
        frames(gs, 10, "L held ");
        key('W', FALSE);
        frames(gs, 15, "L+W    ");
        key('W', TRUE);
        frames(gs, 10, "L, W up");
        in.mi.dwFlags = MOUSEEVENTF_LEFTUP; SendInput(1, &in, sizeof(in));
        frames(gs, 10, "L up   ");
        DestroyWindow(w);
        return 0;
    }
    key('W', FALSE);
    frames(gs, 20, "W held ");
    {
        /* GetCursorInfo isn't hooked: it shows the real cursor */
        CURSORINFO before, after;
        before.cbSize = after.cbSize = sizeof(CURSORINFO);
        GetCursorInfo(&before);
        set_cursor(5, 5); /* the game pushing its (fake) cursor back */
        GetCursorInfo(&after);
        printf("SetCursorPos while moving blocked: %d\n",
               before.ptScreenPos.x == after.ptScreenPos.x && before.ptScreenPos.y == after.ptScreenPos.y);
    }
    key('1', FALSE);
    frames(gs, 5, "1 down ");
    key('1', TRUE);
    frames(gs, 5, "1 up+80");
    frames(gs, 25, "1 up+500");
    {
        INPUT in; memset(&in, 0, sizeof(in)); in.type = INPUT_MOUSE;
        in.mi.dwFlags = MOUSEEVENTF_LEFTDOWN; SendInput(1, &in, sizeof(in));
        frames(gs, 10, "real L ");
        in.mi.dwFlags = MOUSEEVENTF_LEFTUP; SendInput(1, &in, sizeof(in));
        frames(gs, 20, "L up   ");
    }
    key('D', FALSE);
    frames(gs, 10, "W+D    ");
    key('W', TRUE);
    key('D', TRUE);
    frames(gs, 10, "release");
    DestroyWindow(w);
    return 0;
}

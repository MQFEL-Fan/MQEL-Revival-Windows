/*
 * MQEL WASD helper: drop-in xinput9_1_0.dll for MightyQuest.exe (32-bit).
 *
 * The game has no keyboard "move" action, and the PC build ignores the
 * gamepad stick for movement (tested 2026-11-20: the game polls XInput slot 0
 * every frame, full stick deflection and a real Steam controller both did
 * nothing). Movement works by holding the left mouse button: the hero walks
 * towards the cursor. So this DLL makes WASD hold the left button at a point
 * next to the hero in that direction (screen-relative: W = up the screen).
 *
 * The DLL is loaded by the game (static import of XINPUT9_1_0.dll; all XInput
 * calls are passed through to the real Windows DLL). XInputGetState runs every
 * frame on the game thread, so it drives the movement. Two methods (WASD.ini
 * Mode, also in the Keybind panel):
 *   1 = virtual cursor (default): left-button and mouse-move messages to the
 *       game window, plus in-process hooks of GetCursorPos / GetKeyState /
 *       GetKeyboardState, so the game "sees" the button held at the target
 *       while the real cursor stays where it is.
 *   2 = real cursor: moves the real cursor to the target and presses the real
 *       left button (SendInput), restoring the cursor on release.
 *
 * Movement only runs during an attack (the UI patch reports attack start/end,
 * WASD.ini AttackOnly=0 turns that off), while the game has focus, no text
 * field has focus (UI patch) and Alt isn't held. Ctrl+WASD = move without
 * attacking (Ctrl is that game key), Shift+WASD = hold the ground.
 *
 * Local control endpoint for the in-game Keybind panel (UI patch 12):
 *   http://127.0.0.1:27631   (only answers the game UI, Origin http://localhost)
 *   GET  /state            -> {"enabled":..,"up":VK,..,"pendingBinds":bool}
 *   POST /config           body "enabled=1&up=87&left=65&down=83&right=68&mode=1&attackonly=1"
 *   GET  /binds            -> the ShortcutsDictionary object (pending one if any)
 *   POST /binds            body = new ShortcutsDictionary object (JSON)
 *   POST /binds/discard    drop the pending key binds
 *   POST /typing           body "1" / "0"
 *   POST /attack           body "1" / "0" (attack started / ended)
 *   POST /quit             close the game (update countdown), killed after 2 s
 *   GET  /debug            diagnostics (also written to WASD.log every 5 s)
 *   POST /config           also "lootplayer=1": the pet's loot filter applies to the
 *                          hero too (2026-11-24, Setting Mod panel)
 *
 * Loot filter for the hero: the game exe (level60.patch_exe, LootComponent::
 * CollectLoot) asks XInputGetCapabilities(0x4D51454C "MQEL", 0, buf) whether
 * the filter is on: 0x4D510001 = on, 0x4D510000 = off. Real XInput (helper not
 * loaded) answers an error for that index: off.
 *
 * The game keeps its key binds in memory and writes CustomUserSettings.json
 * itself, so edited binds are stored as CustomUserSettings.wasd-pending.json
 * and merged into CustomUserSettings.json when this DLL loads at the next
 * game start, before the game reads the file. Movement keys apply live.
 *
 * Settings: WASD.ini next to the exe.
 */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "winmm.lib")
#include <mmsystem.h>

#define WASD_PORT 27631

/* ---- XInput types (own copies, so the SDK prototypes don't clash) ---- */
typedef struct {
    WORD wButtons;
    BYTE bLeftTrigger, bRightTrigger;
    SHORT sThumbLX, sThumbLY, sThumbRX, sThumbRY;
} XPAD;
typedef struct { DWORD dwPacketNumber; XPAD Gamepad; } XSTATE;
typedef struct { WORD wLeftMotorSpeed, wRightMotorSpeed; } XVIB;
typedef struct { BYTE Type, SubType; WORD Flags; XPAD Gamepad; XVIB Vibration; } XCAPS;

typedef DWORD (WINAPI *PGetState)(DWORD, XSTATE *);
typedef DWORD (WINAPI *PSetState)(DWORD, XVIB *);
typedef DWORD (WINAPI *PGetCaps)(DWORD, DWORD, XCAPS *);

static PGetState real_get_state;
static PSetState real_set_state;
static PGetCaps real_get_caps;
static INIT_ONCE real_once = INIT_ONCE_STATIC_INIT;

/* ---- settings ---- */
static volatile LONG g_enabled = 1;
static volatile LONG g_vk[4] = {'W', 'A', 'S', 'D'}; /* up, left, down, right */
static volatile LONG g_mode = 1;        /* 1 virtual cursor, 2 real cursor */
static volatile LONG g_attack_only = 1;
static volatile LONG g_layout_offered = 0; /* first-run KEYS panel shown */
static volatile LONG g_layout_applied = 0; /* WASD layout written into CustomUserSettings.json once */
static volatile LONG g_radius = 10;     /* % of window height */
static volatile LONG g_center_y = 52;   /* hero position, % of window height */
static volatile LONG g_typing = 0;
static volatile DWORD g_typing_since = 0;
static volatile LONG g_in_attack = 0;
static volatile LONG g_loot_player = 0; /* WASD.ini LootPlayer=1: pet loot filter for the hero too */
static volatile LONG d_loot_asks = 0;   /* exe asked for the loot filter */
static LONG g_accept_injected = 0; /* WASD.ini AcceptInjected=1: tests only */
static LONG g_force_keys = 0;      /* WASD.ini ForceKeys=<bitmask 1 up 2 left 4 down 8 right>: tests only */

/* diagnostics (GET /debug, WASD.log, bottom of the Keybind panel) */
static volatile LONG d_gs_calls, d_focus, d_keys, d_key_frames, d_blocked_focus, d_blocked_typing,
    d_blocked_alt, d_blocked_attack, d_blocked_window, d_moved_frames, d_presses, d_attack_msgs, d_attack_on;
static volatile LONG d_hook_cursor, d_hook_keystate, d_hook_kbstate, d_hooks_installed;
static volatile LONG d_hook_setcursor, d_takeovers, d_key_pauses, d_ll_hooks, d_rewritten, d_subclassed;

static wchar_t g_bin[MAX_PATH];      /* ...\GameData\Bin\ */
static wchar_t g_ini[MAX_PATH];
static wchar_t g_log[MAX_PATH];
static wchar_t g_cus[MAX_PATH];      /* CustomUserSettings.json */
static wchar_t g_pending[MAX_PATH];  /* CustomUserSettings.wasd-pending.json */
static wchar_t g_backup[MAX_PATH];

static CRITICAL_SECTION g_file_lock;

/* ------------------------------------------------------------------ */
/* real XInput                                                         */
/* ------------------------------------------------------------------ */
static BOOL CALLBACK load_real(PINIT_ONCE once, PVOID p, PVOID *ctx)
{
    wchar_t path[MAX_PATH];
    HMODULE h;
    UINT n = GetSystemDirectoryW(path, MAX_PATH);
    (void)once; (void)p; (void)ctx;
    if (n == 0 || n > MAX_PATH - 20) return TRUE;
    wcscat(path, L"\\xinput9_1_0.dll");
    h = LoadLibraryW(path); /* 32-bit process: System32 -> SysWOW64 */
    if (!h) {
        GetSystemDirectoryW(path, MAX_PATH);
        wcscat(path, L"\\xinput1_4.dll");
        h = LoadLibraryW(path);
    }
    if (h) {
        real_get_state = (PGetState)GetProcAddress(h, "XInputGetState");
        real_set_state = (PSetState)GetProcAddress(h, "XInputSetState");
        real_get_caps = (PGetCaps)GetProcAddress(h, "XInputGetCapabilities");
    }
    return TRUE;
}

static void ensure_real(void) { InitOnceExecuteOnce(&real_once, load_real, NULL, NULL); }

/* ------------------------------------------------------------------ */
/* hooks (import table of MightyQuest.exe)                             */
/* ------------------------------------------------------------------ */
typedef BOOL (WINAPI *PGetCursorPos)(LPPOINT);
typedef SHORT (WINAPI *PGetKeyState)(int);
typedef BOOL (WINAPI *PGetKeyboardState)(PBYTE);
typedef BOOL (WINAPI *PSetCursorPos)(int, int);
static PGetCursorPos orig_GetCursorPos;      /* set in DllMain */
static PGetKeyState orig_GetKeyState;
static PGetKeyboardState orig_GetKeyboardState;
static PSetCursorPos orig_SetCursorPos;
static volatile DWORD mv_last_active; /* tick when the fake cursor was last used */

/* movement state, written on the game thread */
static volatile LONG mv_active = 0;   /* left button held by us */
static POINT mv_target;               /* client coordinates */
static HWND mv_hwnd;
static POINT mv_saved_cursor;         /* mode 2 */
static BOOL g_real_l, g_real_r;       /* real mouse buttons held (input hooks) */
static BOOL g_wasd_priority;          /* WASD pressed after the real left button */

/* The game also aims with the coordinates in WM_MOUSEMOVE. The real mouse
   sends those far more often than our updates, so while WASD steers every
   mouse move reaching the game window is rewritten to the WASD target (the
   real cursor still moves freely on screen). */
#define WASD_PROP "mqel_wasd_wndproc"
/* 2026-11-23: subclass with the W functions when the game window is a
   Unicode window: SetWindowLongPtrA(GWLP_WNDPROC) turned it into an ANSI
   window (suspected cause of the blank taskbar icon, see game_icon) */
static LRESULT CALLBACK wasd_wndproc(HWND h, UINT m, WPARAM wp, LPARAM lp)
{
    WNDPROC orig = (WNDPROC)GetPropA(h, WASD_PROP);
    BOOL uni = IsWindowUnicode(h);
    if (m == WM_MOUSEMOVE && mv_active && g_mode == 1 && h == mv_hwnd) {
        lp = MAKELPARAM(mv_target.x, mv_target.y);
        wp |= MK_LBUTTON;
        d_rewritten++;
    }
    if (m == WM_NCDESTROY && orig) {
        if (uni) SetWindowLongPtrW(h, GWLP_WNDPROC, (LONG_PTR)orig);
        else SetWindowLongPtrA(h, GWLP_WNDPROC, (LONG_PTR)orig);
        RemovePropA(h, WASD_PROP);
    }
    if (uni) return orig ? CallWindowProcW(orig, h, m, wp, lp) : DefWindowProcW(h, m, wp, lp);
    return orig ? CallWindowProcA(orig, h, m, wp, lp) : DefWindowProcA(h, m, wp, lp);
}

static void subclass_window(HWND w)
{
    WNDPROC cur;
    BOOL uni;
    if (!w || GetPropA(w, WASD_PROP)) return;
    uni = IsWindowUnicode(w);
    cur = (WNDPROC)(uni ? GetWindowLongPtrW(w, GWLP_WNDPROC) : GetWindowLongPtrA(w, GWLP_WNDPROC));
    if (!cur || cur == wasd_wndproc) return;
    SetPropA(w, WASD_PROP, (HANDLE)cur);
    if (uni) SetWindowLongPtrW(w, GWLP_WNDPROC, (LONG_PTR)wasd_wndproc);
    else SetWindowLongPtrA(w, GWLP_WNDPROC, (LONG_PTR)wasd_wndproc);
    d_subclassed++;
}

/* Game logo in the taskbar (2026-11-23): players saw a blank page icon for
   the game window. Give the window the exe's own icon (first RT_GROUP_ICON),
   big and small, once per window. */
static BOOL CALLBACK first_icon(HMODULE m, LPCWSTR type, LPWSTR name, LONG_PTR out)
{
    (void)m; (void)type;
    *(LPCWSTR *)out = IS_INTRESOURCE(name) ? name : _wcsdup(name);
    return FALSE;
}
static volatile LONG d_icon_set = 0;
static void game_icon(HWND w)
{
    static HWND done;
    static HICON big, small_;
    LPCWSTR name = NULL;
    DWORD_PTR r;
    if (!w || w == done) return;
    if (!big) {
        HMODULE exe = GetModuleHandleW(NULL);
        EnumResourceNamesW(exe, (LPCWSTR)RT_GROUP_ICON, first_icon, (LONG_PTR)&name);
        if (!name) { done = w; return; }
        big = (HICON)LoadImageW(exe, name, IMAGE_ICON, GetSystemMetrics(SM_CXICON), GetSystemMetrics(SM_CYICON), 0);
        small_ = (HICON)LoadImageW(exe, name, IMAGE_ICON, GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), 0);
    }
    done = w;
    if (big) SendMessageTimeoutW(w, WM_SETICON, ICON_BIG, (LPARAM)big, SMTO_ABORTIFHUNG, 1000, &r);
    if (small_) SendMessageTimeoutW(w, WM_SETICON, ICON_SMALL, (LPARAM)small_, SMTO_ABORTIFHUNG, 1000, &r);
    if (big) d_icon_set++;
}

static BOOL WINAPI hook_GetCursorPos(LPPOINT pt)
{
    BOOL r = orig_GetCursorPos(pt);
    if (r && pt && mv_active && g_mode == 1 && mv_hwnd) {
        POINT p = mv_target;
        ClientToScreen(mv_hwnd, &p);
        *pt = p;
        d_hook_cursor++;
    }
    return r;
}

static SHORT WINAPI hook_GetKeyState(int vk)
{
    SHORT r = orig_GetKeyState(vk);
    if (vk == VK_LBUTTON && mv_active && g_mode == 1) { r |= (SHORT)0x8000; d_hook_keystate++; }
    return r;
}

/* The game pushes its cursor position back to Windows. While WASD moves,
   that position is the fake target, which would drag the real cursor there:
   ignore those calls (and for a moment after, until the game has read the
   real position again). */
static BOOL WINAPI hook_SetCursorPos(int x, int y)
{
    if (g_mode == 1 && (mv_active || GetTickCount() - mv_last_active < 150)) { d_hook_setcursor++; return TRUE; }
    return orig_SetCursorPos(x, y);
}

static BOOL WINAPI hook_GetKeyboardState(PBYTE keys)
{
    BOOL r = orig_GetKeyboardState(keys);
    if (r && keys && mv_active && g_mode == 1) { keys[VK_LBUTTON] |= 0x80; d_hook_kbstate++; }
    return r;
}

static void patch_iat(HMODULE mod)
{
    BYTE *base = (BYTE *)mod;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR *imp;
    if (!dir.VirtualAddress) return;
    for (imp = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); imp->Name; imp++) {
        IMAGE_THUNK_DATA *names, *funcs;
        if (_stricmp((char *)(base + imp->Name), "USER32.dll") != 0) continue;
        names = (IMAGE_THUNK_DATA *)(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        funcs = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; names->u1.AddressOfData; names++, funcs++) {
            const char *fn;
            void *hook = NULL;
            DWORD old;
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
            fn = (const char *)((IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData))->Name;
            if (strcmp(fn, "GetCursorPos") == 0) { hook = hook_GetCursorPos; if (funcs->u1.Function != (ULONG_PTR)hook) orig_GetCursorPos = (PGetCursorPos)funcs->u1.Function; }
            else if (strcmp(fn, "GetKeyState") == 0) { hook = hook_GetKeyState; if (funcs->u1.Function != (ULONG_PTR)hook) orig_GetKeyState = (PGetKeyState)funcs->u1.Function; }
            else if (strcmp(fn, "SetCursorPos") == 0) { hook = hook_SetCursorPos; if (funcs->u1.Function != (ULONG_PTR)hook) orig_SetCursorPos = (PSetCursorPos)funcs->u1.Function; }
            else if (strcmp(fn, "GetKeyboardState") == 0) { hook = hook_GetKeyboardState; if (funcs->u1.Function != (ULONG_PTR)hook) orig_GetKeyboardState = (PGetKeyboardState)funcs->u1.Function; }
            if (!hook || funcs->u1.Function == (ULONG_PTR)hook) continue;
            if (VirtualProtect(&funcs->u1.Function, sizeof(void *), PAGE_READWRITE, &old)) {
                funcs->u1.Function = (ULONG_PTR)hook;
                VirtualProtect(&funcs->u1.Function, sizeof(void *), old, &old);
                d_hooks_installed++;
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* keyboard -> held left button                                        */
/* ------------------------------------------------------------------ */
static BOOL CALLBACK find_game_window(HWND w, LPARAM lp)
{
    DWORD pid = 0;
    RECT r;
    HWND *best = (HWND *)lp;
    GetWindowThreadProcessId(w, &pid);
    if (pid != GetCurrentProcessId() || !IsWindowVisible(w) || GetWindow(w, GW_OWNER)) return TRUE;
    GetClientRect(w, &r);
    if (r.right * r.bottom > 0) {
        RECT b;
        if (!*best) *best = w;
        else { GetClientRect(*best, &b); if (r.right * r.bottom > b.right * b.bottom) *best = w; }
    }
    return TRUE;
}

static HWND game_window(void)
{
    static HWND cached;
    static DWORD tick;
    if (cached && IsWindow(cached) && GetTickCount() - tick < 2000) return cached;
    cached = NULL;
    EnumWindows(find_game_window, (LPARAM)&cached);
    tick = GetTickCount();
    return cached;
}

static BOOL pid_is_game(DWORD pid)
{
    wchar_t name[MAX_PATH];
    DWORD n = MAX_PATH;
    HANDLE h;
    BOOL ok = FALSE;
    if (pid == GetCurrentProcessId()) return TRUE;
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return FALSE;
    if (QueryFullProcessImageNameW(h, 0, name, &n)) {
        wchar_t *b = wcsrchr(name, L'\\');
        b = b ? b + 1 : name;
        ok = _wcsicmp(b, L"mightyquest-ui.exe") == 0 || _wcsicmp(b, L"MightyQuest.exe") == 0;
    }
    CloseHandle(h);
    return ok;
}

/* Foreground window belongs to the game (or its CEF UI processes). Cached
   for 250 ms: XInputGetState runs every frame. */
static BOOL game_has_focus(void)
{
    static DWORD last_tick, last_pid;
    static BOOL last_ok;
    DWORD pid = 0, now = GetTickCount();
    HWND fg = GetForegroundWindow(), root;
    if (!fg) return FALSE;
    GetWindowThreadProcessId(fg, &pid);
    if (pid == last_pid && now - last_tick < 250) return last_ok;
    last_ok = pid_is_game(pid);
    if (!last_ok) {
        root = GetAncestor(fg, GA_ROOTOWNER);
        if (root && root != fg) { DWORD p2 = 0; GetWindowThreadProcessId(root, &p2); last_ok = pid_is_game(p2); }
    }
    last_pid = pid; last_tick = now;
    return last_ok;
}

static BOOL down(LONG vk) { return vk > 0 && vk < 256 && (GetAsyncKeyState((int)vk) & 0x8000); }

static WPARAM mouse_wparam(BOOL lbutton)
{
    WPARAM w = lbutton ? MK_LBUTTON : 0;
    if (down(VK_SHIFT)) w |= MK_SHIFT;
    if (down(VK_CONTROL)) w |= MK_CONTROL;
    return w;
}

static void send_button(BOOL press)
{
    INPUT in;
    memset(&in, 0, sizeof(in));
    in.type = INPUT_MOUSE;
    in.mi.dwFlags = press ? MOUSEEVENTF_LEFTDOWN : MOUSEEVENTF_LEFTUP;
    SendInput(1, &in, sizeof(in));
}

static void release_move(void)
{
    if (!mv_active) return;
    if (g_mode == 2) {
        send_button(FALSE);
        SetCursorPos(mv_saved_cursor.x, mv_saved_cursor.y);
    } else if (mv_hwnd) {
        POINT real;
        /* player still holds the real left button (e.g. attacking): keep the
           button down, just give the game the real cursor back */
        if (!g_real_l)
            PostMessageA(mv_hwnd, WM_LBUTTONUP, mouse_wparam(FALSE), MAKELPARAM(mv_target.x, mv_target.y));
        mv_active = 0;
        mv_last_active = GetTickCount();
        if (orig_GetCursorPos(&real) && ScreenToClient(mv_hwnd, &real))
            PostMessageA(mv_hwnd, WM_MOUSEMOVE, mouse_wparam(g_real_l), MAKELPARAM(real.x, real.y));
    }
    mv_active = 0;
}

static BOOL user_input_busy(void);

/* Called ~120x per second from movement_thread. (The game polls XInput
   only while a controller is connected, so XInputGetState can't drive it.) */
static void movement_tick(void)
{
    int dx = 0, dy = 0;
    HWND w;
    RECT rc;
    POINT t;
    double len, r;


    d_keys = (down(g_vk[0]) ? 1 : 0) | (down(g_vk[1]) ? 2 : 0) | (down(g_vk[2]) ? 4 : 0) | (down(g_vk[3]) ? 8 : 0);
    if (g_force_keys) d_keys = g_force_keys;
    {   /* hook the game's imports once its window exists (not while the
           loader is still starting the exe), re-check every 5 s */
        static DWORD last_patch;
        if (GetTickCount() - last_patch > 5000 && game_window()) {
            last_patch = GetTickCount();
            patch_iat(GetModuleHandleW(NULL));
            if (g_mode == 1) subclass_window(game_window());
            game_icon(game_window());
        }
    }
    if (!d_keys) g_wasd_priority = FALSE;
    if (!g_enabled || !d_keys) { release_move(); return; }
    if (mv_active && g_mode == 1) mv_last_active = GetTickCount();
    if (user_input_busy()) { release_move(); return; }
    d_key_frames++;
    if (g_attack_only && !g_in_attack) { d_blocked_attack++; release_move(); return; }
    d_focus = g_force_keys ? TRUE : game_has_focus();
    if (!d_focus) { d_blocked_focus++; release_move(); return; }
    /* a text field reported focus; forget it after 10 min in case the
       "blur" message got lost */
    if (g_typing && GetTickCount() - g_typing_since < 600000) { d_blocked_typing++; release_move(); return; }
    if (down(VK_MENU)) { d_blocked_alt++; release_move(); return; }
    if (d_keys & 1) dy -= 1; /* screen y grows downwards */
    if (d_keys & 4) dy += 1;
    if (d_keys & 2) dx -= 1;
    if (d_keys & 8) dx += 1;
    if (!dx && !dy) { release_move(); return; }

    w = game_window();
    if (!w || !GetClientRect(w, &rc) || rc.bottom < 50) { d_blocked_window++; release_move(); return; }
    len = sqrt((double)(dx * dx + dy * dy));
    r = rc.bottom * g_radius / 100.0;
    t.x = (LONG)(rc.right / 2 + dx / len * r);
    t.y = (LONG)(rc.bottom * g_center_y / 100.0 + dy / len * r);
    if (t.x < 1) t.x = 1;
    if (t.y < 1) t.y = 1;
    if (t.x > rc.right - 2) t.x = rc.right - 2;
    if (t.y > rc.bottom - 2) t.y = rc.bottom - 2;
    d_moved_frames++;

    if (g_mode == 2) {
        POINT s = t;
        ClientToScreen(w, &s);
        if (!mv_active) {
            orig_GetCursorPos(&mv_saved_cursor);
            mv_hwnd = w; mv_target = t;
            SetCursorPos(s.x, s.y);
            send_button(TRUE);
            mv_active = 1;
            d_presses++;
        } else {
            mv_target = t;
            SetCursorPos(s.x, s.y);
        }
        return;
    }

    mv_hwnd = w;
    mv_target = t;
    if (!mv_active) {
        patch_iat(GetModuleHandleW(NULL)); /* no-op when already hooked */
        subclass_window(w);
        mv_active = 1;
        d_presses++;
        if (g_real_l) {
            PostMessageA(w, WM_MOUSEMOVE, mouse_wparam(TRUE), MAKELPARAM(t.x, t.y));
        } else {
            PostMessageA(w, WM_MOUSEMOVE, mouse_wparam(FALSE), MAKELPARAM(t.x, t.y));
            PostMessageA(w, WM_LBUTTONDOWN, mouse_wparam(TRUE), MAKELPARAM(t.x, t.y));
        }
    } else {
        /* every frame, so real mouse movement doesn't steer the hero */
        PostMessageA(w, WM_MOUSEMOVE, mouse_wparam(TRUE), MAKELPARAM(t.x, t.y));
    }
}

/* ---- the player's own mouse and keys take priority --------------------
   Low-level hooks see real input before the game does:
   - real left button down: the player takes over the held button (no
     button-up is sent, so the game just retargets to the real cursor, e.g.
     a monster); WASD resumes shortly after the real button is released.
   - right button, or any other key (abilities, potions ...): the fake
     button and cursor are released before the game handles the input, so
     it aims at the real cursor; WASD resumes 250 ms after release. */
static HHOOK g_kb_hook, g_mouse_hook;
static BYTE g_other_down[256];
static int g_other_count;
static BYTE g_move_down[4];
static DWORD g_resume_at;
static DWORD g_last_ll_event; /* the hooks run before GetAsyncKeyState sees the input */

static BOOL is_move_or_modifier(DWORD vk)
{
    int i;
    for (i = 0; i < 4; i++) if ((DWORD)g_vk[i] == vk) return TRUE;
    switch (vk) {
    case VK_SHIFT: case VK_CONTROL: case VK_MENU: case VK_LSHIFT: case VK_RSHIFT:
    case VK_LCONTROL: case VK_RCONTROL: case VK_LMENU: case VK_RMENU:
    case VK_LWIN: case VK_RWIN: case VK_CAPITAL:
        return TRUE;
    }
    return FALSE;
}

static BOOL user_input_busy(void)
{
    int vk;
    BOOL settled = GetTickCount() - g_last_ll_event > 500;
    if (g_other_count && settled) { /* drop keys whose key-up we missed */
        g_other_count = 0;
        for (vk = 0; vk < 256; vk++) if (g_other_down[vk]) {
            if (GetAsyncKeyState(vk) & 0x8000) g_other_count++; else g_other_down[vk] = 0;
        }
        if (!g_other_count) g_resume_at = GetTickCount() + 250;
    }
    /* missed button-up (e.g. released outside the window) */
    if (settled && g_real_l && !(GetAsyncKeyState(VK_LBUTTON) & 0x8000)) g_real_l = FALSE;
    if (settled && g_real_r && !(GetAsyncKeyState(VK_RBUTTON) & 0x8000)) g_real_r = FALSE;
    if (g_wasd_priority && !g_real_r && !g_other_count) return FALSE; /* WASD pressed after the click */
    return g_real_l || g_real_r || g_other_count || (LONG)(GetTickCount() - g_resume_at) < 0;
}

static LRESULT CALLBACK ll_keyboard(int code, WPARAM wp, LPARAM lp)
{
    if (code == HC_ACTION) {
        KBDLLHOOKSTRUCT *k = (KBDLLHOOKSTRUCT *)lp;
        DWORD vk = k->vkCode & 0xFF;
        int i;
        if (!(k->flags & LLKHF_INJECTED) || g_accept_injected) {
            for (i = 0; i < 4; i++) if ((DWORD)g_vk[i] == vk) {
                if (wp == WM_KEYDOWN || wp == WM_SYSKEYDOWN) {
                    /* a new press (not key repeat) while holding the real
                       left button: WASD steers until it's released */
                    if (!g_move_down[i] && g_real_l) g_wasd_priority = TRUE;
                    g_move_down[i] = 1;
                } else g_move_down[i] = 0;
            }
        }
        if ((!(k->flags & LLKHF_INJECTED) || g_accept_injected) && !is_move_or_modifier(vk)) {
            g_last_ll_event = GetTickCount();
            if (wp == WM_KEYDOWN || wp == WM_SYSKEYDOWN) {
                if (!g_other_down[vk]) { g_other_down[vk] = 1; g_other_count++; }
                if (mv_active) { release_move(); d_key_pauses++; }
            } else if (g_other_down[vk]) {
                g_other_down[vk] = 0;
                if (--g_other_count <= 0) { g_other_count = 0; g_resume_at = GetTickCount() + 250; }
            }
        }
    }
    return CallNextHookEx(g_kb_hook, code, wp, lp);
}

static LRESULT CALLBACK ll_mouse(int code, WPARAM wp, LPARAM lp)
{
    if (code == HC_ACTION && (!(((MSLLHOOKSTRUCT *)lp)->flags & LLMHF_INJECTED) || g_accept_injected)) {
        if (wp != WM_MOUSEMOVE && wp != WM_MOUSEWHEEL) g_last_ll_event = GetTickCount();
        switch (wp) {
        case WM_LBUTTONDOWN:
            g_real_l = TRUE;
            g_wasd_priority = FALSE; /* the click is the newest input */
            if (mv_active) {
                if (g_mode == 1) { mv_active = 0; mv_last_active = GetTickCount(); }
                else release_move();
                d_takeovers++;
            }
            break;
        case WM_LBUTTONUP:
            g_real_l = FALSE;
            if (g_wasd_priority) {
                /* WASD kept moving over the click: the game must see the
                   release, then WASD presses again on the next tick */
                if (mv_active && mv_hwnd && g_mode == 1) {
                    PostMessageA(mv_hwnd, WM_LBUTTONUP, mouse_wparam(FALSE), MAKELPARAM(mv_target.x, mv_target.y));
                    mv_active = 0;
                }
                g_wasd_priority = FALSE;
            } else g_resume_at = GetTickCount() + 120;
            break;
        case WM_RBUTTONDOWN:
            g_real_r = TRUE;
            if (mv_active) { release_move(); d_takeovers++; }
            break;
        case WM_RBUTTONUP: g_real_r = FALSE; g_resume_at = GetTickCount() + 250; break;
        }
    }
    return CallNextHookEx(g_mouse_hook, code, wp, lp);
}

/* Movement and the input hooks share this thread (the hooks need its
   message loop), so they never race. ~120 ticks per second. */
static DWORD WINAPI movement_thread(LPVOID p)
{
    MSG m;
    HMODULE self = NULL;
    (void)p;
    timeBeginPeriod(1);
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)movement_thread, &self);
    g_kb_hook = SetWindowsHookExW(WH_KEYBOARD_LL, ll_keyboard, self, 0);
    g_mouse_hook = SetWindowsHookExW(WH_MOUSE_LL, ll_mouse, self, 0);
    d_ll_hooks = (g_kb_hook ? 1 : 0) + (g_mouse_hook ? 1 : 0);
    for (;;) {
        MsgWaitForMultipleObjects(0, NULL, FALSE, 8, QS_ALLINPUT);
        while (PeekMessageW(&m, NULL, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
        movement_tick();
    }
}

/* ------------------------------------------------------------------ */
/* exports (names set in xinput9_1_0.def)                              */
/* ------------------------------------------------------------------ */
DWORD WINAPI wasd_XInputGetState(DWORD idx, XSTATE *st)
{
    DWORD r = ERROR_DEVICE_NOT_CONNECTED;
    ensure_real();
    if (real_get_state) r = real_get_state(idx, st);
    if (idx == 0) d_gs_calls++;
    return r;
}

DWORD WINAPI wasd_XInputSetState(DWORD idx, XVIB *vib)
{
    ensure_real();
    return real_set_state ? real_set_state(idx, vib) : ERROR_DEVICE_NOT_CONNECTED;
}

#define MQEL_LOOT_ASK 0x4D51454Cu  /* "MQEL" */
DWORD WINAPI wasd_XInputGetCapabilities(DWORD idx, DWORD flags, XCAPS *caps)
{
    if (idx == MQEL_LOOT_ASK) {  /* loot filter question of the patched exe */
        d_loot_asks++;
        return g_loot_player ? 0x4D510001u : 0x4D510000u;
    }
    ensure_real();
    return real_get_caps ? real_get_caps(idx, flags, caps) : ERROR_DEVICE_NOT_CONNECTED;
}

/* ------------------------------------------------------------------ */
/* settings file                                                       */
/* ------------------------------------------------------------------ */
static const wchar_t *KEY_NAMES[4] = {L"Up", L"Left", L"Down", L"Right"};

static LONG clamp(LONG v, LONG lo, LONG hi) { return v < lo ? lo : v > hi ? hi : v; }

static void load_ini(void)
{
    int i;
    /* 2026-11-23: off for new players (no WASD.ini yet): they keep the
       game's own keys (potion on Q, camera on W/E) until they switch WASD
       on in the KEYS panel; existing players keep their WASD.ini */
    g_enabled = GetPrivateProfileIntW(L"WASD", L"Enabled", 0, g_ini) ? 1 : 0;
    for (i = 0; i < 4; i++) {
        LONG def[4] = {'W', 'A', 'S', 'D'};
        UINT v = GetPrivateProfileIntW(L"WASD", KEY_NAMES[i], def[i], g_ini);
        g_vk[i] = (v > 0 && v < 256) ? (LONG)v : def[i];
    }
    g_mode = GetPrivateProfileIntW(L"WASD", L"Mode", 1, g_ini) == 2 ? 2 : 1;
    g_layout_offered = GetPrivateProfileIntW(L"WASD", L"LayoutOffered", 0, g_ini) ? 1 : 0;
    g_layout_applied = GetPrivateProfileIntW(L"WASD", L"LayoutApplied", 0, g_ini) ? 1 : 0;
    g_attack_only = GetPrivateProfileIntW(L"WASD", L"AttackOnly", 1, g_ini) ? 1 : 0;
    g_radius = clamp((LONG)GetPrivateProfileIntW(L"WASD", L"Radius", 10, g_ini), 4, 40);
    g_accept_injected = GetPrivateProfileIntW(L"WASD", L"AcceptInjected", 0, g_ini) ? 1 : 0;
    g_force_keys = (LONG)GetPrivateProfileIntW(L"WASD", L"ForceKeys", 0, g_ini) & 15;
    g_center_y = clamp((LONG)GetPrivateProfileIntW(L"WASD", L"CenterY", 52, g_ini), 20, 80);
    g_loot_player = GetPrivateProfileIntW(L"WASD", L"LootPlayer", 0, g_ini) ? 1 : 0;
}

static void save_ini(void)
{
    wchar_t buf[16];
    int i;
    WritePrivateProfileStringW(L"WASD", L"Enabled", g_enabled ? L"1" : L"0", g_ini);
    for (i = 0; i < 4; i++) {
        swprintf(buf, 16, L"%ld", g_vk[i]);
        WritePrivateProfileStringW(L"WASD", KEY_NAMES[i], buf, g_ini);
    }
    WritePrivateProfileStringW(L"WASD", L"Mode", g_mode == 2 ? L"2" : L"1", g_ini);
    WritePrivateProfileStringW(L"WASD", L"AttackOnly", g_attack_only ? L"1" : L"0", g_ini);
    WritePrivateProfileStringW(L"WASD", L"LayoutOffered", g_layout_offered ? L"1" : L"0", g_ini);
    WritePrivateProfileStringW(L"WASD", L"LayoutApplied", g_layout_applied ? L"1" : L"0", g_ini);
    swprintf(buf, 16, L"%ld", g_radius);
    WritePrivateProfileStringW(L"WASD", L"Radius", buf, g_ini);
    swprintf(buf, 16, L"%ld", g_center_y);
    WritePrivateProfileStringW(L"WASD", L"CenterY", buf, g_ini);
    WritePrivateProfileStringW(L"WASD", L"LootPlayer", g_loot_player ? L"1" : L"0", g_ini);
}

/* ------------------------------------------------------------------ */
/* small file helpers                                                  */
/* ------------------------------------------------------------------ */
static char *read_file(const wchar_t *path, DWORD *len)
{
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                           OPEN_EXISTING, 0, NULL);
    DWORD size, got = 0;
    char *buf;
    if (h == INVALID_HANDLE_VALUE) return NULL;
    size = GetFileSize(h, NULL);
    if (size == INVALID_FILE_SIZE || size > 4 * 1024 * 1024) { CloseHandle(h); return NULL; }
    buf = (char *)malloc(size + 1);
    if (buf && (!ReadFile(h, buf, size, &got, NULL) || got != size)) { free(buf); buf = NULL; }
    CloseHandle(h);
    if (buf) { buf[size] = 0; if (len) *len = size; }
    return buf;
}

static BOOL write_file(const wchar_t *path, const char *data, DWORD len)
{
    wchar_t tmp[MAX_PATH + 8];
    HANDLE h;
    DWORD put = 0;
    BOOL ok;
    swprintf(tmp, MAX_PATH + 8, L"%s.tmp", path);
    h = CreateFileW(tmp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return FALSE;
    ok = WriteFile(h, data, len, &put, NULL) && put == len;
    CloseHandle(h);
    if (ok) ok = MoveFileExW(tmp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    if (!ok) DeleteFileW(tmp);
    return ok;
}

/* End of a JSON value that starts with '{' at s[i] (string aware), or -1. */
static long object_end(const char *s, long n, long i)
{
    int depth = 0, in_str = 0;
    for (; i < n; i++) {
        char c = s[i];
        if (in_str) {
            if (c == '\\') i++;
            else if (c == '"') in_str = 0;
        } else if (c == '"') in_str = 1;
        else if (c == '{' || c == '[') depth++;
        else if (c == '}' || c == ']') { if (--depth == 0) return i + 1; if (depth < 0) return -1; }
    }
    return -1;
}

/* Span of the "ShortcutsDictionary" object in a settings text. */
static BOOL find_shortcuts(const char *s, long n, long *b, long *e)
{
    const char *key = "\"ShortcutsDictionary\"";
    const char *p = s;
    while ((p = strstr(p, key)) != NULL) {
        long i = (long)(p - s) + (long)strlen(key);
        while (i < n && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) i++;
        if (i < n && s[i] == ':') {
            i++;
            while (i < n && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) i++;
            if (i < n && s[i] == '{') {
                long end = object_end(s, n, i);
                if (end < 0) return FALSE;
                *b = i; *e = end;
                return TRUE;
            }
        }
        p += strlen(key);
    }
    return FALSE;
}

static BOOL is_object(const char *s, long n)
{
    long i = 0, end;
    while (i < n && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) i++;
    if (i >= n || s[i] != '{') return FALSE;
    end = object_end(s, n, i);
    if (end < 0) return FALSE;
    while (end < n && (s[end] == ' ' || s[end] == '\t' || s[end] == '\r' || s[end] == '\n')) end++;
    return end == n;
}

/* Merge the pending key binds into CustomUserSettings.json (game start). */
/* Span [*b, *e) of the value of "key" (starting with `open`) inside s[from, to). */
static BOOL find_value(const char *s, long from, long to, const char *key, char open, long *b, long *e)
{
    char q[96];
    long klen, i;
    _snprintf(q, sizeof(q), "\"%s\"", key);
    q[sizeof(q) - 1] = 0;
    klen = (long)strlen(q);
    for (i = from; i + klen <= to; i++) {
        long j;
        if (memcmp(s + i, q, klen) != 0) continue;
        j = i + klen;
        while (j < to && (s[j] == ' ' || s[j] == '\t' || s[j] == '\r' || s[j] == '\n')) j++;
        if (j >= to || s[j] != ':') continue;
        j++;
        while (j < to && (s[j] == ' ' || s[j] == '\t' || s[j] == '\r' || s[j] == '\n')) j++;
        if (j >= to || s[j] != open) continue;
        *b = j;
        *e = object_end(s, to, j);
        return *e > j;
    }
    return FALSE;
}

#define KEY_ENTRY(k) "{\"Key\":" #k ",\"CanStillBeTriggeredWithShiftPressedA\":false,\"IgnoredModifiers\":2,\"IsGrabbable\":true,\"RequiredModifiers\":0}"

/* WASD layout (once, at the first game start with WASD switched on;
   new players since 2026-11-23 start with WASD off and keep the game keys):
   W/A/S/D move, so the camera rotates with Left/Q and Right/E and Ability 5
   (Q slot) moves to R. Only these three actions' keyboard keys change.
   Returns FALSE if CustomUserSettings.json doesn't exist yet (the game
   creates it on its first run; then this runs at the next start). */
static BOOL apply_wasd_layout(void)
{
    static const char *actions[3][2] = {
        {"OrbitGameCameraLeft", "[" KEY_ENTRY(80) "," KEY_ENTRY(20) "]"},   /* Left arrow, Q */
        {"OrbitGameCameraRight", "[" KEY_ENTRY(79) "," KEY_ENTRY(8) "]"},   /* Right arrow, E */
        {"Ability5", "[" KEY_ENTRY(21) "]"},                                /* R */
    };
    DWORD len = 0;
    char *cus = read_file(g_cus, &len);
    long n, sb, se, ab, ae, kb, ke;
    int i, changed = 0;
    if (!cus) return FALSE;
    n = (long)len;
    for (i = 0; i < 3; i++) {
        long alen = (long)strlen(actions[i][1]);
        char *out;
        if (!find_shortcuts(cus, n, &sb, &se)) break;
        if (!find_value(cus, sb + 1, se - 1, actions[i][0], '{', &ab, &ae)) continue;
        if (!find_value(cus, ab + 1, ae - 1, "KeyboardShortcuts", '[', &kb, &ke)) continue;
        out = (char *)malloc(n - (ke - kb) + alen + 1);
        if (!out) break;
        memcpy(out, cus, kb);
        memcpy(out + kb, actions[i][1], alen);
        memcpy(out + kb + alen, cus + ke, n - ke);
        n = n - (ke - kb) + alen;
        out[n] = 0;
        free(cus);
        cus = out;
        changed++;
    }
    if (changed) {
        CopyFileW(g_cus, g_backup, FALSE);
        write_file(g_cus, cus, (DWORD)n);
    }
    free(cus);
    return TRUE;
}

static void apply_pending(void)
{
    DWORD plen = 0, clen = 0;
    char *pend, *cus, *out;
    long b, e;
    pend = read_file(g_pending, &plen);
    if (!pend) return;
    cus = read_file(g_cus, &clen);
    if (cus && is_object(pend, (long)plen) && find_shortcuts(cus, (long)clen, &b, &e)) {
        DWORD olen = (DWORD)(b + plen + (clen - e));
        out = (char *)malloc(olen);
        if (out) {
            memcpy(out, cus, b);
            memcpy(out + b, pend, plen);
            memcpy(out + b + plen, cus + e, clen - e);
            CopyFileW(g_cus, g_backup, FALSE);
            if (write_file(g_cus, out, olen)) DeleteFileW(g_pending);
            free(out);
        }
    } else if (!is_object(pend, (long)plen)) {
        DeleteFileW(g_pending); /* broken file: never retry it */
    }
    free(cus);
    free(pend);
}

/* ------------------------------------------------------------------ */
/* local HTTP endpoint for the Keybind panel                           */
/* ------------------------------------------------------------------ */
static void send_all(SOCKET s, const char *d, int n)
{
    while (n > 0) { int k = send(s, d, n, 0); if (k <= 0) return; d += k; n -= k; }
}

static void reply(SOCKET s, int code, const char *type, const char *body, int blen)
{
    char head[512];
    const char *msg = code == 200 ? "OK" : code == 204 ? "No Content" : code == 403 ? "Forbidden"
                    : code == 404 ? "Not Found" : code == 400 ? "Bad Request" : "Error";
    int n;
    if (blen < 0) blen = body ? (int)strlen(body) : 0;
    n = _snprintf(head, sizeof(head),
        "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
        "Access-Control-Allow-Origin: http://localhost\r\n"
        "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
        "Access-Control-Allow-Headers: Content-Type\r\n"
        "Cache-Control: no-store\r\nConnection: close\r\n\r\n",
        code, msg, type, blen);
    send_all(s, head, n);
    if (blen) send_all(s, body, blen);
}

static int form_int(const char *body, const char *name, int def)
{
    size_t ln = strlen(name);
    const char *p = body;
    while (p && *p) {
        if (strncmp(p, name, ln) == 0 && p[ln] == '=') return atoi(p + ln + 1);
        p = strchr(p, '&');
        if (p) p++;
    }
    return def;
}

static void send_state(SOCKET s)
{
    char body[384];
    _snprintf(body, sizeof(body),
        "{\"version\":2,\"enabled\":%s,\"up\":%ld,\"left\":%ld,\"down\":%ld,\"right\":%ld,"
        "\"mode\":%ld,\"radius\":%ld,\"layoutOffered\":%s,\"layoutApplied\":%s,\"attackOnly\":%s,\"inAttack\":%s,\"pendingBinds\":%s,\"lootPlayer\":%s,\"lootFilter\":true}",
        g_enabled ? "true" : "false", g_vk[0], g_vk[1], g_vk[2], g_vk[3],
        g_mode, g_radius, g_layout_offered ? "true" : "false", g_layout_applied ? "true" : "false", g_attack_only ? "true" : "false", g_in_attack ? "true" : "false",
        GetFileAttributesW(g_pending) != INVALID_FILE_ATTRIBUTES ? "true" : "false",
        g_loot_player ? "true" : "false");
    body[sizeof(body) - 1] = 0;
    reply(s, 200, "application/json", body, -1);
}

static char g_presence_status[64];   /* discord_presence.c */
static void debug_json(char *b, int size)
{
    _snprintf(b, size,
        "{\"version\":2,\"enabled\":%s,\"mode\":%ld,\"attackOnly\":%s,\"inAttack\":%s,\"attackMsgs\":%ld,\"attackStarts\":%ld,"
        "\"polls\":%ld,\"focus\":%s,\"typing\":%s,\"keys\":%ld,\"keyFrames\":%ld,"
        "\"blockedAttack\":%ld,\"blockedFocus\":%ld,\"blockedTyping\":%ld,\"blockedAlt\":%ld,\"blockedWindow\":%ld,"
        "\"movedFrames\":%ld,\"presses\":%ld,\"hooksInstalled\":%ld,"
        "\"hookCursor\":%ld,\"hookKeyState\":%ld,\"hookKeyboardState\":%ld,\"hookSetCursor\":%ld,\"takeovers\":%ld,\"rewrittenMoves\":%ld,\"subclassed\":%ld,\"keyPauses\":%ld,\"llHooks\":%ld,\"active\":%ld,\"tx\":%ld,\"ty\":%ld,\"discord\":\"%s\",\"lootPlayer\":%ld,\"lootAsks\":%ld,\"iconSet\":%ld}",
        g_enabled ? "true" : "false", g_mode, g_attack_only ? "true" : "false",
        g_in_attack ? "true" : "false", d_attack_msgs, d_attack_on,
        d_gs_calls, d_focus ? "true" : "false", g_typing ? "true" : "false", d_keys, d_key_frames,
        d_blocked_attack, d_blocked_focus, d_blocked_typing, d_blocked_alt, d_blocked_window,
        d_moved_frames, d_presses, d_hooks_installed,
        d_hook_cursor, d_hook_keystate, d_hook_kbstate, d_hook_setcursor, d_takeovers, d_rewritten, d_subclassed, d_key_pauses, d_ll_hooks, mv_active, mv_target.x, mv_target.y, g_presence_status, g_loot_player, d_loot_asks, d_icon_set);
    b[size - 1] = 0;
}

/* WASD.log next to the exe: the diagnostics, rewritten every 5 s */
static DWORD WINAPI log_thread(LPVOID p)
{
    char b[1024];
    (void)p;
    for (;;) {
        Sleep(5000);
        debug_json(b, sizeof(b));
        strcat(b, "\r\n");
        write_file(g_log, b, (DWORD)strlen(b));
    }
}

#define REQ_MAX (256 * 1024)
static void handle(SOCKET s, char *req)
{
    int got = 0, k, clen = 0;
    char *hdr_end = NULL, *body, *p, method[8] = {0}, path[64] = {0};

    for (;;) {
        k = recv(s, req + got, REQ_MAX - 1 - got, 0);
        if (k <= 0) return;
        got += k;
        req[got] = 0;
        if (!hdr_end && (hdr_end = strstr(req, "\r\n\r\n")) != NULL) {
            p = strstr(req, "\r\nContent-Length:");
            if (!p) p = strstr(req, "\r\ncontent-length:");
            if (p) clen = atoi(p + 17);
            if (clen < 0 || clen > REQ_MAX - 1 - (int)(hdr_end + 4 - req)) {
                reply(s, 400, "text/plain", "too large", -1);
                return;
            }
        }
        if (hdr_end && got >= (int)(hdr_end + 4 - req) + clen) break;
        if (got >= REQ_MAX - 1) return;
    }
    *hdr_end = 0;
    body = hdr_end + 4;
    body[clen] = 0;
    sscanf(req, "%7s %63s", method, path);

    /* Only the game UI (http://localhost) may use this; a web page in a
       normal browser sends its own Origin and is refused. */
    p = strstr(req, "\r\nOrigin:");
    if (!p) p = strstr(req, "\r\norigin:");
    if (p) {
        size_t olen;
        p += 9;
        while (*p == ' ') p++;
        olen = strcspn(p, "\r");
        if (!(olen == 16 && strncmp(p, "http://localhost", 16) == 0)) {
            reply(s, 403, "text/plain", "forbidden", -1);
            return;
        }
    }

    if (strcmp(method, "OPTIONS") == 0) { reply(s, 204, "text/plain", NULL, 0); return; }

    if (strcmp(method, "GET") == 0 && strcmp(path, "/state") == 0) { send_state(s); return; }

    if (strcmp(method, "GET") == 0 && strcmp(path, "/debug") == 0) {
        char b[1024];
        debug_json(b, sizeof(b));
        reply(s, 200, "application/json", b, -1);
        return;
    }

    if (strcmp(method, "POST") == 0 && strcmp(path, "/config") == 0) {
        int i, v;
        g_enabled = form_int(body, "enabled", g_enabled) ? 1 : 0;
        for (i = 0; i < 4; i++) {
            const char *n[4] = {"up", "left", "down", "right"};
            v = form_int(body, n[i], g_vk[i]);
            if (v > 0 && v < 256) g_vk[i] = v;
        }
        g_mode = form_int(body, "mode", g_mode) == 2 ? 2 : 1;
        g_attack_only = form_int(body, "attackonly", g_attack_only) ? 1 : 0;
        g_radius = clamp(form_int(body, "radius", g_radius), 4, 40);
        g_layout_offered = form_int(body, "layoutoffered", g_layout_offered) ? 1 : 0;
        g_loot_player = form_int(body, "lootplayer", g_loot_player) ? 1 : 0;
        save_ini();
        send_state(s);
        return;
    }

    if (strcmp(method, "POST") == 0 && strcmp(path, "/attack") == 0) {
        g_in_attack = body[0] == '1';
        d_attack_msgs++;
        if (g_in_attack) d_attack_on++;
        reply(s, 204, "text/plain", NULL, 0);
        return;
    }

    /* server update countdown at 0 (UI patch 16): close the game like
       Alt+F4, and end the process if it is still there after 2 s */
    if (strcmp(method, "POST") == 0 && strcmp(path, "/quit") == 0) {
        HWND w = game_window();
        reply(s, 204, "text/plain", NULL, 0);
        if (w) PostMessageA(w, WM_CLOSE, 0, 0);
        Sleep(2000);
        TerminateProcess(GetCurrentProcess(), 0);
        return;
    }

    if (strcmp(method, "POST") == 0 && strcmp(path, "/typing") == 0) {
        g_typing = body[0] == '1';
        g_typing_since = GetTickCount();
        reply(s, 204, "text/plain", NULL, 0);
        return;
    }

    if (strcmp(method, "GET") == 0 && strcmp(path, "/binds") == 0) {
        DWORD n = 0;
        char *t;
        long b, e;
        EnterCriticalSection(&g_file_lock);
        t = read_file(g_pending, &n);
        if (t && is_object(t, (long)n)) reply(s, 200, "application/json", t, (int)n);
        else {
            free(t);
            t = read_file(g_cus, &n);
            if (t && find_shortcuts(t, (long)n, &b, &e))
                reply(s, 200, "application/json", t + b, (int)(e - b));
            else reply(s, 404, "text/plain", "CustomUserSettings.json not found", -1);
        }
        free(t);
        LeaveCriticalSection(&g_file_lock);
        return;
    }

    if (strcmp(method, "POST") == 0 && strcmp(path, "/binds") == 0) {
        BOOL ok = FALSE;
        if (is_object(body, clen)) {
            EnterCriticalSection(&g_file_lock);
            ok = write_file(g_pending, body, (DWORD)clen);
            LeaveCriticalSection(&g_file_lock);
        }
        if (ok) send_state(s); else reply(s, 400, "text/plain", "invalid key binds", -1);
        return;
    }

    if (strcmp(method, "POST") == 0 && strcmp(path, "/binds/discard") == 0) {
        EnterCriticalSection(&g_file_lock);
        DeleteFileW(g_pending);
        LeaveCriticalSection(&g_file_lock);
        send_state(s);
        return;
    }

    reply(s, 404, "text/plain", "not found", -1);
}

static DWORD WINAPI conn_thread(LPVOID p)
{
    SOCKET c = (SOCKET)p;
    DWORD tmo = 10000;
    char *req = (char *)malloc(REQ_MAX);
    setsockopt(c, SOL_SOCKET, SO_RCVTIMEO, (const char *)&tmo, sizeof(tmo));
    if (req) { handle(c, req); free(req); }
    shutdown(c, SD_SEND);
    closesocket(c);
    return 0;
}

static DWORD WINAPI server_thread(LPVOID p)
{
    WSADATA wsa;
    SOCKET ls;
    struct sockaddr_in a;
    BOOL excl = TRUE;
    (void)p;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return 0;
    ls = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (ls == INVALID_SOCKET) return 0;
    setsockopt(ls, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, (const char *)&excl, sizeof(excl));
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(WASD_PORT);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(ls, (struct sockaddr *)&a, sizeof(a)) != 0 || listen(ls, 8) != 0) {
        closesocket(ls); /* second game instance: the first one serves the panel */
        return 0;
    }
    for (;;) {
        SOCKET c = accept(ls, NULL, NULL);
        HANDLE t;
        if (c == INVALID_SOCKET) { Sleep(100); continue; }
        /* one thread per connection: Chromium opens idle pre-connections
           that would block a one-at-a-time server */
        t = CreateThread(NULL, 0, conn_thread, (LPVOID)c, 0, NULL);
        if (t) CloseHandle(t); else closesocket(c);
    }
}

/* Discord Rich Presence (server/presence.py, docs/85-discord-presence.md) */
#include "discord_presence.c"

/* ------------------------------------------------------------------ */
BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        wchar_t *slash;
        HANDLE t;
        DisableThreadLibraryCalls(inst);
        orig_GetCursorPos = GetCursorPos;
        orig_GetKeyState = GetKeyState;
        orig_GetKeyboardState = GetKeyboardState;
        orig_SetCursorPos = SetCursorPos;
        InitializeCriticalSection(&g_file_lock);
        GetModuleFileNameW(NULL, g_bin, MAX_PATH);
        slash = wcsrchr(g_bin, L'\\');
        if (slash) slash[1] = 0;
        swprintf(g_ini, MAX_PATH, L"%sWASD.ini", g_bin);
        swprintf(g_log, MAX_PATH, L"%sWASD.log", g_bin);
        swprintf(g_cus, MAX_PATH, L"%s..\\Config\\Game\\CustomUserSettings.json", g_bin);
        swprintf(g_pending, MAX_PATH, L"%s..\\Config\\Game\\CustomUserSettings.wasd-pending.json", g_bin);
        swprintf(g_backup, MAX_PATH, L"%s..\\Config\\Game\\CustomUserSettings.json.wasd-backup", g_bin);
        load_ini();
        if (GetFileAttributesW(g_ini) == INVALID_FILE_ATTRIBUTES) save_ini();
        /* before the game reads CustomUserSettings.json; the WASD layout
           (camera Left/Q, Right/E, Ability 5 on R) only once WASD is on */
        if (g_enabled && !g_layout_applied && apply_wasd_layout()) { g_layout_applied = 1; save_ini(); }
        apply_pending();
        t = CreateThread(NULL, 0, server_thread, NULL, 0, NULL);
        if (t) CloseHandle(t);
        t = CreateThread(NULL, 0, movement_thread, NULL, 0, NULL);
        if (t) CloseHandle(t);
        t = CreateThread(NULL, 0, log_thread, NULL, 0, NULL);
        if (t) CloseHandle(t);
        presence_start();
    }
    return TRUE;
}

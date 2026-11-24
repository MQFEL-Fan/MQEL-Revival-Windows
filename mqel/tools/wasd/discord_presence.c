/*
 * Discord Rich Presence for the MQEL WASD helper (docs/85-discord-presence.md).
 *
 * The game server knows what the player does (server/presence.py). Every
 * POLL_MS this thread asks it:
 *   GET http://<patcher host:port>/presence/<login name>
 * (host from ..\..\Launcher\PublicLauncherSettings.json "PatcherServiceUrl",
 * login name from the game's command line "-email <name>@...").
 * Answer 200: "<Discord application id>\n<activity JSON>", 204: nothing.
 * The activity goes to the local Discord client over its IPC channel
 * (handshake opcode 0, then opcode 1 frames {"cmd":"SET_ACTIVITY",...}):
 * - Windows: named pipe \\.\pipe\discord-ipc-0..9;
 * - Linux (Wine/Proton, detected by ntdll's wine_get_version): Discord's
 *   Unix socket $XDG_RUNTIME_DIR/[app/com.discordapp.Discord/ | snap.discord/
 *   | .flatpak/dev.vencord.Vesktop/xdg-run/]discord-ipc-0..9 (also $TMPDIR,
 *   /tmp), reached through Wine's AF_UNIX support in Winsock (Wine 6+ /
 *   Proton 7+; the path is passed as a DOS path from wine_get_dos_file_name).
 * Discord clears the activity when the game closes the connection (exit).
 *
 * WASD.ini DiscordPresence=0 turns it off.
 */
#include <windows.h>
#include <winhttp.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "shell32.lib")

#define POLL_MS 10000
#define BODY_MAX 4096

/* included at the end of xinput_wasd.c (uses its g_bin, g_ini) */

static HANDLE p_pipe = INVALID_HANDLE_VALUE;
static SOCKET p_sock = INVALID_SOCKET;   /* Linux: Discord's Unix socket via Wine */
static char p_app[32];          /* application id of the open pipe */
static char p_sent[BODY_MAX];   /* last activity sent ("" = cleared) */
static LONG p_nonce;
static char g_presence_status[64] = "off";

static void status(const char *s) { lstrcpynA(g_presence_status, s, sizeof(g_presence_status)); }

/* "-email Name@mqel.local" -> "Name" (the login name) */
static BOOL login_name(wchar_t *out, int size)
{
    int argc, i;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    BOOL ok = FALSE;
    if (!argv) return FALSE;
    for (i = 1; i + 1 < argc; i++) {
        if (!_wcsicmp(argv[i], L"-email")) {
            wchar_t *at;
            lstrcpynW(out, argv[i + 1], size);
            at = wcschr(out, L'@');
            if (at) *at = 0;
            ok = out[0] != 0;
            break;
        }
    }
    LocalFree(argv);
    return ok;
}

/* "PatcherServiceUrl":"http://host:8081/patcher" -> host, port */
static BOOL server_address(wchar_t *host, int size, INTERNET_PORT *port)
{
    wchar_t path[MAX_PATH];
    char buf[16384], *p, *e, *colon;
    DWORD n = 0;
    HANDLE f;
    swprintf(path, MAX_PATH, L"%s..\\..\\Launcher\\PublicLauncherSettings.json", g_bin);
    f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return FALSE;
    ReadFile(f, buf, sizeof(buf) - 1, &n, NULL);
    CloseHandle(f);
    buf[n] = 0;
    p = strstr(buf, "\"PatcherServiceUrl\"");
    if (!p || !(p = strstr(p, "http://"))) return FALSE;
    p += 7;
    for (e = p; *e && *e != '/' && *e != '"'; e++) {}
    *e = 0;
    colon = strchr(p, ':');
    *port = 80;
    if (colon) { *colon = 0; *port = (INTERNET_PORT)atoi(colon + 1); }
    return MultiByteToWideChar(CP_UTF8, 0, p, -1, host, size) > 0;
}

/* GET /presence/<name>: HTTP status, body */
static DWORD fetch(const wchar_t *host, INTERNET_PORT port, const wchar_t *name, char *body, DWORD size)
{
    HINTERNET s, c = NULL, r = NULL;
    wchar_t path[160];
    DWORD code = 0, len = sizeof(code), got = 0, n;
    body[0] = 0;
    s = WinHttpOpen(L"MQEL-WASD/2", WINHTTP_ACCESS_TYPE_NO_PROXY, NULL, NULL, 0);
    if (!s) return 0;
    WinHttpSetTimeouts(s, 3000, 3000, 3000, 3000);
    swprintf(path, 160, L"/presence/%s", name);
    if ((c = WinHttpConnect(s, host, port, 0))
        && (r = WinHttpOpenRequest(c, L"GET", path, NULL, NULL, NULL, 0))
        && WinHttpSendRequest(r, NULL, 0, NULL, 0, 0, 0)
        && WinHttpReceiveResponse(r, NULL)) {
        WinHttpQueryHeaders(r, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, NULL, &code, &len, NULL);
        while (got + 1 < size && WinHttpReadData(r, body + got, size - 1 - got, &n) && n)
            got += n;
        body[got] = 0;
    }
    if (r) WinHttpCloseHandle(r);
    if (c) WinHttpCloseHandle(c);
    WinHttpCloseHandle(s);
    return code;
}

static BOOL connected(void) { return p_pipe != INVALID_HANDLE_VALUE || p_sock != INVALID_SOCKET; }

static BOOL raw_write(const char *buf, DWORD len)
{
    DWORD w;
    if (p_sock != INVALID_SOCKET) {
        while (len) {
            int n = send(p_sock, buf, (int)len, 0);
            if (n <= 0) return FALSE;
            buf += n;
            len -= (DWORD)n;
        }
        return TRUE;
    }
    return WriteFile(p_pipe, buf, len, &w, NULL) && w == len;
}

/* bytes ready to read within `ms` (pipe: polled, socket: select) */
static BOOL raw_wait(DWORD want, int ms)
{
    int waited;
    if (p_sock != INVALID_SOCKET) {
        fd_set fs;
        struct timeval tv;
        FD_ZERO(&fs);
        FD_SET(p_sock, &fs);
        tv.tv_sec = ms / 1000;
        tv.tv_usec = (ms % 1000) * 1000;
        return select(0, &fs, NULL, NULL, &tv) == 1;
    }
    for (waited = 0; waited < ms; waited += 50) {
        DWORD avail = 0;
        if (!PeekNamedPipe(p_pipe, NULL, 0, NULL, &avail, NULL)) return FALSE;
        if (avail >= want) return TRUE;
        Sleep(50);
    }
    return FALSE;
}

static BOOL raw_read(char *buf, DWORD len)
{
    DWORD r;
    while (len) {
        if (p_sock != INVALID_SOCKET) {
            int n;
            if (!raw_wait(1, 2000)) return FALSE;
            n = recv(p_sock, buf, (int)len, 0);
            if (n <= 0) return FALSE;
            r = (DWORD)n;
        } else if (!ReadFile(p_pipe, buf, len, &r, NULL) || !r) {
            return FALSE;
        }
        buf += r;
        len -= r;
    }
    return TRUE;
}

static void pipe_close(void)
{
    if (p_pipe != INVALID_HANDLE_VALUE) CloseHandle(p_pipe);
    if (p_sock != INVALID_SOCKET) closesocket(p_sock);
    p_pipe = INVALID_HANDLE_VALUE;
    p_sock = INVALID_SOCKET;
    p_app[0] = 0;
    p_sent[0] = 0;
}

static BOOL frame_write(DWORD op, const char *json)
{
    DWORD len = (DWORD)strlen(json);
    char *buf = (char *)HeapAlloc(GetProcessHeap(), 0, len + 8);
    BOOL ok;
    if (!buf) return FALSE;
    memcpy(buf, &op, 4);
    memcpy(buf + 4, &len, 4);
    memcpy(buf + 8, json, len);
    ok = raw_write(buf, len + 8);
    HeapFree(GetProcessHeap(), 0, buf);
    return ok;
}

/* one reply frame (up to 2 s); opcode or -1 */
static int frame_read(void)
{
    char hdr[8], skip[512];
    DWORD op, len;
    if (!raw_wait(8, 2000) || !raw_read(hdr, 8)) return -1;
    memcpy(&op, hdr, 4);
    memcpy(&len, hdr + 4, 4);
    while (len) {
        DWORD want = len < sizeof(skip) ? len : sizeof(skip);
        if (!raw_read(skip, want)) return -1;
        len -= want;
    }
    return (int)op;
}

/* Linux (Wine/Proton): connect to Discord's Unix socket */
typedef LPWSTR (CDECL *PDosName)(LPCSTR);
struct mq_sockaddr_un { ADDRESS_FAMILY sun_family; char sun_path[108]; };

static BOOL unix_connect(void)
{
    static const char *subdirs[] = {"", "app/com.discordapp.Discord/", "snap.discord/",
                                    ".flatpak/dev.vencord.Vesktop/xdg-run/", "app/dev.vencord.Vesktop/"};
    const char *envs[] = {"XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"};
    char base[MAX_PATH], unixp[MAX_PATH];
    PDosName dos_name;
    WSADATA wsa;
    int e, d, i;
    if (!GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "wine_get_version")) return FALSE;
    dos_name = (PDosName)GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "wine_get_dos_file_name");
    if (!dos_name || WSAStartup(MAKEWORD(2, 2), &wsa)) return FALSE;
    for (e = 0; e <= 4; e++) {
        if (e < 4) {
            DWORD n = GetEnvironmentVariableA(envs[e], base, sizeof(base));
            if (!n || n >= sizeof(base) || base[0] != '/') continue;   /* Unix paths only */
        } else {
            lstrcpyA(base, "/tmp");
        }
        for (d = 0; d < (int)(sizeof(subdirs) / sizeof(subdirs[0])); d++) {
            for (i = 0; i < 10; i++) {
                struct mq_sockaddr_un a;
                LPWSTR w;
                SOCKET s;
                _snprintf(unixp, sizeof(unixp), "%s/%sdiscord-ipc-%d", base, subdirs[d], i);
                unixp[sizeof(unixp) - 1] = 0;
                w = dos_name(unixp);
                if (!w) continue;
                memset(&a, 0, sizeof(a));
                a.sun_family = 1;  /* AF_UNIX */
                WideCharToMultiByte(CP_UTF8, 0, w, -1, a.sun_path, sizeof(a.sun_path) - 1, NULL, NULL);
                HeapFree(GetProcessHeap(), 0, w);
                if (GetFileAttributesA(a.sun_path) == INVALID_FILE_ATTRIBUTES) continue;
                s = socket(1, SOCK_STREAM, 0);
                if (s == INVALID_SOCKET) { WSACleanup(); status("no AF_UNIX (old Wine)"); return FALSE; }
                if (connect(s, (struct sockaddr *)&a, sizeof(a)) == 0) {
                    p_sock = s;
                    return TRUE;
                }
                closesocket(s);
            }
        }
    }
    WSACleanup();
    return FALSE;
}

static BOOL pipe_open(const char *app)
{
    char hello[96];
    int i;
    pipe_close();
    for (i = 0; i < 10 && p_pipe == INVALID_HANDLE_VALUE; i++) {
        wchar_t name[32];
        swprintf(name, 32, L"\\\\.\\pipe\\discord-ipc-%d", i);
        p_pipe = CreateFileW(name, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    }
    if (p_pipe == INVALID_HANDLE_VALUE && !unix_connect()) {
        if (strncmp(g_presence_status, "no AF_UNIX", 10)) status("no Discord");
        return FALSE;
    }
    _snprintf(hello, sizeof(hello), "{\"v\":1,\"client_id\":\"%s\"}", app);
    hello[sizeof(hello) - 1] = 0;
    if (!frame_write(0, hello) || frame_read() != 1) {  /* 1 = READY (2 = close) */
        pipe_close();
        status("Discord refused");
        return FALSE;
    }
    lstrcpynA(p_app, app, sizeof(p_app));
    return TRUE;
}

static BOOL set_activity(const char *activity)
{
    static char msg[BODY_MAX + 160];
    _snprintf(msg, sizeof(msg),
              "{\"cmd\":\"SET_ACTIVITY\",\"args\":{\"pid\":%lu,\"activity\":%s},\"nonce\":\"%ld\"}",
              GetCurrentProcessId(), activity[0] ? activity : "null", InterlockedIncrement(&p_nonce));
    msg[sizeof(msg) - 1] = 0;
    if (!frame_write(1, msg) || frame_read() < 0) { pipe_close(); status("Discord closed"); return FALSE; }
    lstrcpynA(p_sent, activity, sizeof(p_sent));
    status(activity[0] ? "showing" : "cleared");
    return TRUE;
}

static DWORD WINAPI presence_thread(LPVOID unused)
{
    wchar_t name[64], host[128];
    INTERNET_PORT port;
    static char body[BODY_MAX];
    (void)unused;
    if (!login_name(name, 64)) { status("no -email"); return 0; }
    if (!server_address(host, 128, &port)) { status("no server address"); return 0; }
    status("waiting");
    Sleep(5000);
    for (;; Sleep(POLL_MS)) {
        DWORD code = fetch(host, port, name, body, sizeof(body));
        char *nl = strchr(body, '\n');
        if (code == 200 && nl) {
            *nl = 0;
            if (strcmp(p_app, body) && !pipe_open(body)) continue;
            if (strcmp(p_sent, nl + 1)) set_activity(nl + 1);
        } else if (code == 204 || code == 0) {
            if (connected() && p_sent[0]) set_activity("");
            if (code == 0) status("server unreachable");
        }
    }
}

static void presence_start(void)
{
    HANDLE t;
    if (!GetPrivateProfileIntW(L"WASD", L"DiscordPresence", 1, g_ini)) { status("off (WASD.ini)"); return; }
    t = CreateThread(NULL, 0, presence_thread, NULL, 0, NULL);
    if (t) CloseHandle(t);
}

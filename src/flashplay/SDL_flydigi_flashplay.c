/* Vader 5 Pro Flashplay backend, SDL 3.4.4, zlib license.
 * Linux: BlueZ lookup, saved selection, or SDL_FLYDIGI_BT_ADDRESS/ADAPTER.
 * Button mapping comes from the labelled capture of 2026-10-22.
 */
#include "SDL_internal.h"
#if defined(SDL_JOYSTICK_LINUX) || defined(SDL_PLATFORM_WINDOWS)
#include "../SDL_sysjoystick.h"
#include "../SDL_joystick_c.h"
#ifdef SDL_JOYSTICK_LINUX
#include <sys/socket.h>
#include <poll.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

/* Linux Bluetooth userspace socket ABI; no libbluetooth dependency. */
typedef struct {
    sa_family_t family;
    Uint16 psm;
    Uint8 address[6];
    Uint16 cid;
    Uint8 type;
} FP_Address;
#else
#include "../../core/windows/SDL_windows.h"
typedef struct { Uint8 address[6]; } FP_Address;
#endif

typedef struct {
    SDL_AtomicInt quit, ready;
    SDL_Thread *thread;
    SDL_Mutex *mutex;
    FP_Address local, remote;
    Uint8 packets[256][20];
    Uint64 timestamps[256];
    Uint8 rumble[2];
    bool rumble_dirty;
    int first, count, player, stream_mode;
    SDL_JoystickID id;
    char device_address[18], connected_address[18];
    char requested_device[18], requested_adapter[18];
} FP_Context;
static FP_Context fp;

static bool FP_ParseAddress(const char *value, Uint8 out[6])
{
    if (!value || SDL_strlen(value) != 17) return false;
    for (int i = 0; i < 6; ++i) {
        int byte = 0;
        for (int j = 0; j < 2; ++j) {
            char c = value[i * 3 + j];
            int digit = c >= '0' && c <= '9' ? c - '0' :
                        c >= 'a' && c <= 'f' ? c - 'a' + 10 :
                        c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (digit < 0) return false;
            byte = byte * 16 + digit;
        }
        if (i < 5 && value[i * 3 + 2] != ':') return false;
        out[5 - i] = (Uint8)byte;
    }
    return true;
}

#ifdef SDL_JOYSTICK_LINUX
#include "SDL_flydigi_flashplay_bluez.h"

static void FP_Failure(const char *stage, int error)
{
    static const char *last_stage;
    static int last_error;
    if (stage == last_stage && error == last_error) return;
    last_stage = stage; last_error = error;
    if (stage) SDL_LogWarn(SDL_LOG_CATEGORY_INPUT, "Flashplay: %s (%d)", stage, error);
}

static int FP_Read(int fd, Uint8 *reply, size_t capacity, int timeout)
{
    struct pollfd p = { fd, POLLIN, 0 };
    int n;
    do { n = poll(&p, 1, timeout); } while (n < 0 && errno == EINTR);
    if (n <= 0 || (p.revents & (POLLERR | POLLHUP | POLLNVAL))) return -1;
    return (int)recv(fd, reply, capacity, 0);
}

static int FP_Request(int fd, const Uint8 *request, size_t size, Uint8 *reply)
{
    Uint64 until = SDL_GetTicks() + 1000;
    if (send(fd, request, size, MSG_NOSIGNAL) != (ssize_t)size) return -1;
    while (SDL_GetTicks() < until && !SDL_GetAtomicInt(&fp.quit)) {
        int n = FP_Read(fd, reply, 128, 100);
        if (n < 0) continue;
        if (!n) return -1;
        if (reply[0] == 0x1d) {
            const Uint8 ack = 0x1e;
            send(fd, &ack, 1, MSG_NOSIGNAL);
        } else if (reply[0] != 0x1b) return n;
    }
    return -1;
}

static bool FP_Command(int fd, bool enabled)
{
    Uint8 p[23] = { 0x52, 0x24, 0x00, 0x41, 0 };
    p[4] = enabled ? (Uint8)fp.stream_mode : 0;
    p[22] = (Uint8)(0x41 + p[4]);
    return send(fd, p, sizeof(p), MSG_NOSIGNAL) == sizeof(p);
}

/* Android SDK cb.e.n/o: two motor amplitudes, final field 100.
 * Its time unit is not established; refresh active effects and explicitly stop.
 * Only the worker writes to the ATT socket, including during shutdown.
 */
static bool FP_SendRumble(int fd, Uint8 left, Uint8 right)
{
    const Uint8 p[] = { 0x52, 0x24, 0, 0x11, left, right,
                        (left || right) ? 100 : 0 };
    return send(fd, p, sizeof(p), MSG_NOSIGNAL) == sizeof(p);
}

static int FP_Connect(void)
{
    int fd = socket(AF_BLUETOOTH, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0 /* BTPROTO_L2CAP */);
    struct pollfd p;
    int error = 0;
    socklen_t len = sizeof(error);
    if (fd < 0) return -1;
    if (bind(fd, (struct sockaddr *)&fp.local, sizeof(fp.local)) < 0) goto failed;
    if (connect(fd, (struct sockaddr *)&fp.remote, sizeof(fp.remote)) < 0) {
        if (errno != EINPROGRESS) goto failed;
        p.fd = fd; p.events = POLLOUT; p.revents = 0;
        Uint64 deadline = SDL_GetTicks() + 6000;
        while (!SDL_GetAtomicInt(&fp.quit)) {
            int ready = poll(&p, 1, 100);
            if (ready < 0 && errno == EINTR) continue;
            if (ready < 0) goto failed;
            if (ready > 0) {
                if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0) goto failed;
                if (error) { errno = error; goto failed; }
                return fd;
            }
            if (SDL_GetTicks() >= deadline) { errno = ETIMEDOUT; goto failed; }
        }
        errno = ECANCELED;
        goto failed;
    }
    return fd;
failed:
    error = errno;
    close(fd);
    errno = error;
    return -1;
}

static int SDLCALL FP_Worker(void *unused)
{
    const Uint8 name_request[] = { 0x0a, 0x03, 0x00 };
    const Uint8 rx_request[] = { 0x08, 0x22, 0, 0x29, 0, 0x03, 0x28 };
    const Uint8 tx_request[] = { 0x08, 0x24, 0, 0x29, 0, 0x03, 0x28 };
    const Uint8 rx_expected[] = { 0x09,0x15,0x23,0,0x08,0x24,0,0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x02,0,0x40,0x6e };
    const Uint8 tx_expected[] = { 0x09,0x15,0x26,0,0x10,0x27,0,0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x03,0,0x40,0x6e };
    const Uint8 cccd_request[] = { 0x0a,0x29,0 };
    const Uint8 subscribe[] = { 0x12,0x29,0,1,0 };
    while (!SDL_GetAtomicInt(&fp.quit)) {
        Uint8 reply[128], restore[] = { 0x12,0x29,0,0,0 };
        bool subscribed = false, started = false;
        int n, fd;
        if (!FP_ResolveAddress()) goto retry;
        fd = FP_Connect();
        if (fd < 0) { FP_Failure("Bluetooth connection failed", errno); goto retry; }
        n = FP_Request(fd, name_request, sizeof(name_request), reply);
        if (n != 20 || reply[0] != 0x0b || SDL_memcmp(reply + 1, "Flydigi Vader 5 Pro", 19)) { FP_Failure("device name response", n); goto cleanup; }
        n = FP_Request(fd, rx_request, sizeof(rx_request), reply);
        if (n != sizeof(rx_expected) || SDL_memcmp(reply, rx_expected, sizeof(rx_expected))) { FP_Failure("UART RX discovery", n); goto cleanup; }
        n = FP_Request(fd, tx_request, sizeof(tx_request), reply);
        if (n != sizeof(tx_expected) || SDL_memcmp(reply, tx_expected, sizeof(tx_expected))) { FP_Failure("UART TX discovery", n); goto cleanup; }
        n = FP_Request(fd, cccd_request, sizeof(cccd_request), reply);
        if ((n != 2 && n != 3) || reply[0] != 0x0b || (n == 2 && reply[1] > 3)) { FP_Failure("notification descriptor read", n); goto cleanup; }
        restore[3] = reply[1]; restore[4] = n == 3 ? reply[2] : 0;
        n = FP_Request(fd, subscribe, sizeof(subscribe), reply);
        if (n != 1 || reply[0] != 0x13) { FP_Failure("notification subscription", n); goto cleanup; }
        subscribed = true;
        if (!FP_Command(fd, true)) { FP_Failure("stream start", errno); goto cleanup; }
        started = true;
        SDL_LockMutex(fp.mutex);
        fp.first = fp.count = 0;
        fp.rumble[0] = fp.rumble[1] = 0;
        fp.rumble_dirty = false;
        SDL_UnlockMutex(fp.mutex);
        /* Publish only after the first actual input report, not just a connection. */
        {
            Uint64 last_packet = SDL_GetTicks();
            Uint64 last_rumble = 0;
            while (!SDL_GetAtomicInt(&fp.quit)) {
                Uint8 left, right;
                bool dirty;
                SDL_LockMutex(fp.mutex);
                left = fp.rumble[0]; right = fp.rumble[1];
                dirty = fp.rumble_dirty;
                fp.rumble_dirty = false;
                SDL_UnlockMutex(fp.mutex);
                if (dirty || ((left || right) && SDL_GetTicks() - last_rumble >= 80)) {
                    if (!FP_SendRumble(fd, left, right)) break;
                    last_rumble = SDL_GetTicks();
                }
                struct pollfd p = { fd, POLLIN, 0 };
                int ready = poll(&p, 1, 20);
                if (ready < 0 && errno == EINTR) continue;
                if (ready < 0 || (p.revents & (POLLERR | POLLHUP | POLLNVAL))) break;
                if (!ready) {
                    if (SDL_GetTicks() - last_packet > 3000) { FP_Failure("input stream timeout", 0); break; }
                    continue;
                }
                n = (int)recv(fd, reply, sizeof(reply), 0);
                if (n <= 0) break;
                if (reply[0] == 0x1d) {
                    const Uint8 ack = 0x1e;
                    send(fd, &ack, 1, MSG_NOSIGNAL);
                }
                if (n != 23 || reply[0] != 0x1b || reply[1] != 0x27 || reply[2] ||
                    reply[21] != 0xfe || reply[22] != 0) continue;
                last_packet = SDL_GetTicks();
                FP_Failure(NULL, 0);
                SDL_LockMutex(fp.mutex);
                if (fp.count == 256) { fp.first = (fp.first + 1) % 256; --fp.count; }
                SDL_memcpy(fp.packets[(fp.first + fp.count) % 256], reply + 3, 20);
                fp.timestamps[(fp.first + fp.count) % 256] = SDL_GetTicksNS();
                ++fp.count;
                SDL_UnlockMutex(fp.mutex);
                SDL_SetAtomicInt(&fp.ready, 1);
            }
        }
cleanup:
        SDL_SetAtomicInt(&fp.ready, 0);
        if (started) {
            FP_SendRumble(fd, 0, 0);
            FP_Command(fd, false);
        }
        if (subscribed) {
            /* Shutdown also restores CCCD, even when quit is already set. */
            if (send(fd, restore, sizeof(restore), MSG_NOSIGNAL) == sizeof(restore)) {
                for (int i = 0; i < 5; ++i) {
                    n = FP_Read(fd, reply, sizeof(reply), 100);
                    if (n == 1 && reply[0] == 0x13) break;
                }
            }
        }
        close(fd);
retry:
        for (int i = 0; i < 30 && !SDL_GetAtomicInt(&fp.quit); ++i) SDL_Delay(100);
    }
    return 0;
}

#else
#include "SDL_flydigi_flashplay_windows.h"
#endif

/* The CLI saves two addresses here. Read a bounded file, without creating it.
 * Explicit hints take precedence, including an empty hint to disable Flashplay.
 */
static void FP_ReadConfig(char device[18], char adapter[18])
{
    char *path = NULL, data[128];
    Uint8 address[6];
#ifdef SDL_PLATFORM_WINDOWS
    const char *appdata = SDL_GetEnvironmentVariable(SDL_GetEnvironment(), "APPDATA");
    if (appdata && *appdata) SDL_asprintf(&path, "%s/Vader5Control/bluetooth", appdata);
#else
    const char *base = SDL_GetEnvironmentVariable(SDL_GetEnvironment(), "XDG_CONFIG_HOME");
    const char *home = SDL_GetEnvironmentVariable(SDL_GetEnvironment(), "HOME");
    if (base && *base) SDL_asprintf(&path, "%s/vader5/bluetooth", base);
    else if (home && *home) SDL_asprintf(&path, "%s/.config/vader5/bluetooth", home);
#endif
    if (!path) return;
    SDL_IOStream *io = SDL_IOFromFile(path, "rb");
    SDL_free(path);
    if (!io) return;
    size_t n = SDL_ReadIO(io, data, sizeof(data) - 1);
    SDL_CloseIO(io);
    data[n] = 0;
    char *second = SDL_strchr(data, '\n');
    if (second) *second++ = 0;
    else second = data + n;
    char *end = SDL_strchr(second, '\n');
    if (end) *end = 0;
    if (FP_ParseAddress(data, address)) SDL_strlcpy(device, data, 18);
    if (FP_ParseAddress(second, address)) SDL_strlcpy(adapter, second, 18);
}

static bool FP_Init(void)
{
    const char *device = SDL_GetHint("SDL_FLYDIGI_BT_ADDRESS");
    const char *adapter = SDL_GetHint("SDL_FLYDIGI_BT_ADAPTER");
    const char *mode = SDL_GetHint("SDL_FLYDIGI_BT_STREAM_MODE");
    char saved_device[18] = {0}, saved_adapter[18] = {0};
    SDL_zero(fp); fp.player = -1;
    if (!device || !adapter) FP_ReadConfig(saved_device, saved_adapter);
    if (!device) device = saved_device;
    if (!adapter) adapter = (device && SDL_strcasecmp(device, saved_device) == 0) ? saved_adapter : "";
    if (device && !*device && SDL_GetHint("SDL_FLYDIGI_BT_ADDRESS")) return true;
#ifdef SDL_JOYSTICK_LINUX
#ifdef SDL_USE_LIBDBUS
    fp_dbus = SDL_DBus_GetContext();
#else
    if (!device || !*device) return true;
#endif
#else
    if (!device || !*device) return true;
#endif
    if (mode && SDL_strcmp(mode, "1") && SDL_strcmp(mode, "2"))
        return SDL_SetError("SDL_FLYDIGI_BT_STREAM_MODE must be 1 or 2");
    fp.stream_mode = mode ? SDL_atoi(mode) : 2;
    if (device && *device && !FP_ParseAddress(device, fp.remote.address))
        return SDL_SetError("Invalid Flashplay Bluetooth device address");
    if (device) {
        SDL_strlcpy(fp.requested_device, device, sizeof(fp.requested_device));
        SDL_strlcpy(fp.device_address, device, sizeof(fp.device_address));
        SDL_strlcpy(fp.connected_address, device, sizeof(fp.connected_address));
    }
    if (adapter) SDL_strlcpy(fp.requested_adapter, adapter, sizeof(fp.requested_adapter));
#ifdef SDL_JOYSTICK_LINUX
    if (adapter && *adapter && !FP_ParseAddress(adapter, fp.local.address))
        return SDL_SetError("Invalid Flashplay Bluetooth adapter address");
    fp.local.family = fp.remote.family = AF_BLUETOOTH;
    fp.local.cid = fp.remote.cid = SDL_Swap16LE(4);
    fp.local.type = fp.remote.type = 1; /* BDADDR_LE_PUBLIC */
#else
    (void)adapter;
#endif
    fp.mutex = SDL_CreateMutex();
    if (!fp.mutex) return false;
    fp.thread = SDL_CreateThread(FP_Worker, "Flydigi Flashplay", NULL);
    if (!fp.thread) { SDL_DestroyMutex(fp.mutex); fp.mutex = NULL; return false; }
    return true;
}
static int FP_Count(void) { return fp.id ? 1 : 0; }
static void FP_Detect(void)
{
    if (SDL_GetAtomicInt(&fp.ready) && !fp.id) {
        SDL_LockMutex(fp.mutex);
        SDL_strlcpy(fp.device_address, fp.connected_address, sizeof(fp.device_address));
        SDL_UnlockMutex(fp.mutex);
        fp.id = SDL_GetNextObjectID();
        SDL_PrivateJoystickAdded(fp.id);
    } else if (!SDL_GetAtomicInt(&fp.ready) && fp.id) {
        SDL_JoystickID old = fp.id; fp.id = 0;
        SDL_PrivateJoystickRemoved(old);
    }
}
static bool FP_Present(Uint16 v, Uint16 p, Uint16 version, const char *name) { return false; }
static const char *FP_Name(int index) { return "Flydigi Vader 5 Pro (Bluetooth Flashplay)"; }
static const char *FP_Path(int index) { return fp.device_address; }
static int FP_Slot(int index) { return -1; }
static int FP_Player(int index) { return fp.player; }
static void FP_SetPlayer(int index, int player) { fp.player = player; }
static SDL_GUID FP_GUID(int index) { return SDL_CreateJoystickGUID(SDL_HARDWARE_BUS_BLUETOOTH, 0x37d7, 0x2401, 0, "Flydigi", FP_Name(0), 'b', 0); }
static SDL_JoystickID FP_ID(int index) { return fp.id; }
static bool FP_Open(SDL_Joystick *joystick, int index)
{
    if (!fp.id || !SDL_GetAtomicInt(&fp.ready)) return SDL_SetError("Flashplay controller disconnected");
    joystick->nbuttons = 21; joystick->naxes = 6; joystick->nhats = 1;
    SDL_SetBooleanProperty(SDL_GetJoystickProperties(joystick), SDL_PROP_JOYSTICK_CAP_RUMBLE_BOOLEAN, true);
    return true;
}
static bool FP_Rumble(SDL_Joystick *j, Uint16 a, Uint16 b)
{
    if (j->instance_id != fp.id || !SDL_GetAtomicInt(&fp.ready))
        return SDL_SetError("Flashplay controller disconnected");
    SDL_LockMutex(fp.mutex);
    fp.rumble[0] = (Uint8)(((Uint32)a * 255 + 32767) / 65535);
    fp.rumble[1] = (Uint8)(((Uint32)b * 255 + 32767) / 65535);
    fp.rumble_dirty = true;
    SDL_UnlockMutex(fp.mutex);
    return true;
}
static bool FP_TriggerRumble(SDL_Joystick *j, Uint16 a, Uint16 b) { return SDL_Unsupported(); }
static bool FP_LED(SDL_Joystick *j, Uint8 a, Uint8 b, Uint8 c) { return SDL_Unsupported(); }
static bool FP_Effect(SDL_Joystick *j, const void *data, int size) { return SDL_Unsupported(); }
static bool FP_Sensors(SDL_Joystick *j, bool enabled) { return SDL_Unsupported(); }
static void FP_Update(SDL_Joystick *joystick)
{
    static const Uint8 offsets[21] = {4,4,4,5,4,8,5,5,5,5,5,9,9,9,9,9,9,9,9,8,8};
    static const Uint8 masks[21] = {0x10,0x20,0x80,1,0x40,8,2,0x40,0x80,4,8,8,4,0x20,0x10,1,2,0x40,0x80,1,2};
    for (int processed = 0; processed < 256; ++processed) {
        Uint8 p[20];
        Uint64 now;
        SDL_LockMutex(fp.mutex);
        if (!fp.count) { SDL_UnlockMutex(fp.mutex); break; }
        SDL_memcpy(p, fp.packets[fp.first], 20);
        now = fp.timestamps[fp.first];
        fp.first = (fp.first + 1) % 256; --fp.count;
        SDL_UnlockMutex(fp.mutex);
        for (int i = 0; i < 21; ++i) SDL_SendJoystickButton(now, joystick, i, (p[offsets[i]] & masks[i]) != 0);
        SDL_SendJoystickHat(now, joystick, 0, p[4] & 15);
        for (int i = 0; i < 4; ++i) SDL_SendJoystickAxis(now, joystick, i, (Sint16)((int)p[i] * 257 - 32768));
        SDL_SendJoystickAxis(now, joystick, 4, (Sint16)((int)p[6] * 257 - 32768));
        SDL_SendJoystickAxis(now, joystick, 5, (Sint16)((int)p[7] * 257 - 32768));
    }
}
static void FP_Close(SDL_Joystick *j)
{
    /* An old handle must not stop effects on a newly reconnected controller. */
    if (j->instance_id != fp.id) return;
    SDL_LockMutex(fp.mutex);
    fp.rumble[0] = fp.rumble[1] = 0;
    fp.rumble_dirty = true;
    SDL_UnlockMutex(fp.mutex);
}
static void FP_Quit(void)
{
    SDL_SetAtomicInt(&fp.quit, 1);
    if (fp.thread) SDL_WaitThread(fp.thread, NULL);
    if (fp.mutex) SDL_DestroyMutex(fp.mutex);
    SDL_zero(fp);
}
static void FP_Button(SDL_InputMapping *m, int target) { m->kind = EMappingKind_Button; m->target = target; }
static void FP_Axis(SDL_InputMapping *m, int target) { m->kind = EMappingKind_Axis; m->target = target; }
static bool FP_Mapping(int index, SDL_GamepadMapping *m)
{
    SDL_zero(*m);
    FP_Button(&m->a,0); FP_Button(&m->b,1); FP_Button(&m->x,2); FP_Button(&m->y,3);
    FP_Button(&m->back,4); FP_Button(&m->guide,5); FP_Button(&m->start,6);
    FP_Button(&m->leftstick,7); FP_Button(&m->rightstick,8);
    FP_Button(&m->leftshoulder,9); FP_Button(&m->rightshoulder,10);
    /* M1-M4 use misc slots; LM/RM and C/Z use paddle slots. */
    FP_Button(&m->right_paddle1,18); FP_Button(&m->left_paddle1,17);
    FP_Button(&m->right_paddle2,15); FP_Button(&m->left_paddle2,16);
    FP_Button(&m->misc1,20); FP_Button(&m->misc2,11); FP_Button(&m->misc3,12);
    FP_Button(&m->misc4,13); FP_Button(&m->misc5,14); FP_Button(&m->misc6,19);
    m->dpup.kind = m->dpdown.kind = m->dpleft.kind = m->dpright.kind = EMappingKind_Hat;
    m->dpup.target = 1; m->dpdown.target = 4; m->dpleft.target = 8; m->dpright.target = 2;
    FP_Axis(&m->leftx,0); FP_Axis(&m->lefty,1); FP_Axis(&m->rightx,2);
    FP_Axis(&m->righty,3); FP_Axis(&m->lefttrigger,4); FP_Axis(&m->righttrigger,5);
    return true;
}
SDL_JoystickDriver SDL_FLYDIGI_FLASHPLAY_JoystickDriver = {
    FP_Init, FP_Count, FP_Detect, FP_Present, FP_Name, FP_Path, FP_Slot,
    FP_Player, FP_SetPlayer, FP_GUID, FP_ID, FP_Open, FP_Rumble, FP_TriggerRumble,
    FP_LED, FP_Effect, FP_Sensors, FP_Update, FP_Close, FP_Quit, FP_Mapping
};
#endif

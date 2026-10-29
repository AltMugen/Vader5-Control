/* Vader5 Control: experimental Windows desktop GATT transport, zlib license.
 * Included by SDL_flydigi_flashplay.c. Pair Flashplay in Windows first.
 */
#include <setupapi.h>
#include <bluetoothleapis.h>

static const GUID FP_NUS = {0x6e400001,0xb5a3,0xf393,{0xe0,0xa9,0xe5,0x0e,0x24,0xdc,0xca,0x9e}};
static const GUID FP_RX = {0x6e400002,0xb5a3,0xf393,{0xe0,0xa9,0xe5,0x0e,0x24,0xdc,0xca,0x9e}};
static const GUID FP_TX = {0x6e400003,0xb5a3,0xf393,{0xe0,0xa9,0xe5,0x0e,0x24,0xdc,0xca,0x9e}};

static bool FP_WinIsRX(const BTH_LE_GATT_CHARACTERISTIC *characteristic)
{
    return !characteristic->CharacteristicUuid.IsShortUuid &&
        IsEqualGUID(&characteristic->CharacteristicUuid.Value.LongUuid, &FP_RX) &&
        (characteristic->IsWritable || characteristic->IsWritableWithoutResponse);
}

static bool FP_WinResult(const char *stage, HRESULT result, Uint64 since)
{
    SDL_LogDebug(SDL_LOG_CATEGORY_INPUT,
                 "Flashplay: %s hr=0x%08lx elapsed=%" SDL_PRIu64 " ms",
                 stage, (unsigned long)result, SDL_GetTicks() - since);
    return SUCCEEDED(result);
}

typedef struct {
    HANDLE device;
    BTH_LE_GATT_CHARACTERISTIC rx, tx;
    SDL_AtomicInt accept;
    Uint64 last_packet;
} FP_WinSession;

static HANDLE FP_WinOpen(void)
{
    HDEVINFO devices = SetupDiGetClassDevsW(&FP_NUS, NULL, NULL, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    HANDLE result = INVALID_HANDLE_VALUE;
    DWORD error = ERROR_NOT_FOUND;
    char mac[13];
    if (devices == INVALID_HANDLE_VALUE) return result;
    SDL_snprintf(mac, sizeof(mac), "%02x%02x%02x%02x%02x%02x", fp.remote.address[5], fp.remote.address[4],
                 fp.remote.address[3], fp.remote.address[2], fp.remote.address[1], fp.remote.address[0]);
    for (DWORD i = 0; ; ++i) {
        SP_DEVICE_INTERFACE_DATA iface;
        PSP_DEVICE_INTERFACE_DETAIL_DATA_W detail;
        DWORD size = 0;
        SDL_zero(iface); iface.cbSize = sizeof(iface);
        if (!SetupDiEnumDeviceInterfaces(devices, NULL, &FP_NUS, i, &iface)) break;
        SetupDiGetDeviceInterfaceDetailW(devices, &iface, NULL, 0, &size, NULL);
        if (size < sizeof(*detail)) continue;
        detail = (PSP_DEVICE_INTERFACE_DETAIL_DATA_W)SDL_malloc(size);
        if (!detail) break;
        detail->cbSize = sizeof(*detail);
        if (SetupDiGetDeviceInterfaceDetailW(devices, &iface, detail, size, NULL, NULL)) {
            char *path = WIN_StringToUTF8W(detail->DevicePath);
            if (path && SDL_strcasestr(path, mac)) {
                result = CreateFileW(detail->DevicePath, GENERIC_READ | GENERIC_WRITE,
                                     FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
                if (result == INVALID_HANDLE_VALUE) error = GetLastError();
            }
            SDL_free(path);
        }
        SDL_free(detail);
        if (result != INVALID_HANDLE_VALUE) break;
    }
    SetupDiDestroyDeviceInfoList(devices);
    if (result == INVALID_HANDLE_VALUE) SetLastError(error);
    return result;
}

static bool FP_WinWrite(FP_WinSession *session, const Uint8 *data, ULONG size)
{
    struct { ULONG DataSize; UCHAR Data[20]; } value;
    if (size > sizeof(value.Data)) return false;
    value.DataSize = size;
    SDL_memcpy(value.Data, data, size);
    Uint64 since = SDL_GetTicks();
    HRESULT result = BluetoothGATTSetCharacteristicValue(session->device, &session->rx,
        (PBTH_LE_GATT_CHARACTERISTIC_VALUE)&value, 0, BLUETOOTH_GATT_FLAG_WRITE_WITHOUT_RESPONSE);
    return FP_WinResult(data[0] == 0x41 ? "stream command" : "rumble command", result, since);
}

static bool FP_WinMode(FP_WinSession *session, int mode)
{
    Uint8 data[20] = {0x41};
    data[1] = (Uint8)mode; data[19] = (Uint8)(0x41 + mode);
    return FP_WinWrite(session, data, sizeof(data));
}

static bool FP_WinRumble(FP_WinSession *session, Uint8 left, Uint8 right)
{
    const Uint8 data[] = {0x11, left, right, (left || right) ? 100 : 0};
    return FP_WinWrite(session, data, sizeof(data));
}

static VOID CALLBACK FP_WinNotify(BTH_LE_GATT_EVENT_TYPE type, PVOID event, PVOID context)
{
    FP_WinSession *session = (FP_WinSession *)context;
    const BLUETOOTH_GATT_VALUE_CHANGED_EVENT *value = (const BLUETOOTH_GATT_VALUE_CHANGED_EVENT *)event;
    const Uint8 *data;
    if (!SDL_GetAtomicInt(&session->accept) || type != CharacteristicValueChangedEvent || !value ||
        value->ChangedAttributeHandle != session->tx.CharacteristicValueHandle ||
        !value->CharacteristicValue || value->CharacteristicValue->DataSize != 20) return;
    data = value->CharacteristicValue->Data;
    if (data[18] != 0xfe || data[19] != 0) return;
    SDL_LockMutex(fp.mutex);
    if (fp.count == 256) { fp.first = (fp.first + 1) % 256; --fp.count; }
    SDL_memcpy(fp.packets[(fp.first + fp.count) % 256], data, 20);
    fp.timestamps[(fp.first + fp.count) % 256] = SDL_GetTicksNS();
    ++fp.count;
    session->last_packet = SDL_GetTicks();
    SDL_UnlockMutex(fp.mutex);
    if (!SDL_GetAtomicInt(&fp.ready))
        SDL_LogDebug(SDL_LOG_CATEGORY_INPUT, "Flashplay: first input notification");
    SDL_SetAtomicInt(&fp.ready, 1);
}

static int SDLCALL FP_Worker(void *unused)
{
    while (!SDL_GetAtomicInt(&fp.quit)) {
        FP_WinSession session;
        BTH_LE_GATT_CHARACTERISTIC chars[8];
        BTH_LE_GATT_DESCRIPTOR descriptors[8], cccd;
        BTH_LE_GATT_DESCRIPTOR_VALUE subscription;
        BLUETOOTH_GATT_EVENT_HANDLE event = NULL;
        BLUETOOTH_GATT_VALUE_CHANGED_EVENT_REGISTRATION registration;
        USHORT count = 0;
        bool found_rx = false, found_tx = false, found_cccd = false, subscribed = false, started = false;
        Uint64 last_rumble = 0, since;
        HRESULT result;
        SDL_zero(session);
        since = SDL_GetTicks();
        session.device = FP_WinOpen();
        FP_WinResult("open NUS interface", session.device == INVALID_HANDLE_VALUE ?
                     HRESULT_FROM_WIN32(GetLastError()) : S_OK, since);
        if (session.device == INVALID_HANDLE_VALUE) goto retry;
        since = SDL_GetTicks();
        result = BluetoothGATTGetCharacteristics(session.device, NULL, SDL_arraysize(chars), chars, &count, 0);
        if (!FP_WinResult("get characteristics", result, since)) goto cleanup;
        for (USHORT i = 0; i < count; ++i) {
            /* The vendor declares RX as Write (08) but parses commands via
             * ATT Write Command (52). Keep that wire operation; do not exclude
             * this characteristic or alter the descriptor returned by Windows. */
            if (FP_WinIsRX(&chars[i])) {
                session.rx = chars[i]; found_rx = true;
            }
            if (!chars[i].CharacteristicUuid.IsShortUuid && IsEqualGUID(&chars[i].CharacteristicUuid.Value.LongUuid, &FP_TX) && chars[i].IsNotifiable) {
                session.tx = chars[i]; found_tx = true;
            }
        }
        if (!found_rx || !found_tx) {
            SDL_LogDebug(SDL_LOG_CATEGORY_INPUT, "Flashplay: missing RX/TX characteristic");
            goto cleanup;
        }
        since = SDL_GetTicks();
        result = BluetoothGATTGetDescriptors(session.device, &session.tx, SDL_arraysize(descriptors), descriptors, &count, 0);
        if (!FP_WinResult("get descriptors", result, since)) goto cleanup;
        for (USHORT i = 0; i < count; ++i) {
            if (descriptors[i].DescriptorType == ClientCharacteristicConfiguration) {
                cccd = descriptors[i]; found_cccd = true; break;
            }
        }
        if (!found_cccd) goto cleanup;
        /* SI3605 returns a constant one-byte CCCD value, not subscription state.
         * Reading it is neither a prerequisite for subscribing nor a snapshot
         * that can be restored. This transport owns its single stream session. */
        SDL_zero(subscription);
        subscription.DescriptorType = ClientCharacteristicConfiguration;
        subscription.DescriptorUuid = cccd.DescriptorUuid;
        subscription.ClientCharacteristicConfiguration.IsSubscribeToNotification = TRUE;
        SDL_zero(registration); registration.NumCharacteristics = 1; registration.Characteristics[0] = session.tx;
        since = SDL_GetTicks();
        result = BluetoothGATTRegisterEvent(session.device, CharacteristicValueChangedEvent, &registration,
                                           FP_WinNotify, &session, &event, 0);
        if (!FP_WinResult("register notifications", result, since)) goto cleanup;
        since = SDL_GetTicks();
        result = BluetoothGATTSetDescriptorValue(session.device, &cccd, &subscription, 0);
        if (!FP_WinResult("enable notifications", result, since)) goto cleanup;
        subscribed = true;
        SDL_LockMutex(fp.mutex);
        fp.first = fp.count = 0; fp.rumble[0] = fp.rumble[1] = 0; fp.rumble_dirty = false;
        session.last_packet = SDL_GetTicks();
        SDL_UnlockMutex(fp.mutex);
        SDL_SetAtomicInt(&session.accept, 1);
        if (!FP_WinMode(&session, fp.stream_mode)) goto cleanup;
        started = true;
        while (!SDL_GetAtomicInt(&fp.quit)) {
            Uint8 left, right;
            bool dirty;
            Uint64 last_packet;
            SDL_LockMutex(fp.mutex);
            left = fp.rumble[0]; right = fp.rumble[1]; dirty = fp.rumble_dirty;
            fp.rumble_dirty = false; last_packet = session.last_packet;
            SDL_UnlockMutex(fp.mutex);
            if (SDL_GetTicks() - last_packet > 3000) {
                SDL_LogDebug(SDL_LOG_CATEGORY_INPUT, "Flashplay: input timeout");
                break;
            }
            if (dirty || ((left || right) && SDL_GetTicks() - last_rumble >= 80)) {
                if (!FP_WinRumble(&session, left, right)) break;
                last_rumble = SDL_GetTicks();
            }
            SDL_Delay(10);
        }
cleanup:
        SDL_SetAtomicInt(&session.accept, 0);
        if (event) BluetoothGATTUnregisterEvent(event, 0);
        SDL_SetAtomicInt(&fp.ready, 0);
        if (started) { FP_WinRumble(&session, 0, 0); FP_WinMode(&session, 0); }
        if (subscribed) {
            subscription.ClientCharacteristicConfiguration.IsSubscribeToNotification = FALSE;
            since = SDL_GetTicks();
            result = BluetoothGATTSetDescriptorValue(session.device, &cccd, &subscription, 0);
            FP_WinResult("disable notifications", result, since);
        }
        CloseHandle(session.device);
retry:
        for (int i = 0; i < 30 && !SDL_GetAtomicInt(&fp.quit); ++i) SDL_Delay(100);
    }
    return 0;
}

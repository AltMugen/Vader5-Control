/* Offline tests of the Windows Flashplay RX selection and packet builders. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>
#include <setupapi.h>
#include <bluetoothleapis.h>
#include <SDL3/SDL.h>

static struct {
    struct { Uint8 address[6]; } remote;
    SDL_Mutex *mutex;
    SDL_AtomicInt quit, ready;
    Uint8 packets[256][20], rumble[2];
    Uint64 timestamps[256];
    unsigned first, count;
    bool rumble_dirty;
    int stream_mode;
} fp;
static char *WIN_StringToUTF8W(const wchar_t *text) { (void)text; return NULL; }
static ULONG sent_size, sent_flags;
static HRESULT sent_result = S_OK;
static Uint8 sent[20];
static HRESULT WINAPI mock_write(HANDLE device, PBTH_LE_GATT_CHARACTERISTIC characteristic,
        PBTH_LE_GATT_CHARACTERISTIC_VALUE value,
        BTH_LE_GATT_RELIABLE_WRITE_CONTEXT context, ULONG flags)
{
    (void)device; (void)characteristic; (void)context;
    sent_size=value->DataSize;sent_flags=flags;
    assert(sent_size<=sizeof(sent));memcpy(sent,value->Data,sent_size);
    return sent_result;
}
#define BluetoothGATTSetCharacteristicValue mock_write
#define SDL_memcpy memcpy
#define SDL_LogDebug(...) ((void)0)
#define SDL_GetTicks() ((Uint64)0)
#include "../src/flashplay/SDL_flydigi_flashplay_windows.h"

int main(void)
{
    BTH_LE_GATT_CHARACTERISTIC characteristic={0};
    characteristic.CharacteristicUuid.Value.LongUuid=FP_RX;
    assert(!FP_WinIsRX(&characteristic));
    characteristic.IsWritable=TRUE;
    assert(FP_WinIsRX(&characteristic));
    characteristic.IsWritable=FALSE;characteristic.IsWritableWithoutResponse=TRUE;
    assert(FP_WinIsRX(&characteristic));
    characteristic.CharacteristicUuid.IsShortUuid=TRUE;
    assert(!FP_WinIsRX(&characteristic));
    characteristic.CharacteristicUuid.IsShortUuid=FALSE;
    characteristic.CharacteristicUuid.Value.LongUuid=FP_TX;
    assert(!FP_WinIsRX(&characteristic));
    FP_WinSession session={0};
    assert(FP_WinMode(&session,2));
    assert(sent_size==20 && sent[0]==0x41 && sent[1]==2 && sent[19]==0x43);
    assert(sent_flags==BLUETOOTH_GATT_FLAG_WRITE_WITHOUT_RESPONSE);
    assert(FP_WinMode(&session,0));assert(sent[1]==0 && sent[19]==0x41);
    assert(FP_WinRumble(&session,20,30));
    assert(sent_size==4 && sent[0]==0x11 && sent[1]==20 && sent[2]==30 && sent[3]==100);
    assert(FP_WinRumble(&session,0,0));assert(sent[3]==0);
    Uint8 oversized[21]={0};assert(!FP_WinWrite(&session,oversized,sizeof(oversized)));
    sent_result = E_ACCESSDENIED;
    assert(!FP_WinMode(&session, 2));
    puts("Windows Flashplay selection, packets and errors OK");return 0;
}

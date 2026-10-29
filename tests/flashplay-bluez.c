/* Offline BlueZ object parsing. No bus or controller is contacted. */
#include <assert.h>
#include <SDL3/SDL.h>
#define SDL_internal_h_
#define HAVE_DBUS_DBUS_H 1
#include "SDL_dbus.h"
static struct {
    SDL_Mutex *mutex;
    char requested_device[18], requested_adapter[18], connected_address[18];
    struct { Uint8 address[6]; } local, remote;
} fp;
static bool FP_ParseAddress(const char *s, Uint8 out[6])
{
    if (!s || SDL_strlen(s) != 17) return false;
    for (int i = 0; i < 6; ++i) {
        unsigned value;
        if (SDL_sscanf(s + 3*i, "%2x", &value) != 1) return false;
        out[5-i] = (Uint8)value;
    }
    return true;
}
#include "SDL_flydigi_flashplay_bluez.h"
static DBusMessage *fixture;
static DBusConnection *fake_bus(DBusBusType type, DBusError *error) { return (DBusConnection *)1; }
static void fake_close(DBusConnection *c) {}
static void fake_exit(DBusConnection *c, dbus_bool_t value) {}
static DBusMessage *fake_call(DBusConnection *c, DBusMessage *m, int timeout, DBusError *error)
{
    return dbus_message_ref(fixture);
}
static void property(DBusMessageIter *properties, const char *key, int type, const void *value)
{
    DBusMessageIter pair, variant;
    char signature[] = {(char)type, 0};
    assert(dbus_message_iter_open_container(properties, DBUS_TYPE_DICT_ENTRY, NULL, &pair));
    assert(dbus_message_iter_append_basic(&pair, DBUS_TYPE_STRING, &key));
    assert(dbus_message_iter_open_container(&pair, DBUS_TYPE_VARIANT, signature, &variant));
    assert(dbus_message_iter_append_basic(&variant, type, value));
    assert(dbus_message_iter_close_container(&pair, &variant));
    assert(dbus_message_iter_close_container(properties, &pair));
}
static void object(DBusMessageIter *objects, const char *path, bool adapter,
                   const char *address, const char *name, bool powered)
{
    DBusMessageIter entry, interfaces, item, properties;
    const char *iface = adapter ? "org.bluez.Adapter1" : "org.bluez.Device1";
    assert(dbus_message_iter_open_container(objects, DBUS_TYPE_DICT_ENTRY, NULL, &entry));
    dbus_message_iter_append_basic(&entry, DBUS_TYPE_OBJECT_PATH, &path);
    dbus_message_iter_open_container(&entry, DBUS_TYPE_ARRAY, "{sa{sv}}", &interfaces);
    dbus_message_iter_open_container(&interfaces, DBUS_TYPE_DICT_ENTRY, NULL, &item);
    dbus_message_iter_append_basic(&item, DBUS_TYPE_STRING, &iface);
    dbus_message_iter_open_container(&item, DBUS_TYPE_ARRAY, "{sv}", &properties);
    property(&properties, "Address", DBUS_TYPE_STRING, &address);
    if (adapter) {
        dbus_bool_t on = powered;
        property(&properties, "Powered", DBUS_TYPE_BOOLEAN, &on);
    } else {
        const char *local = "/org/bluez/hci0", *type = "public";
        property(&properties, "Name", DBUS_TYPE_STRING, &name);
        property(&properties, "Adapter", DBUS_TYPE_OBJECT_PATH, &local);
        property(&properties, "AddressType", DBUS_TYPE_STRING, &type);
    }
    dbus_message_iter_close_container(&item, &properties);
    dbus_message_iter_close_container(&interfaces, &item);
    dbus_message_iter_close_container(&entry, &interfaces);
    dbus_message_iter_close_container(objects, &entry);
}
static void setup(int devices, bool powered)
{
    DBusMessageIter root, objects;
    if (fixture) dbus_message_unref(fixture);
    fixture = dbus_message_new(DBUS_MESSAGE_TYPE_METHOD_RETURN);
    dbus_message_iter_init_append(fixture, &root);
    dbus_message_iter_open_container(&root, DBUS_TYPE_ARRAY, "{oa{sa{sv}}}", &objects);
    object(&objects, "/org/bluez/hci0", true, "00:11:22:33:44:55", "", powered);
    if (devices) object(&objects, "/org/bluez/hci0/dev_one", false,
                        "AA:BB:CC:DD:EE:01", "Flydigi Vader 5 Pro", true);
    if (devices > 1) object(&objects, "/org/bluez/hci0/dev_two", false,
                            "AA:BB:CC:DD:EE:02", "Flydigi Vader 5 Pro", true);
    object(&objects, "/org/bluez/hci0/dev_other", false,
           "AA:BB:CC:DD:EE:03", "Other UART Device", true);
    dbus_message_iter_close_container(&root, &objects);
}
int main(void)
{
    SDL_DBusContext context = {0};
#define ITER(name) context.name = dbus_##name
    ITER(message_iter_init); ITER(message_iter_next); ITER(message_iter_get_basic);
    ITER(message_iter_get_arg_type); ITER(message_iter_recurse);
    ITER(message_new_method_call); ITER(message_unref);
#undef ITER
    context.bus_get_private = fake_bus;
    context.connection_close = context.connection_unref = fake_close;
    context.connection_set_exit_on_disconnect = fake_exit;
    context.connection_send_with_reply_and_block = fake_call;
    fp_dbus = &context;
    char device[18], adapter[18];
    setup(0, true); assert(!FP_BlueZAddress(device, adapter));
    setup(1, false); assert(!FP_BlueZAddress(device, adapter));
    setup(1, true); assert(FP_BlueZAddress(device, adapter));
    assert(SDL_strcmp(device, "AA:BB:CC:DD:EE:01") == 0);
    assert(SDL_strcmp(adapter, "00:11:22:33:44:55") == 0);
    setup(2, true); assert(!FP_BlueZAddress(device, adapter));
    SDL_strlcpy(fp.requested_device, "aa:bb:cc:dd:ee:02", 18);
    assert(FP_BlueZAddress(device, adapter));
    SDL_strlcpy(fp.requested_adapter, "00:11:22:33:44:99", 18);
    assert(!FP_BlueZAddress(device, adapter));
    dbus_message_unref(fixture);
    SDL_Log("BlueZ parsing: all scenarios passed");
    return 0;
}

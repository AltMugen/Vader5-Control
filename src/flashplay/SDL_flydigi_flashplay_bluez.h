/* BlueZ device lookup for the Flashplay transport, zlib license.
 * Uses already known devices. Discovery/pairing remains with the desktop.
 */
#include "../../core/linux/SDL_dbus.h"

#ifdef SDL_USE_LIBDBUS
static SDL_DBusContext *fp_dbus;

static bool FP_Property(DBusMessageIter *interfaces, const char *interface_name,
                        const char *property, int type, void *value)
{
    DBusMessageIter entry = *interfaces;
    while (fp_dbus->message_iter_get_arg_type(&entry) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter fields, properties;
        const char *name;
        fp_dbus->message_iter_recurse(&entry, &fields);
        fp_dbus->message_iter_get_basic(&fields, &name);
        fp_dbus->message_iter_next(&fields);
        if (SDL_strcmp(name, interface_name) == 0) {
            fp_dbus->message_iter_recurse(&fields, &properties);
            while (fp_dbus->message_iter_get_arg_type(&properties) == DBUS_TYPE_DICT_ENTRY) {
                DBusMessageIter pair, variant;
                fp_dbus->message_iter_recurse(&properties, &pair);
                fp_dbus->message_iter_get_basic(&pair, &name);
                fp_dbus->message_iter_next(&pair);
                if (SDL_strcmp(name, property) == 0) {
                    fp_dbus->message_iter_recurse(&pair, &variant);
                    if (fp_dbus->message_iter_get_arg_type(&variant) != type) return false;
                    fp_dbus->message_iter_get_basic(&variant, value);
                    return true;
                }
                fp_dbus->message_iter_next(&properties);
            }
        }
        fp_dbus->message_iter_next(&entry);
    }
    return false;
}

static bool FP_BlueZAddress(char device[18], char adapter[18])
{
    DBusConnection *connection;
    DBusMessage *request, *reply;
    DBusMessageIter root, objects;
    int matches = 0;
    if (!fp_dbus) return false;
    connection = fp_dbus->bus_get_private(DBUS_BUS_SYSTEM, NULL);
    if (!connection) return false;
    fp_dbus->connection_set_exit_on_disconnect(connection, false);
    request = fp_dbus->message_new_method_call("org.bluez", "/",
                  "org.freedesktop.DBus.ObjectManager", "GetManagedObjects");
    if (!request) {
        fp_dbus->connection_close(connection);
        fp_dbus->connection_unref(connection);
        return false;
    }
    reply = fp_dbus->connection_send_with_reply_and_block(connection, request, 1000, NULL);
    fp_dbus->message_unref(request);
    if (!reply) goto done;
    if (!fp_dbus->message_iter_init(reply, &root) ||
        fp_dbus->message_iter_get_arg_type(&root) != DBUS_TYPE_ARRAY) goto done;
    fp_dbus->message_iter_recurse(&root, &objects);
    while (fp_dbus->message_iter_get_arg_type(&objects) == DBUS_TYPE_DICT_ENTRY) {
        DBusMessageIter fields, interfaces, adapters;
        const char *name = NULL, *address = NULL, *adapter_path = NULL, *address_type = NULL;
        fp_dbus->message_iter_recurse(&objects, &fields);
        fp_dbus->message_iter_next(&fields);
        fp_dbus->message_iter_recurse(&fields, &interfaces);
        if (!FP_Property(&interfaces, "org.bluez.Device1", "Name", DBUS_TYPE_STRING, &name) ||
            SDL_strcmp(name, "Flydigi Vader 5 Pro") != 0 ||
            !FP_Property(&interfaces, "org.bluez.Device1", "Address", DBUS_TYPE_STRING, &address) ||
            !FP_Property(&interfaces, "org.bluez.Device1", "Adapter", DBUS_TYPE_OBJECT_PATH, &adapter_path) ||
            !FP_Property(&interfaces, "org.bluez.Device1", "AddressType", DBUS_TYPE_STRING, &address_type) ||
            SDL_strcmp(address_type, "public") != 0 ||
            (*fp.requested_device && SDL_strcasecmp(address, fp.requested_device))) goto next;
        fp_dbus->message_iter_recurse(&root, &adapters);
        while (fp_dbus->message_iter_get_arg_type(&adapters) == DBUS_TYPE_DICT_ENTRY) {
            DBusMessageIter adapter_fields, adapter_interfaces;
            const char *path, *local = NULL;
            dbus_bool_t powered = false;
            fp_dbus->message_iter_recurse(&adapters, &adapter_fields);
            fp_dbus->message_iter_get_basic(&adapter_fields, &path);
            fp_dbus->message_iter_next(&adapter_fields);
            fp_dbus->message_iter_recurse(&adapter_fields, &adapter_interfaces);
            if (SDL_strcmp(path, adapter_path) == 0 &&
                FP_Property(&adapter_interfaces, "org.bluez.Adapter1", "Powered", DBUS_TYPE_BOOLEAN, &powered) && powered &&
                FP_Property(&adapter_interfaces, "org.bluez.Adapter1", "Address", DBUS_TYPE_STRING, &local) &&
                (!*fp.requested_adapter || SDL_strcasecmp(local, fp.requested_adapter) == 0)) {
                Uint8 parsed[6];
                if (FP_ParseAddress(address, parsed) && FP_ParseAddress(local, parsed)) {
                    SDL_strlcpy(device, address, 18);
                    SDL_strlcpy(adapter, local, 18);
                    ++matches;
                }
                break;
            }
            fp_dbus->message_iter_next(&adapters);
        }
next:
        fp_dbus->message_iter_next(&objects);
    }
done:
    if (reply) fp_dbus->message_unref(reply);
    fp_dbus->connection_close(connection);
    fp_dbus->connection_unref(connection);
    /* Multiple controllers/adapters need an explicit selection, not first wins. */
    return matches == 1;
}
#endif

static bool FP_ResolveAddress(void)
{
    char device[18] = {0}, adapter[18] = {0};
    if (*fp.requested_device) {
        SDL_strlcpy(device, fp.requested_device, sizeof(device));
        SDL_strlcpy(adapter, fp.requested_adapter, sizeof(adapter));
    } else {
#ifdef SDL_USE_LIBDBUS
        if (!FP_BlueZAddress(device, adapter)) return false;
#else
        return false;
#endif
    }
    if (!FP_ParseAddress(device, fp.remote.address)) return false;
    SDL_memset(fp.local.address, 0, sizeof(fp.local.address));
    if (*adapter && !FP_ParseAddress(adapter, fp.local.address)) return false;
    SDL_LockMutex(fp.mutex);
    SDL_strlcpy(fp.connected_address, device, sizeof(fp.connected_address));
    SDL_UnlockMutex(fp.mutex);
    return true;
}

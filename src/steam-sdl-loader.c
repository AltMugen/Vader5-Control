/* Redirect Steam's SDL loads to the user's driver, including dlmopen namespaces.
 * Stock Steam files remain available to the updater. Never redirect a game's
 * SDL: both the calling module and requested filename must match Steam itself.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <link.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int steam_module(const char *path, const char *root)
{
    size_t n = strlen(root);
    if (strncmp(path, root, n) || path[n] != '/') return 0;
    const char *relative = path + n + 1;
    return !strcmp(relative, "steamrt64/steam") ||
           !strcmp(relative, "steamrt64/steamclient.so") ||
           !strcmp(relative, "ubuntu12_64/steam") ||
           !strcmp(relative, "ubuntu12_64/steamclient.so");
}

static const char *sdl_path(const char *name, void *caller)
{
    const char *root = getenv("VADER5_STEAM_ROOT");
    const char *override = getenv("VADER5_PRIVATE_SDL");
    Dl_info origin;
    if (!name || !root || !override || override[0] != '/' ||
        !dladdr(caller, &origin) || !origin.dli_fname ||
        !steam_module(origin.dli_fname, root)) return name;
    if (strcmp(name, "libSDL3.so.0")) {
        size_t n = strlen(root);
        if (strncmp(name, root, n) || name[n] != '/' ||
            (strcmp(name + n + 1, "steamrt64/libSDL3.so.0") &&
             strcmp(name + n + 1, "ubuntu12_64/libSDL3.so.0"))) return name;
    }
    return access(override, R_OK) == 0 ? override : name;
}

void *dlopen(const char *name, int flags)
{
    void *(*next)(const char *, int) = dlsym(RTLD_NEXT, "dlopen");
    return next(sdl_path(name, __builtin_return_address(0)), flags);
}

void *dlmopen(Lmid_t namespace, const char *name, int flags)
{
    void *(*next)(Lmid_t, const char *, int) = dlsym(RTLD_NEXT, "dlmopen");
    return next(namespace, sdl_path(name, __builtin_return_address(0)), flags);
}

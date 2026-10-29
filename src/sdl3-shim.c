/* Steam's UI expects this symbol from Valve's SDL build. */
extern void SDL_LockJoysticks(void);

int SDL_TryLockJoysticks(void)
{
    SDL_LockJoysticks();
    return 1;
}

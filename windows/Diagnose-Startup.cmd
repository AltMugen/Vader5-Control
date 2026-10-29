@echo off
setlocal
set "VADER5_STARTUP_TRACE=1"
set "VADER5_DIAGNOSTICS=1"
set "STARTUP_LOG=%TEMP%\Vader5Control-Startup.log"
echo Launch started %DATE% %TIME% > "%STARTUP_LOG%"
echo Close Vader5 Control to finish the startup log.
call "%~dp0Launch.cmd" >> "%STARTUP_LOG%" 2>&1
type "%STARTUP_LOG%"
echo Log: %STARTUP_LOG%
pause

@echo off
setlocal
set "PATH=%~dp0ucrt64\bin;%PATH%"
set "PYTHONHOME=%~dp0ucrt64"
set "PYTHONUTF8=1"
set "GI_TYPELIB_PATH=%~dp0ucrt64\lib\girepository-1.0"
set "XDG_DATA_DIRS=%~dp0ucrt64\share"
set "GSETTINGS_SCHEMA_DIR=%~dp0ucrt64\share\glib-2.0\schemas"
set "FONTCONFIG_PATH=%~dp0ucrt64\etc\fonts"
set "GSETTINGS_BACKEND=keyfile"
set "GSK_RENDERER=cairo"
set "GDK_BACKEND=win32"
"%~dp0ucrt64\bin\python.exe" "%~dp0app\app.py"
if errorlevel 1 if not defined VADER5_DIAGNOSTICS pause

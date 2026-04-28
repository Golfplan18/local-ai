@echo off
REM Local AI - Stop Script (Windows)
REM Mirror of stop.sh for Windows users.

setlocal enabledelayedexpansion

set "FOUND="
for /f "tokens=2" %%a in ('tasklist /v /fo csv ^| findstr /i "server.py"') do (
    taskkill /pid %%~a /f >nul 2>&1
    set "FOUND=1"
)

if defined FOUND (
    echo Server stopped.
) else (
    echo Server was not running.
)
endlocal
exit /b 0

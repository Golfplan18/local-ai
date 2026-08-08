@echo off
REM Local AI - Start Script (Windows)
REM Mirror of start.sh for Windows users.

setlocal enabledelayedexpansion

REM Honor a relocated/worktree checkout. Otherwise launch the checkout that owns
REM this script, not whichever repository happens to live at %%USERPROFILE%%\ora.
if defined ORA_HOME (
    set "WORKSPACE=!ORA_HOME!"
) else (
    set "WORKSPACE=%~dp0"
)
for %%I in ("!WORKSPACE!") do set "WORKSPACE=%%~fI"
set "ORA_HOME=!WORKSPACE!"

REM Find Python: prefer this checkout's .venv — scripts\install.py creates one
REM when the host interpreter is PEP 668 externally managed, and it owns the
REM dependencies. Mirrors run-ora-server.sh on POSIX. Then the 'py' launcher
REM (Windows-standard), then 'python'.
if exist "!WORKSPACE!\.venv\Scripts\python.exe" (
    set PYTHON="!WORKSPACE!\.venv\Scripts\python.exe"
    goto :have_python
)
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=py -3"
    goto :have_python
)
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON=python"
    goto :have_python
)
echo ERROR: Python not found. Install Python 3.10+ from python.org and ensure 'py' or 'python' is on PATH.
exit /b 1

:have_python

REM PORT is exact intent when explicitly set. Validate before backgrounding so
REM an invalid value fails immediately rather than becoming a 30-second timeout.
if defined PORT (
    %PYTHON% -c "import os; p=os.environ.get('PORT',''); raise SystemExit(0 if p.isascii() and p.isdecimal() and str(int(p)) == p and 1 <= int(p) <= 65535 else 2)"
    if !errorlevel! neq 0 (
        echo ERROR: PORT must be a canonical integer from 1 to 65535; got "!PORT!".
        exit /b 2
    )
    REM Preflight the common collision case so the wrapper fails immediately.
    REM server.py repeats the probe; Flask's actual bind is the final loud guard.
    %PYTHON% -c "import os,socket; s=socket.socket(); s.bind(('localhost',int(os.environ['PORT']))); s.close()" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: PORT=!PORT! is unavailable on localhost; refusing to start on another port.
        exit /b 2
    )
)

REM Kill any stale server process only after the explicit-port contract passes.
REM Best-effort: ignore errors if nothing matches.
for /f "tokens=2" %%a in ('tasklist /v /fo csv ^| findstr /i "server.py"') do (
    taskkill /pid %%~a /f >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Execution Review loop + tiered persistence (mirrors start.sh).
set "ORA_EXECUTION_LOOP=1"

REM Start server in background.
start "Ora Server" /B %PYTHON% "%WORKSPACE%\server\server.py" %*

REM Wait up to 30s. An explicit PORT is exact; otherwise scan 5000-5010.
set "FOUND_PORT="
for /l %%i in (1,1,30) do (
    if defined PORT (
        if not defined FOUND_PORT (
            set "ORA_HEALTH_PORT=!PORT!"
            call :check_health_identity
            if !errorlevel!==0 (
                set "FOUND_PORT=!PORT!"
            )
        )
    ) else (
        for /l %%p in (5000,1,5010) do (
            if not defined FOUND_PORT (
                set "ORA_HEALTH_PORT=%%p"
                call :check_health_identity
                if !errorlevel!==0 (
                    set "FOUND_PORT=%%p"
                )
            )
        )
    )
    if defined FOUND_PORT goto :found
    timeout /t 1 /nobreak >nul
)

echo ERROR: Server did not start. Run: %PYTHON% "%WORKSPACE%\server\server.py"
exit /b 1

:found
echo Local AI ready at http://localhost:%FOUND_PORT%
start "" "http://localhost:%FOUND_PORT%"
endlocal
exit /b 0

:check_health_identity
REM ORA_HEALTH_IDENTITY_CHECK — accept only this checkout's Ora process.
%PYTHON% -c "import json,os,urllib.request; expected=os.path.normcase(os.path.realpath(os.environ['ORA_HOME'])); data=json.load(urllib.request.urlopen('http://localhost:'+os.environ['ORA_HEALTH_PORT']+'/health',timeout=2)); value=data.get('ora_home',''); actual=os.path.normcase(os.path.realpath(value)) if value else ''; raise SystemExit(0 if actual and actual == expected else 1)" >nul 2>&1
exit /b !errorlevel!

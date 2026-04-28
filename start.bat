@echo off
REM Local AI - Start Script (Windows)
REM Mirror of start.sh for Windows users.

setlocal enabledelayedexpansion

set "WORKSPACE=%USERPROFILE%\ora"

REM Kill any stale server process. Best-effort: ignore errors if nothing matches.
for /f "tokens=2" %%a in ('tasklist /v /fo csv ^| findstr /i "server.py"') do (
    taskkill /pid %%~a /f >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Find Python: prefer 'py' launcher (Windows-standard), then 'python'.
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

REM Start server in background.
start "Ora Server" /B %PYTHON% "%WORKSPACE%\server\server.py" %*

REM Wait up to 30s for server on any port 5000-5010.
set "FOUND_PORT="
for /l %%i in (1,1,30) do (
    for /l %%p in (5000,1,5010) do (
        if not defined FOUND_PORT (
            curl -sf "http://localhost:%%p/health" >nul 2>&1
            if !errorlevel!==0 (
                set "FOUND_PORT=%%p"
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

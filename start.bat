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

REM ---- shared: ora-process-identity ----
REM start.bat and stop.bat must agree on which process belongs to this checkout,
REM so this block is byte-identical in both files (asserted by
REM orchestrator/tests/test_server_launchers.py).
REM
REM Identity is the PID start.bat recorded when it launched the server, held in
REM a launcher-owned file beside this script. Before any kill, the recorded PID
REM is re-checked against the live command line, so a PID the operating system
REM has since recycled onto an unrelated program cannot be terminated by
REM mistake. This mirrors start.sh/stop.sh, which accept only a Python
REM interpreter whose next argument is this checkout's exact server file.
REM A window title is not identity: it matches any window a user happens to
REM have named the same thing, and misses the server whenever the title differs.
for %%I in ("!WORKSPACE!\server\app.py") do set "ORA_SERVER_TARGET=%%~fI"
for %%I in ("!WORKSPACE!\.ora-server.pid") do set "ORA_SERVER_PID_FILE=%%~fI"
REM ---- end shared: ora-process-identity ----

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
REM The floor below is scripts/install.py's PREFLIGHT_MIN_PYTHON. Keep the two
REM in step; the test suite asserts they agree.
echo ERROR: Python not found. Install Python 3.11+ from python.org and ensure 'py' or 'python' is on PATH.
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
    REM The server repeats the probe; Flask's actual bind is the final loud guard.
    %PYTHON% -c "import os,socket; s=socket.socket(); s.bind(('localhost',int(os.environ['PORT']))); s.close()" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: PORT=!PORT! is unavailable on localhost; refusing to start on another port.
        exit /b 2
    )
)

REM Stop a server this checkout started earlier, only after the explicit-port
REM contract passes. Best-effort: nothing to stop is not an error here.
call :stop_owned_server >nul 2>&1
timeout /t 1 /nobreak >nul

REM Execution Review loop + tiered persistence (mirrors start.sh).
set "ORA_EXECUTION_LOOP=1"

REM Start server in background with oversight enabled by default; the explicit
REM --no-oversight diagnostic opt-out is consumed here, exactly as on POSIX.
REM Record the PID this launcher owns. Python
REM performs the spawn because cmd's 'start' reports no PID back to the script,
REM and the window title 'start' would set is not a usable identity for
REM stop.bat. CREATE_NEW_PROCESS_GROUP reproduces 'start /B': the server keeps
REM this console for its output and ignores the console's Ctrl+C.
setlocal DisableDelayedExpansion
%PYTHON% -c "import os,pathlib,subprocess,sys; enable_oversight='--no-oversight' not in sys.argv[1:]; args=[arg for arg in sys.argv[1:] if arg != '--no-oversight']; server_args=(['--oversight'] if enable_oversight else []) + args; child=subprocess.Popen([sys.executable, os.environ['ORA_SERVER_TARGET']] + server_args, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP); pathlib.Path(os.environ['ORA_SERVER_PID_FILE']).write_text(str(child.pid), encoding='ascii')" %*
endlocal

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

echo ERROR: Server did not start. Run: %PYTHON% "!ORA_SERVER_TARGET!"
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

:stop_owned_server
REM ---- shared: ora-stop-owned-server ----
REM Byte-identical in start.bat and stop.bat (asserted by the test suite).
REM Exit codes: 0 stopped a server this checkout owns, 3 there was nothing of
REM ours to stop, 2 found ours but could not stop it, 4 the query itself failed.
REM Anything else means powershell.exe never ran (cmd reports 9009 when it is
REM missing), which is not the same fact as an idle machine and must not be
REM reported as one.
REM
REM When the PID file exists only that PID is eligible; without one, fall back to
REM a command-line query. Either way the match is positional, exactly as the awk
REM in stop.sh is: the text immediately BEFORE this checkout's server path must be
REM a Python interpreter plus optional -flags and nothing else, and the character
REM immediately after it must end the argument. A path that merely appears
REM somewhere in the command line is not a match, so a py_compile run, a pytest
REM run, or a formatter handed the server file as an argument all survive, and so
REM do an editor holding the file open, a recycled PID, and a similarly-named backup.
powershell -NoProfile -Command "$q = [string][char]34; $ord = [System.StringComparison]::Ordinal; $code = 3; try { $target = $env:ORA_SERVER_TARGET; $file = $env:ORA_SERVER_PID_FILE; $target = $target.ToLower(); $owned = -1; $parsed = 0; if (Test-Path -LiteralPath $file) { $raw = Get-Content -LiteralPath $file -TotalCount 1; if ($raw -and [int]::TryParse($raw.Trim(), [ref]$parsed) -and $parsed -gt 0) { $owned = $parsed } }; $stopped = 0; $failed = 0; foreach ($proc in Get-CimInstance Win32_Process) { if ($owned -ge 0 -and $proc.ProcessId -ne $owned) { continue }; $name = $proc.Name; if (-not $name -or -not $name.ToLower().StartsWith('python')) { continue }; $cl = $proc.CommandLine; if (-not $cl) { continue }; $cl = $cl.ToLower(); $pos = $cl.IndexOf($target, $ord); if ($pos -lt 0) { continue }; $before = $cl.Substring(0, $pos); $after = $cl.Substring($pos + $target.Length); if ($before.EndsWith($q, $ord) -ne $after.StartsWith($q, $ord)) { continue }; if ($after.StartsWith($q, $ord)) { $before = $before.Substring(0, $before.Length - 1); $after = $after.Substring(1) }; if ($after.Length -gt 0 -and -not $after.StartsWith(' ', $ord)) { continue }; $parts = $before.Replace($q, '').TrimEnd().Split([char[]]('\', '/')); $exe = $parts[$parts.Length - 1]; if ($exe -notmatch '^python([0-9]+([.][0-9]+)*)?([.]exe)?(\s+-\S+)*$') { continue }; try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; $stopped = $stopped + 1 } catch { $failed = $failed + 1 } }; if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }; if ($stopped -gt 0) { $code = 0 } elseif ($failed -gt 0) { $code = 2 } } catch { $code = 4 }; exit $code"
exit /b !errorlevel!
REM ---- end shared: ora-stop-owned-server ----

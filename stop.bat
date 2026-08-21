@echo off
REM Local AI - Stop Script (Windows)
REM Mirror of stop.sh for Windows users.

setlocal enabledelayedexpansion

REM Honor a relocated/worktree checkout, exactly as start.bat does, so this
REM script stops the server belonging to the checkout that owns it and never
REM a server another checkout started.
if defined ORA_HOME (
    set "WORKSPACE=!ORA_HOME!"
) else (
    set "WORKSPACE=%~dp0"
)
for %%I in ("!WORKSPACE!") do set "WORKSPACE=%%~fI"

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

REM Report what actually happened. A stop that could not run, and a server
REM that would not die, are both failures and neither is 'nothing was running'.
call :stop_owned_server
set "STOP_RC=!errorlevel!"
if "!STOP_RC!"=="0" (
    echo Server stopped.
) else if "!STOP_RC!"=="3" (
    echo Server was not running.
) else if "!STOP_RC!"=="2" (
    echo ERROR: Ora server is running but could not be stopped. It may be running
    echo elevated; retry stop.bat from an administrator prompt.
    endlocal
    exit /b 1
) else if "!STOP_RC!"=="4" (
    echo ERROR: Could not query running processes, so nothing was stopped.
    echo The Ora server may still be running.
    endlocal
    exit /b 1
) else (
    echo ERROR: Could not run powershell.exe, so nothing was stopped.
    echo The Ora server may still be running.
    endlocal
    exit /b 1
)
endlocal
exit /b 0

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

#!/usr/bin/env python3
"""
Session Refresh Script
Extracts cookies from Chrome and/or Firefox into Playwright session files.
Called automatically by LaunchAgents (macOS), systemd (Linux), or scheduled
tasks (Windows) when either browser quits.
Only extracts from a browser that is NOT currently running.

Cross-platform: macOS, Linux, and Windows browser profile paths are detected
based on sys.platform. Notification mechanism falls back to console output
when the platform-native channel is not available.
"""

import sqlite3, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

SESSION_DIR = Path.home() / "ora/config/browser-sessions"
LOG_FILE    = Path.home() / "ora/config/session-refresh.log"


def _browser_paths():
    """Return (chrome_cookies, chrome_lock, firefox_cookies, firefox_lock) for the current platform."""
    home = Path.home()
    platform = sys.platform

    if platform == "darwin":
        chrome_base = home / "Library/Application Support/Google/Chrome/Default"
        firefox_root = home / "Library/Application Support/Firefox/Profiles"
        # Match the existing Mac behavior: target the nightly profile if it exists,
        # otherwise fall back to the first .default* profile found.
        firefox_profile = firefox_root / "nx5dsqdk.default-nightly"
        if not firefox_profile.exists() and firefox_root.exists():
            for p in firefox_root.iterdir():
                if p.is_dir() and ".default" in p.name:
                    firefox_profile = p
                    break
    elif platform.startswith("linux"):
        chrome_base = home / ".config/google-chrome/Default"
        firefox_root = home / ".mozilla/firefox"
        firefox_profile = None
        if firefox_root.exists():
            for p in firefox_root.iterdir():
                if p.is_dir() and ".default" in p.name:
                    firefox_profile = p
                    break
        if firefox_profile is None:
            firefox_profile = firefox_root / "default"
    elif platform == "win32":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData/Roaming")))
        local_appdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local")))
        chrome_base = local_appdata / "Google/Chrome/User Data/Default"
        firefox_root = appdata / "Mozilla/Firefox/Profiles"
        firefox_profile = None
        if firefox_root.exists():
            for p in firefox_root.iterdir():
                if p.is_dir() and ".default" in p.name:
                    firefox_profile = p
                    break
        if firefox_profile is None:
            firefox_profile = firefox_root / "default"
    else:
        chrome_base = home / ".config/google-chrome/Default"
        firefox_profile = home / ".mozilla/firefox/default"

    # On Windows, Chrome stores cookies under Network/ subfolder (since Chrome 96+)
    chrome_cookies_candidates = [chrome_base / "Network/Cookies", chrome_base / "Cookies"]
    chrome_cookies = next((p for p in chrome_cookies_candidates if p.exists()),
                          chrome_cookies_candidates[-1])
    chrome_lock = chrome_base / "SingletonLock"
    firefox_cookies = firefox_profile / "cookies.sqlite"
    firefox_lock = firefox_profile / "lock"

    return chrome_cookies, chrome_lock, firefox_cookies, firefox_lock


CHROME_COOKIES, CHROME_LOCK, FIREFOX_COOKIES, FIREFOX_LOCK = _browser_paths()

TARGETS = {
    "claude":  {"chrome": [".claude.ai","claude.ai",".anthropic.com","anthropic.com"],
                "firefox": [".claude.ai","claude.ai",".anthropic.com","anthropic.com"]},
    "chatgpt": {"chrome": [".openai.com","openai.com","chat.openai.com",".chatgpt.com","chatgpt.com"],
                "firefox": [".openai.com","openai.com","chat.openai.com"]},
    "gemini":  {"chrome": [".google.com","google.com","gemini.google.com"],
                "firefox": [".google.com","google.com","gemini.google.com"]},
}


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def is_running(app_name):
    """Cross-platform process check. app_name is the executable basename (Chrome, firefox, etc.)."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {app_name}"],
                capture_output=True, text=True
            )
            return app_name.lower() in result.stdout.lower()
        except (FileNotFoundError, subprocess.SubprocessError):
            return False
    else:
        try:
            result = subprocess.run(["pgrep", "-x", app_name], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False


def notify(title, msg):
    """Send a desktop notification, or fall back to console output."""
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{msg}" with title "{title}"'],
                capture_output=True
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(
                ["notify-send", title, msg],
                capture_output=True
            )
        elif sys.platform == "win32":
            ps_msg = msg.replace("'", "''")
            ps_title = title.replace("'", "''")
            subprocess.run([
                "powershell", "-NoProfile", "-Command",
                f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                f"[reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null; "
                f"$n = New-Object System.Windows.Forms.NotifyIcon; "
                f"$n.Icon = [System.Drawing.SystemIcons]::Information; "
                f"$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, '{ps_title}', '{ps_msg}', "
                f"[System.Windows.Forms.ToolTipIcon]::Info)"
            ], capture_output=True)
        else:
            print(f"[notify] {title}: {msg}")
    except (FileNotFoundError, subprocess.SubprocessError):
        print(f"[notify] {title}: {msg}")


def _chrome_process_name():
    if sys.platform == "darwin":
        return "Google Chrome"
    if sys.platform == "win32":
        return "chrome.exe"
    return "chrome"


def _firefox_process_name():
    if sys.platform == "win32":
        return "firefox.exe"
    return "firefox"


def extract_chrome():
    if not CHROME_COOKIES.exists():
        log("Chrome cookies file not found — skipping Chrome")
        return 0
    if CHROME_LOCK.exists() or is_running(_chrome_process_name()):
        log("Chrome is still running — skipping Chrome extraction")
        return 0

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        tmp = tf.name
    try:
        shutil.copy2(CHROME_COOKIES, tmp)
        conn = sqlite3.connect(tmp)
        cur  = conn.cursor()
        saved = 0

        for service, domains_map in TARGETS.items():
            domains = domains_map["chrome"]
            ph = ",".join("?" for _ in domains)
            cur.execute(f"SELECT host_key,name,value,path,expires_utc,is_secure,is_httponly,samesite FROM cookies WHERE host_key IN ({ph})", domains)
            rows = cur.fetchall()
            if not rows:
                continue
            same_map = {-1:"None", 0:"None", 1:"Lax", 2:"Strict"}
            cookies = [{"name":n,"value":v,"domain":h,"path":p,
                        "expires":(e/1000000-11644473600) if e>0 else -1,
                        "httpOnly":bool(ho),"secure":bool(s),
                        "sameSite":same_map.get(sm,"Lax")}
                       for h,n,v,p,e,s,ho,sm in rows]
            out = SESSION_DIR / f"{service}.json"
            with open(out,"w") as f:
                json.dump({"cookies":cookies,"origins":[]}, f, indent=2)
            log(f"  Chrome → {service}: {len(cookies)} cookies")
            saved += len(cookies)

        conn.close()
        return saved
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def extract_firefox():
    if not FIREFOX_COOKIES.exists():
        log("Firefox cookies file not found — skipping Firefox")
        return 0
    if FIREFOX_LOCK.exists() or is_running(_firefox_process_name()):
        log("Firefox is still running — skipping Firefox extraction")
        return 0

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        tmp = tf.name
    try:
        shutil.copy2(FIREFOX_COOKIES, tmp)
        conn = sqlite3.connect(tmp)
        cur  = conn.cursor()
        saved = 0

        for service, domains_map in TARGETS.items():
            domains = domains_map["firefox"]
            # Firefox host column uses leading dot for domain cookies
            # Match both .domain.com and domain.com
            like_clauses = " OR ".join("host LIKE ?" for _ in domains)
            cur.execute(
                f"SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite "
                f"FROM moz_cookies WHERE {like_clauses}",
                [f"%{d.lstrip('.')}" for d in domains]
            )
            rows = cur.fetchall()
            if not rows:
                continue

            # Merge with existing session file (keep Chrome cookies, overlay Firefox ones)
            out_path = SESSION_DIR / f"{service}.json"
            existing = {}
            if out_path.exists():
                try:
                    data = json.loads(out_path.read_text())
                    existing = {c["name"]: c for c in data.get("cookies",[])}
                except Exception:
                    pass

            same_map = {0:"None", 1:"Lax", 2:"Strict"}
            for h,n,v,p,exp,sec,ho,sm in rows:
                existing[n] = {"name":n,"value":v,"domain":h,"path":p,
                               "expires":float(exp) if exp else -1,
                               "httpOnly":bool(ho),"secure":bool(sec),
                               "sameSite":same_map.get(sm,"Lax")}

            cookies = list(existing.values())
            with open(out_path,"w") as f:
                json.dump({"cookies":cookies,"origins":[]}, f, indent=2)
            log(f"  Firefox → {service}: {len(rows)} cookies merged ({len(cookies)} total)")
            saved += len(rows)

        conn.close()
        return saved
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "auto"
    log(f"Session refresh triggered (source: {source}, platform: {sys.platform})")

    chrome_saved  = extract_chrome()
    firefox_saved = extract_firefox()
    total = chrome_saved + firefox_saved

    if total > 0:
        log(f"Refresh complete: {total} cookies updated")
        notify("Local AI", f"Sessions refreshed ({total} cookies)")
    else:
        log("No browsers were available for extraction (all running or not found)")

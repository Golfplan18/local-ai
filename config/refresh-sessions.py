#!/usr/bin/env python3
"""
Session Refresh Script
Extracts cookies from Chrome and/or Firefox Nightly into Playwright session files.
Called automatically by LaunchAgents when either browser quits.
Only extracts from a browser that is NOT currently running.
"""

import sqlite3, json, os, shutil, subprocess, sys, time
from pathlib import Path

SESSION_DIR = Path.home() / "local-ai/config/browser-sessions"
LOG_FILE    = Path.home() / "local-ai/config/session-refresh.log"

CHROME_COOKIES  = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
CHROME_LOCK     = Path.home() / "Library/Application Support/Google/Chrome/Default/SingletonLock"
FIREFOX_COOKIES = Path.home() / "Library/Application Support/Firefox/Profiles/nx5dsqdk.default-nightly/cookies.sqlite"
FIREFOX_LOCK    = Path.home() / "Library/Application Support/Firefox/Profiles/nx5dsqdk.default-nightly/lock"

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
    result = subprocess.run(["pgrep", "-x", app_name], capture_output=True)
    return result.returncode == 0

def notify(title, msg):
    subprocess.run(["osascript", "-e",
        f'display notification "{msg}" with title "{title}"'],
        capture_output=True)

def extract_chrome():
    if not CHROME_COOKIES.exists():
        log("Chrome cookies file not found — skipping Chrome")
        return 0
    if CHROME_LOCK.exists() or is_running("Google Chrome"):
        log("Chrome is still running — skipping Chrome extraction")
        return 0

    tmp = "/tmp/chrome_cookies_refresh.sqlite"
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
    os.remove(tmp)
    return saved

def extract_firefox():
    if not FIREFOX_COOKIES.exists():
        log("Firefox Nightly cookies file not found — skipping Firefox")
        return 0
    if FIREFOX_LOCK.exists() or is_running("firefox"):
        log("Firefox is still running — skipping Firefox extraction")
        return 0

    tmp = "/tmp/firefox_cookies_refresh.sqlite"
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
    os.remove(tmp)
    return saved

if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "auto"
    log(f"Session refresh triggered (source: {source})")

    chrome_saved  = extract_chrome()
    firefox_saved = extract_firefox()
    total = chrome_saved + firefox_saved

    if total > 0:
        log(f"Refresh complete: {total} cookies updated")
        notify("Local AI", f"Sessions refreshed ({total} cookies)")
    else:
        log("No browsers were available for extraction (all running or not found)")

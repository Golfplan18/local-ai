#!/usr/bin/env python3
"""Double-fork daemonizer. macOS has no setsid(1), and plain nohup was not enough:
four backgrounded shards were killed when the launching tool call returned. This
detaches fully — new session, no controlling terminal, cwd at / — so the child
outlives the session that started it.

    daemonize.py <logfile> <cmd> [args...]
"""
import os, sys

if len(sys.argv) < 3:
    sys.exit("usage: daemonize.py <logfile> <cmd> [args...]")
log, cmd = sys.argv[1], sys.argv[2:]
if os.fork() > 0:
    os._exit(0)                 # parent returns immediately
os.setsid()                     # new session, detached from the terminal
if os.fork() > 0:
    os._exit(0)                 # cannot reacquire a controlling terminal
os.chdir("/")
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(fd, 1); os.dup2(fd, 2)
os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
os.execvp(cmd[0], cmd)

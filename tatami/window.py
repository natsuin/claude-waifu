#!/usr/bin/env python3
"""Bring up an agent's own window: what clicking its mat on the desk does (through open.vbs).

It works for any window, however it was opened. WSL starts a Windows program through the
session it's started from, so this runs a small PowerShell script (focus-window.ps1, next to
waifu's launchers) through the agent's own session: the script's parent is then the wsl.exe
the agent runs under, and that wsl.exe's console belongs to the agent's window.

  tatami window <agent id>    exit 0: in front. 1: shown, but Windows kept the focus where it
                              was. 2: no window to bring up.
"""
import os
import re
import subprocess
import sys

import tatami_mcp as channel  # same folder: shares the file layout and helpers

WAIFU_CONFIG = os.path.expanduser("~/.config/waifu/config.json")


def session_of(pid):
    """The WSL session an agent runs in: the interop socket its processes use for Windows."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = dict(v.split(b"=", 1) for v in f.read().split(b"\0") if b"=" in v)
    except OSError:
        return None
    return env.get(b"WSL_INTEROP", b"").decode() or None


def win_path(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()


def main():
    aid = sys.argv[1] if len(sys.argv) > 1 else ""
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,60}", aid):
        return 2
    rec = channel.load(os.path.join(channel.AGENTS, aid + ".json"), {})
    launcher = channel.load(WAIFU_CONFIG, {}).get("launcher_dir")
    session = channel.alive(rec) and session_of(rec["pid"])
    if not session or not launcher:
        return 2
    script = os.path.join(launcher, "focus-window.ps1")
    if not os.path.isfile(script):
        return 2
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", win_path(script), win_path(os.path.join(launcher, "window-title.txt"))],
                              env=dict(os.environ, WSL_INTEROP=session), cwd="/mnt/c", stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return 2
    return done.returncode if done.returncode in (0, 1) else 2


if __name__ == "__main__":
    sys.exit(main())

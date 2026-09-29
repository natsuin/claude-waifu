#!/usr/bin/env python3
"""A terminal for the Tatami Room app. It runs Claude in a pseudo-terminal inside WSL, the way
a Claude Waifu window does, and relays it over plain pipes: the app starts it through wsl.exe
and draws it with xterm.js, so nothing needs native modules on the Windows side.

  tatami term <session>    what the app runs; <session> ties the agent on the desk to it

The app resizes the terminal in-band: ESC ] 7373 ; resize ; <cols> ; <rows> BEL. Before it
starts, waifu picks a girl and a color for it, like it does for each new window.
"""
import fcntl
import json
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios

RESIZE = re.compile(rb"\x1b\]7373;resize;(\d{1,4});(\d{1,4})\x07")
WAIFU = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "waifu")


def set_size(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def look():
    """A girl and a color for this terminal, dealt by waifu like a new window's."""
    try:
        out = subprocess.run([WAIFU, "pick"], capture_output=True, text=True, timeout=60).stdout
        pick = json.loads(out.strip().splitlines()[-1])
        return str(pick.get("color") or ""), str(pick.get("girl") or "")
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return "", ""


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else ""
    if not re.fullmatch(r"[a-z0-9-]{1,40}", session):
        sys.exit("usage: tatami term <session>")
    color, girl = look()
    pid, fd = pty.fork()
    if pid == 0:  # the terminal's side: Claude, then a shell once it exits, like a Claude Waifu window
        os.environ.update(TERM="xterm-256color", COLORTERM="truecolor", TATAMI_SESSION=session,
                          TATAMI_COLOR=color, TATAMI_GIRL=girl)
        os.chdir(os.path.expanduser("~"))
        os.execvp("bash", ["bash", "-lic", "claude; exec bash"])
    set_size(fd, 100, 30)
    try:
        while True:
            ready, _, _ = select.select([0, fd], [], [])
            if 0 in ready:
                data = os.read(0, 65536)
                if not data:  # the app closed the session
                    break
                for cols, rows in RESIZE.findall(data):
                    set_size(fd, max(2, int(cols)), max(2, int(rows)))
                data = RESIZE.sub(b"", data)
                if data:
                    os.write(fd, data)
            if fd in ready:
                try:
                    out = os.read(fd, 65536)
                except OSError:  # the shell exited
                    break
                if not out:
                    break
                os.write(1, out)
    finally:
        try:
            os.kill(pid, 1)  # hang up, as closing a window would
        except OSError:
            pass


if __name__ == "__main__":
    main()

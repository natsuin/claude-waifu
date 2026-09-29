#!/usr/bin/env python3
"""A terminal for the Tatami Room app. It runs Claude in a pseudo-terminal inside WSL, the way
a Claude Waifu window does, and relays it over plain pipes: the app starts it through wsl.exe
and draws it with xterm.js, so nothing needs native modules on the Windows side.

Claude starts in ~/desk, a folder of its own: Claude Code asks once whether you trust a folder,
and remembers the answer for that folder, where your home folder would ask every time.

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

import tatami_mcp  # same folder: where the desk folder is

RESIZE = re.compile(rb"\x1b\]7373;resize;(\d{1,4});(\d{1,4})\x07")
WAIFU = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "waifu")


def set_size(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def look():
    """A girl and a color for this terminal, dealt by waifu like a new window's."""
    try:
        # A few seconds at most: waifu can be busy downloading, and Claude shouldn't wait for a girl.
        out = subprocess.run([WAIFU, "pick"], capture_output=True, text=True, timeout=6).stdout
        pick = json.loads(out.strip().splitlines()[-1])
        return str(pick.get("color") or ""), str(pick.get("girl") or "")
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return "", ""


DESK_NOTE = """# The Tatami Room desk

Claude sessions started from the Tatami Room app begin in this folder. It's only a starting
point: the user's projects live in their home folder (~), so work wherever they ask.
"""


def desk():
    """The app's terminals start here; made the first time, with a note for Claude."""
    folder = tatami_mcp.DESK_DIR
    if not os.path.isdir(folder):
        os.makedirs(folder)
        with open(os.path.join(folder, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write(DESK_NOTE)
    return folder


def main():
    session = sys.argv[1] if len(sys.argv) > 1 else ""
    if not re.fullmatch(r"[a-z0-9-]{1,40}", session):
        sys.exit("usage: tatami term <session>")
    os.write(1, b"\x1b[2mStarting Claude\xe2\x80\xa6\x1b[0m")  # something to see straight away
    color, girl = look()
    start = desk()
    pid, fd = pty.fork()
    if pid == 0:  # the terminal's side: Claude, then a shell once it exits, like a Claude Waifu window
        os.environ.update(TERM="xterm-256color", COLORTERM="truecolor", TATAMI_SESSION=session,
                          TATAMI_COLOR=color, TATAMI_GIRL=girl)
        os.chdir(start)
        os.execvp("bash", ["bash", "-lic", "claude; exec bash"])
    set_size(fd, 100, 30)
    os.write(1, b"\r\x1b[2K")  # Claude draws from here
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

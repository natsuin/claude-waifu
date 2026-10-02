#!/usr/bin/env python3
"""Claude Code status line: subscription usage (the rolling 5-hour window and the weekly
one, each with a bar and its reset time) plus how full this session's context is.
Claude Code pipes session JSON in on stdin; see https://code.claude.com/docs/en/statusline
If you use Tatami Room's desk, it also leaves the usage numbers where the board can show them."""
import json
import os
import sys
import time

# The desk's usage colours: dusk blue while there's plenty left, persimmon past half, crimson
# past four fifths.
SKY, AMBER, CORAL = "\x1b[38;2;142;203;255m", "\x1b[38;2;255;195;138m", "\x1b[38;2;255;107;139m"
DIM, RESET = "\x1b[38;2;168;143;174m", "\x1b[0m"


def colour(pct):
    return SKY if pct < 50 else AMBER if pct < 80 else CORAL


def bar(pct, width=10):
    filled = min(width, round(pct / 100 * width))
    return colour(pct) + "█" * filled + DIM + "░" * (width - filled) + RESET


def reset_time(epoch, weekly):
    """'4:10pm' for today, 'Thu 9:00am' for another day of the week."""
    t = time.localtime(epoch)
    clock = time.strftime("%-I:%M%p", t).lower()
    same_day = time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d")
    return clock if same_day or not weekly else time.strftime("%a ", t) + clock


def share(limits):
    """Tatami Room's board shows your usage too: keep the latest numbers where it reads them."""
    desk = os.path.expanduser("~/.local/state/tatami")
    path = os.path.join(desk, "usage.json")
    if not limits or not os.path.isdir(desk):
        return
    try:
        with open(path, encoding="utf-8") as f:
            if json.load(f).get("rate_limits") == limits:
                return
    except (OSError, ValueError):
        pass
    try:
        with open(f"{path}.{os.getpid()}", "w", encoding="utf-8") as f:
            json.dump({"rate_limits": limits, "ts": time.time()}, f)
        os.replace(f"{path}.{os.getpid()}", path)
    except OSError:
        pass


data = json.load(sys.stdin)
parts = []
limits = data.get("rate_limits") or {}
share(limits)
for key, label, weekly in (("five_hour", "5h", False), ("seven_day", "week", True)):
    window = limits.get(key) or {}
    pct = window.get("used_percentage")
    if pct is None:
        continue
    resets = f" {DIM}resets {reset_time(window['resets_at'], weekly)}{RESET}" if window.get("resets_at") else ""
    parts.append(f"{label} {bar(pct)} {colour(pct)}{pct:.0f}%{RESET}{resets}")
if not parts:  # only sent for Pro/Max plans, and only after the session's first reply
    parts.append(f"{DIM}usage shows after Claude's first reply{RESET}")
ctx = (data.get("context_window") or {}).get("used_percentage")
if ctx is not None:
    parts.append(f"context {colour(ctx)}{ctx:.0f}%{RESET}")
print("   ".join(parts))

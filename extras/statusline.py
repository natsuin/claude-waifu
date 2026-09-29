#!/usr/bin/env python3
"""Claude Code status line: subscription usage (the rolling 5-hour window and the weekly
one, each with a bar and its reset time) plus how full this session's context is.
Claude Code pipes session JSON in on stdin; see https://code.claude.com/docs/en/statusline"""
import json
import sys
import time

MINT, AMBER, CORAL = "\x1b[38;2;126;232;181m", "\x1b[38;2;255;195;138m", "\x1b[38;2;255;107;139m"
DIM, RESET = "\x1b[38;2;168;143;174m", "\x1b[0m"


def colour(pct):
    return MINT if pct < 50 else AMBER if pct < 80 else CORAL


def bar(pct, width=10):
    filled = min(width, round(pct / 100 * width))
    return colour(pct) + "█" * filled + DIM + "░" * (width - filled) + RESET


def reset_time(epoch, weekly):
    """'4:10pm' for today, 'Thu 9:00am' for another day of the week."""
    t = time.localtime(epoch)
    clock = time.strftime("%-I:%M%p", t).lower()
    same_day = time.strftime("%Y%m%d", t) == time.strftime("%Y%m%d")
    return clock if same_day or not weekly else time.strftime("%a ", t) + clock


data = json.load(sys.stdin)
parts = []
limits = data.get("rate_limits") or {}
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

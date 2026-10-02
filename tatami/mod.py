#!/usr/bin/env python3
"""What the Tatami Room mod inside Claude Code runs (the mod itself is in ../mod).

A mod lives inside Claude Code and can't walk the process tree, so it asks this script,
which finds the window's agent the way hooks.py does: the Claude process that started this
script is one of its parents, and that's the pid the agent's channel recorded.

  tatami mod poll [--wake]    this window's agent, its room and team, as one line of JSON.
                              With --wake (the session is idle and waking is on), also a
                              prompt to start a turn with, if a message to the agent came in
  tatami mod event [--chime]  the status hooks (see hooks.py), fed one Claude Code hook event
                              on stdin; --chime plays a chime on Windows when the agent
                              starts waiting for your OK
  tatami mod post TEXT        post TEXT to the window's room as the user ("@id text" sends it
                              to one agent)
"""
import json
import math
import os
import struct
import subprocess
import sys
import time
import wave

import hooks
import tatami_mcp as channel  # same folder: shares the file layout and helpers

PALETTE = channel.PALETTE
CREDITS = None  # waifu's art credits, read on first use
WAKES, WAKE_WINDOW = 3, 30 * 60  # at most 3 wake-ups in 30 minutes: two agents can't ping-pong forever
SHOWN = 40  # messages the /room pane gets


def me():
    """This window's agent record, or None in a session without the Tatami Room channel."""
    parents = set(hooks.ancestors(os.getpid()))
    return next((a for a in channel.live_agents() if a.get("pid") in parents), None)


def character(girl):
    """Who's in the window's picture, from waifu's art credits ('Yixuan'), or None."""
    global CREDITS
    if not girl:
        return None
    if CREDITS is None:
        pool = channel.load(os.path.expanduser("~/.config/waifu/config.json"), {}).get("pool") or ""
        CREDITS = channel.load(os.path.join(pool, "credits.json"), {}) if pool else {}
    return (CREDITS.get(girl) or {}).get("characters")


def status_path(agent):
    return os.path.join(channel.HOME, "status", agent["id"] + ".json")


def wake(agent, room, msgs):
    """A prompt to wake an idle agent with, when a message to it has come in that nothing has
    told it about yet. Marks it told. None when there's nothing (or it has woken enough)."""
    path = status_path(agent)
    status = channel.load(path, {})
    if status.get("state") == "asking":  # it's waiting for the user's OK: a prompt can't get in
        return None
    upto = (agent.get("read_upto") or {}).get(room, 0)
    seen = max(upto, status.get("told", 0))
    mine = [m for m in msgs if m.get("to") == agent["id"] and m["ts"] > seen]
    now = time.time()
    woke = [t for t in status.get("woke", []) if now - t < WAKE_WINDOW]
    if not mine or len(woke) >= WAKES:
        return None
    status.update(told=mine[-1]["ts"], woke=woke + [now])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    channel.save(path, status)
    senders = ", ".join(dict.fromkeys(name(m) for m in mine))
    many = len(mine) > 1
    return (f"Tatami Room: {senders} sent you {'messages' if many else 'a message'} in room '{room}' "
            f"while you were idle. Call room_read and answer in the room if it needs an answer. Skip "
            f"replies that only say thanks or OK, so the room doesn't keep waking everyone up.")


def name(m):
    return "the user" if m.get("from") == channel.USER else m.get("from", "?")


def poll(want_wake):
    agent = me()
    out = {"id": None, "color": None, "character": None, "room": None, "roomColor": None, "unread": 0,
           "latest": None, "messages": [], "members": [], "wake": None}
    if not agent:
        return out
    room = agent["room"]
    out.update(id=agent["id"], color=agent.get("color"), character=character(agent.get("girl")), room=room)
    if not room:
        return out
    live = channel.live_agents()
    rooms = channel.live_rooms(live)
    out["roomColor"] = PALETTE.get(channel.room_colors(rooms).get(room))
    msgs = channel.load_jsonl(os.path.join(channel.ROOMS, room + ".jsonl"))
    # What the agent hasn't read, less what the user typed: that's no news to the person looking.
    unread = [m for m in channel.unread(agent, room, msgs) if m.get("from") != channel.USER]
    out["unread"] = len(unread)
    if unread:
        out["latest"] = {"from": name(unread[-1]), "text": unread[-1].get("text", "")[:300]}
    out["messages"] = [{"ts": m["ts"], "from": name(m), "to": m.get("to"), "text": m.get("text", "")[:1000],
                        "mine": m.get("from") == agent["id"]} for m in msgs[-SHOWN:]]
    for rec in live:
        if rec["room"] != room:
            continue
        upto = (rec.get("read_upto") or {}).get(room, 0)
        out["members"].append({"id": rec["id"], "you": rec["id"] == agent["id"],
                               "state": channel.status_of(rec["id"]),
                               "readUpto": upto, "readAll": bool(msgs) and upto >= msgs[-1]["ts"],
                               "helperOf": rec.get("invited_by")})
    if want_wake:
        out["wake"] = wake(agent, room, msgs)
    return out


def post(text):
    agent = me()
    if not agent:
        sys.exit("This window has no Tatami Room channel.")
    room = agent["room"]
    if not room:
        sys.exit("This window's agent is on its own: team it up on the Tatami Room board first.")
    text, to = text.strip()[:channel.MAX_TEXT], None
    if text.startswith("@") and " " in text:
        to, text = channel.safe_name(text[1:].split(" ", 1)[0]), text.split(" ", 1)[1].strip()
    if not text:
        sys.exit("Nothing to post.")
    msg = {"ts": time.time(), "from": channel.USER, "via": agent["id"], "text": text}
    if to:
        msg["to"] = to
    channel.post(room, msg)
    print(f"Posted to room '{room}'" + (f" for {to}." if to else "."))


# The chime: two soft notes (E6, then B6), made here so nothing has to be downloaded.
def write_chime(path):
    rate, notes, frames = 44100, [(1318.5, 0.0), (1975.5, 0.11)], []
    length = int(rate * 0.75)
    for i in range(length):
        t, v = i / rate, 0.0
        for freq, start in notes:
            if t >= start:
                s = t - start
                v += math.sin(2 * math.pi * freq * s) * math.exp(-s * 7) * min(1, s * 200)
        frames.append(struct.pack("<h", int(v * 0.16 * 32767)))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(frames))


def chime():
    """Play the chime on Windows without waiting for it (WSL has no speakers of its own)."""
    folder = channel.load(os.path.expanduser("~/.config/waifu/config.json"), {}).get("launcher_dir")
    if not folder or not os.path.isdir(folder):
        return
    path = os.path.join(folder, "tatami-chime.wav")
    if not os.path.exists(path):
        write_chime(path)
    win = subprocess.run(["wslpath", "-w", path], capture_output=True, text=True).stdout.strip()
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                      f"(New-Object Media.SoundPlayer '{win}').PlaySync()"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def settings_hooks_on():
    """The same hooks can be on in Claude Code's settings (`tatami hooks on`): then they do it."""
    try:
        with open(hooks.SETTINGS, encoding="utf-8") as f:
            groups = json.load(f).get("hooks", {}).get("Stop", [])
    except (OSError, ValueError):
        return False
    return any(hooks.ours(h) for g in groups for h in g.get("hooks", []))


def event(play_chime):
    if settings_hooks_on():
        return None
    ev = json.load(sys.stdin)
    agent = me()
    before = channel.status_of(agent["id"]) if agent else None
    out = hooks.record(ev)
    if play_chime and agent and before != "asking" and channel.status_of(agent["id"]) == "asking":
        chime()
    return out


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "poll":
        print(json.dumps(poll("--wake" in args), ensure_ascii=False))
    elif cmd == "event":
        try:
            out = event("--chime" in args)
        except Exception:  # never get in Claude's way
            out = None
        print(json.dumps(out or {}))
    elif cmd == "post":
        post(" ".join(args[1:]))
    elif cmd == "chime":
        chime()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

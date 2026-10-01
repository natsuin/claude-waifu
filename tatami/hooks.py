#!/usr/bin/env python3
"""Tatami Room status hooks, so the board can show which agents need you.

Claude Code runs this on a few events: when you send a prompt, after each tool it uses,
when it finishes its turn, and when it's waiting for you to OK something. Each time it
notes the agent's state in one small file (~/.local/state/tatami/status/<agent id>.json):

  working   Claude is busy
  done      it finished its turn: your turn
  asking    it's waiting for your OK (a permission prompt or a question)

It always exits 0. Usually it prints nothing. The one thing it tells Claude is that room
messages it hasn't read have arrived, once per message:

  after a tool, or when you send a prompt   a short note: "2 new messages in room X"
  when it's about to finish its turn        if one is addressed to it, it's asked to read
                                            the room first (only once, never twice in a row)

So an agent busy with its work still hears its team, without checking the room every few
minutes. One that's waiting for you can't hear anything until you talk to it; the board
puts a letter on its mat.

  tatami hooks on     add the hooks to ~/.claude/settings.json (the first time, a backup
                      is kept next to it as settings.json.before-tatami-hooks)
  tatami hooks off    take them out again
"""
import json
import os
import sys
import time

import tatami_mcp as channel  # same folder: shares the file layout and helpers

SETTINGS = os.path.expanduser("~/.claude/settings.json")
COMMAND = '"$HOME/.local/bin/tatami" hook'  # through the link, so moving the repo can't break it
EVENTS = {"UserPromptSubmit": "working", "PostToolUse": "working", "Stop": "done", "Notification": None}
ASKING = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog", "agent_needs_input"}


def ancestors(pid):
    """This process's parents, up to init: the agent that ran the hook is one of them."""
    out = []
    while pid > 1 and len(out) < 30:
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
        out.append(pid)
    return out


def state_of(event):
    name = event.get("hook_event_name")
    if name != "Notification":
        return EVENTS.get(name)
    kind = event.get("notification_type") or ""
    message = str(event.get("message") or "").lower()
    if kind in ASKING or "permission" in message:
        return "asking"
    if kind == "idle_prompt" or "waiting for your input" in message:
        return "done"
    return None  # other notices (logins, quotas) don't change what the agent is doing


def record(event):
    """Note the agent's state, and return what to tell it about its room (or None)."""
    state, name = state_of(event), event.get("hook_event_name")
    if not state and name not in MAIL:
        return None
    parents = set(ancestors(os.getpid()))
    agent = next((a for a in channel.live_agents() if a.get("pid") in parents), None)
    if not agent:  # a session without the Tatami Room channel
        return None
    path = os.path.join(channel.HOME, "status", agent["id"] + ".json")
    before = channel.load(path, {})
    now = dict(before, state=state, ts=time.time()) if state and before.get("state") != state else dict(before)
    out = mail(event, agent, now)
    if now != before:  # most tool calls change nothing
        os.makedirs(os.path.dirname(path), exist_ok=True)
        channel.save(path, now)
    return out


MAIL = ("PostToolUse", "UserPromptSubmit", "Stop")


def mail(event, agent, status):
    """Room messages that came in since the agent last read the room, if it hasn't been told
    about them yet: what to tell it, in the shape its hook event takes. Marks them told."""
    name, room = event.get("hook_event_name"), agent["room"]
    if name not in MAIL or not room:
        return None
    msgs = channel.load_jsonl(os.path.join(channel.ROOMS, room + ".jsonl"))
    new = [m for m in channel.unread(agent, room, msgs) if m["ts"] > status.get("told", 0)]
    if not new:
        return None
    mine = [m for m in new if m.get("to") == agent["id"]]
    senders = ", ".join(dict.fromkeys(m.get("from", "?") for m in new))
    if name == "Stop":
        # Only a message to this agent holds up the end of its turn, and only once in a row.
        if not mine or event.get("stop_hook_active"):
            return None
        status.update(told=new[-1]["ts"], state="working", ts=time.time())  # it isn't done after all
        many = len(mine) > 1
        return {"decision": "block",
                "reason": f"Tatami Room: {len(mine)} message{'s' if many else ''} to you from {senders} "
                          f"came in while you worked. Call room_read and answer in the room before you "
                          f"finish."}
    status["told"] = new[-1]["ts"]
    text = (f"Tatami Room: {len(new)} new message{'s' if len(new) > 1 else ''} in room '{room}' from "
            f"{senders}" + (f", {len(mine)} addressed to you" if mine else "")
            + ". Call room_read when you reach a good point.")
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}


def ours(hook):
    return "tatami" in hook.get("command", "") and hook.get("command", "").rstrip().endswith(" hook")


def install(on):
    """Add our hook to each event in Claude Code's settings (or take it out), leaving every
    other setting and hook as it was."""
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    except ValueError:
        sys.exit(f"{SETTINGS} isn't plain JSON, so I'm not touching it.")
    backup = SETTINGS + ".before-tatami-hooks"
    if on and os.path.exists(SETTINGS) and not os.path.exists(backup):
        with open(SETTINGS, encoding="utf-8") as f, open(backup, "w", encoding="utf-8") as b:
            b.write(f.read())
    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        groups = []
        for group in hooks.get(event, []):
            kept = [h for h in group.get("hooks", []) if not ours(h)]
            if kept:
                groups.append(dict(group, hooks=kept))
        if on:
            groups.append({"hooks": [{"type": "command", "command": COMMAND}]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        settings.pop("hooks")
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS + ".tmp", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(SETTINGS + ".tmp", SETTINGS)
    print("Tatami Room hooks are on: the board shows which agents need you, and agents hear about room "
          "messages while they work (new and open sessions pick them up)."
          if on else "Tatami Room hooks are off.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "event":
        try:
            out = record(json.load(sys.stdin))
        except Exception:  # never get in Claude's way
            out = None
        if out:
            print(json.dumps(out))
        return
    if cmd in ("on", "off"):
        install(cmd == "on")
        return
    print(__doc__)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Tatami Room status hooks, so the board can show which agents need you.

Claude Code runs this on a few events: when you send a prompt, after each tool it uses,
when it finishes its turn, and when it's waiting for you to OK something. Each time it
notes the agent's state in one small file (~/.local/state/tatami/status/<agent id>.json):

  working   Claude is busy
  done      it finished its turn: your turn
  asking    it's waiting for your OK (a permission prompt or a question)

It prints nothing and always exits 0, so it never changes what Claude does.

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
    state = state_of(event)
    if not state:
        return
    parents = set(ancestors(os.getpid()))
    agent = next((a for a in channel.live_agents() if a.get("pid") in parents), None)
    if not agent:  # a session without the Tatami Room channel
        return
    path = os.path.join(channel.HOME, "status", agent["id"] + ".json")
    if channel.load(path, {}).get("state") == state:  # most tool calls change nothing
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    channel.save(path, {"state": state, "ts": time.time()})


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
    print("Tatami Room hooks are on: the board shows which agents need you (new and open sessions pick them up)."
          if on else "Tatami Room hooks are off.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "event":
        try:
            record(json.load(sys.stdin))
        except Exception:  # never get in Claude's way
            pass
        return
    if cmd in ("on", "off"):
        install(cmd == "on")
        return
    print(__doc__)


if __name__ == "__main__":
    main()

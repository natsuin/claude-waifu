#!/usr/bin/env python3
"""Start a helper that an agent brought into its Tatami Room with room_invite.

room_invite leaves the task in invites/<token>.json and has waifu open a new Claude Waifu
window running `tatami helper <token>`. This picks the task up (once: the file goes), and
starts Claude in the inviting agent's folder with the task as its first prompt. The room
and the inviter's id ride along in the environment, so the helper's channel joins that
room and the board knows whose helper it is. When Claude exits, the window drops to a
plain shell, like every Claude Waifu window.
"""
import os
import re
import sys
import time

import tatami_mcp as channel  # same folder: shares the file layout

BRIEF = """(This came from {by}, another agent in your Tatami Room, through room_invite. The user \
didn't type it, but they can see this window and talk to you here: if they ask for something \
different, do what they say.)

{by} brought you into room '{room}' to take one piece of its work:

{task}

Start with room_read for the room's context. Post in the room (to: {by}) when you start, if \
you get stuck, and when you're done, saying which files you changed. Keep to the files the \
task gives you: {by} and the others may be editing the rest. You can't bring in helpers \
yourself."""


def main():
    token = sys.argv[1] if len(sys.argv) > 1 else ""
    if not re.fullmatch(r"[0-9a-f]{32}", token):  # only ever a name room_invite made
        token = "missing"
    path = os.path.join(channel.INVITES, token + ".json")
    task = channel.load(path, {})
    if os.path.exists(path):
        os.remove(path)
    if not task or time.time() - task.get("created", 0) > 3600:
        print("Tatami Room: this helper's task is gone or stale (over an hour old), so there's nothing to start.",
              flush=True)  # exec would drop it otherwise
        os.execvp("bash", ["bash", "-l"])
    room, by = channel.safe_name(task["room"]), channel.safe_name(task["by"])
    os.environ.update(TATAMI_ROOM=room, TATAMI_INVITED_BY=by, TATAMI_INVITE=token,
                      TATAMI_BRIEF=BRIEF.format(by=by, room=room, task=task["task"]))
    try:
        os.chdir(task["cwd"])
    except OSError:
        pass
    if task.get("dry"):  # tests: show what would start, without starting Claude
        print(f"helper of {by} in room {room}, folder {os.getcwd()}\n\n{os.environ['TATAMI_BRIEF']}", flush=True)
        time.sleep(float(task["dry"]))
        return
    # The brief goes through the environment, never through a command line or a shell's parser;
    # the room settings are dropped again for the shell that's left when Claude exits.
    os.execvp("bash", ["bash", "-lic", 'b=$TATAMI_BRIEF; unset TATAMI_BRIEF; claude "$b"; '
                       "unset TATAMI_ROOM TATAMI_INVITED_BY TATAMI_INVITE; exec bash"])


if __name__ == "__main__":
    main()

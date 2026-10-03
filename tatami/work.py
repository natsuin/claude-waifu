#!/usr/bin/env python3
"""A team's work, so agents in a room can work at the same time without getting in each
other's way: the room's plan of tasks, claims on files, and a git worktree for each agent.

  tasks/<room>.json   the room's plan: each task, who has it, what done looks like, the files
                      it covers, and how far it has got (open, doing, blocked, done, landed)
  claims.json         the files each agent is working on; inside Claude Code the Tatami Room
                      mod refuses a teammate's edit to one (mod.py guard)
  worktrees.json      each agent's own worktree and branch, per repository

On a team, an agent doesn't edit the repository you have checked out. Its first edit there
gives it a worktree of its own, on a branch made from the branch you're on, under
~/.local/share/tatami/worktrees, and it works there from then on. Finished work comes back
with room_land: the branch is rebased onto yours in the worktree, so any conflict stays
there, and your branch is fast-forwarded to it. Git refuses rather than overwrite changes
you haven't committed. With an orchestrator, it lands the others' work; without one, each
agent lands its own.
"""
import fnmatch
import os
import re
import subprocess
import time

import tatami_mcp as channel  # same folder: the file layout and helpers it shares

TASKS = os.path.join(channel.HOME, "tasks")
CLAIMS = os.path.join(channel.HOME, "claims.json")
WORKTREES = os.path.join(channel.HOME, "worktrees.json")
TREES = os.path.expanduser(os.environ.get("TATAMI_WORKTREES") or "~/.local/share/tatami/worktrees")
OPEN = ("open", "doing", "blocked")  # not finished yet
HELD = ("doing", "blocked", "done")  # its owner still has its files: done isn't in your checkout yet
INVITED = "invite:"  # a task's owner while the helper it went to is still starting
TITLE, LONGEST = 200, 2000  # a task's title, and its done_when or a note: longer is refused, never cut short
TOOLS = [
    {"name": "room_task",
     "description": "Your Tatami Room's plan: a list of tasks, each with one owner, the files it covers and "
                    "what done looks like. The desk shows it to the user. action 'add' puts a task on the plan "
                    "(give owner to hand it to a teammate: they're told at once), 'take' makes an open task "
                    "yours, 'update' changes its status (doing, blocked, open), owner or note, 'done' says "
                    "you finished it (commit first; note says what changed and how you checked it), 'list' "
                    "shows the plan.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["add", "take", "update", "done", "list"]},
         "id": {"type": "string", "description": "The task's id, like t3 (take, update, done)"},
         "title": {"type": "string", "description": "add: the task in a few words"},
         "done_when": {"type": "string", "description": "add: what done looks like, so its owner knows when to stop "
                                                        f"(at most {LONGEST} characters)"},
         "files": {"type": "array", "items": {"type": "string"},
                   "description": "add: the files or folders (ending in /) it covers, as absolute paths. "
                                  "They become its owner's, so no teammate edits them meanwhile"},
         "owner": {"type": "string", "description": "add, update: the agent id it goes to"},
         "status": {"type": "string", "enum": ["doing", "blocked", "open"], "description": "update"},
         "note": {"type": "string", "description": "update: why it's blocked, or news; done: what changed "
                                                   f"and how you checked it (at most {LONGEST} characters)"}},
         "required": ["action"]}},
    {"name": "room_claim",
     "description": "Say which files you're working on, so your teammates' edits to them are refused until you "
                    "let go (files you edit are claimed for you anyway). release=true lets go of the paths "
                    "you name, or of all your claims when you name none.",
     "inputSchema": {"type": "object", "properties": {
         "paths": {"type": "array", "items": {"type": "string"},
                   "description": "Absolute paths of files, or folders ending in /"},
         "release": {"type": "boolean"}}}},
    {"name": "room_land",
     "description": "Bring finished work from a worktree into the user's checkout: rebases the branch onto the "
                    "user's branch in the worktree, then fast-forwards the user's branch to it. With an "
                    "orchestrator, only it lands (agent: whose work); without one, you land your own. Leave "
                    "agent out to land your own, or to see what's waiting.",
     "inputSchema": {"type": "object", "properties": {
         "agent": {"type": "string", "description": "Whose work to land (default: yours)"},
         "repo": {"type": "string", "description": "Which repository, when they have worktrees in more than one"}}}},
]


class Refused(Exception):
    """Something a tool can't do, said for the agent that asked."""


def git(*args, cwd):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def hhmm(ts):
    return time.strftime("%H:%M", time.localtime(ts))


def tilde(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


# ---- where a file lives ----

def repo_of(path):
    """The repository a path is in: (its main checkout, the checkout the path is in, the path
    inside it). None outside git. A path in a worktree names the main checkout too, so a file
    is the same file wherever it's edited."""
    path = os.path.realpath(os.path.expanduser(path))
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while d and d != "/" and not os.path.isdir(d):  # a new file in a new folder
        d = os.path.dirname(d)
    r = git("rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir", cwd=d or "/")
    lines = r.stdout.split("\n")
    if r.returncode != 0 or len(lines) < 2 or os.path.basename(lines[1]) != ".git":
        return None  # not in git, or a bare repository: nothing to keep apart
    top = lines[0]
    rel = os.path.relpath(path, top)
    if rel == ".git" or rel.startswith(".git/"):
        return None
    return os.path.dirname(lines[1]), top, rel


def canonical(path):
    """The name a claim goes by: the path in the main checkout, wherever the file is edited."""
    where = repo_of(path)
    if not where:
        return os.path.realpath(os.path.expanduser(path))
    main, _, rel = where
    return os.path.normpath(os.path.join(main, rel))


def covers(claim, path):
    """Whether a claimed path (a file, a folder ending in /, or a glob) covers `path`."""
    if claim.endswith("/"):
        return path.startswith(claim) or path == claim.rstrip("/")
    if any(c in claim for c in "*?["):
        return fnmatch.fnmatch(path, claim)
    return path == claim


def claim_name(path):
    """A path an agent gave, as a claim: canonical, keeping a folder's trailing slash."""
    folder = path.endswith("/")
    name = canonical(path.rstrip("/") or "/")
    return name.rstrip("/") + "/" if folder else name


# ---- the plan ----

def tasks_path(room):
    return os.path.join(TASKS, channel.safe_name(room) + ".json")


def tasks(room):
    return channel.load(tasks_path(room), []) if room else []


def save_tasks(room, items):
    os.makedirs(TASKS, exist_ok=True)
    channel.save(tasks_path(room), items)


def find(items, tid):
    tid = str(tid or "").strip().lower()
    tid = tid if tid.startswith("t") else f"t{tid}"
    return next((t for t in items if t["id"] == tid), None)


def current(items, agent_id):
    """The task an agent is on: its newest one in progress."""
    mine = [t for t in items if t.get("owner") == agent_id and t["status"] == "doing"]
    return max(mine, key=lambda t: t["updated"]) if mine else None


def line(t):
    """One task, as the tools show it."""
    owner = t.get("owner") or "no one yet"
    if owner.startswith(INVITED):
        owner = "a helper that's starting"
    status = {"done": "done, waiting to land" if t.get("branch") else "done"}.get(t["status"], t["status"])
    out = f"{t['id']} [{status}] {t['title']} (owner: {owner}"
    out += f"; done when: {t['done_when']}" if t.get("done_when") else ""
    out += f"; files: {', '.join(tilde(f) for f in t['files'])}" if t.get("files") else ""
    out += f"; note: {t['note']}" if t.get("note") else ""
    return out + ")"


def plan(room, everything=False):
    """The room's plan, as room_members and room_task list say it: what's left, and the newest
    finished tasks."""
    items = tasks(room)
    if not items:
        return "The plan is empty: no tasks yet."
    # Done work that's still to land isn't finished: it isn't in the user's checkout yet.
    left = [t for t in items if t["status"] != "landed" and (everything or t["status"] != "done" or t.get("branch"))]
    done = [t for t in items if t not in left]
    out = [line(t) for t in left] or ["Nothing left to do."]
    if done:
        out.append(f"Finished: {len(done)} task{'s' if len(done) > 1 else ''}"
                   + (f" (newest: {', '.join(t['id'] + ' ' + t['title'] for t in done[-3:])})" if not everything else ""))
    return "The room's plan:\n" + "\n".join("- " + x for x in out)


def to_land(items, agent_id, lead):
    """The finished work on a plan that `agent_id` is the one to land: everyone's, for the
    orchestrator; with no orchestrator, its own."""
    return [t for t in items if t["status"] == "done" and t.get("branch")
            and (lead == agent_id if lead else t.get("owner") == agent_id)]


def landing(room, agent_id, lead):
    """For whoever lands the room's work, at the top of room_read: what's waiting for it, so a
    done report can't get lost among older messages. Empty when there's nothing."""
    ready = to_land(tasks(room), agent_id, lead)
    if not ready:
        return ""
    return "Finished and waiting for you to land: " + "; ".join(
        f"{t['id']} {t['title']} ({t['owner']}'s {t['branch']}: room_land"
        + (f" agent={t['owner']}" if lead == agent_id else "") + ")" for t in ready) + "."


# ---- claims ----

def claims():
    """Every live claim. A claim lasts while its agent is running and in the room it was made in."""
    live = {a["id"]: a["room"] for a in channel.live_agents()}
    return [c for c in channel.load(CLAIMS, []) if live.get(c["agent"]) == c["room"] and c["room"]]


def holder(path, agent_id, room):
    """The teammate's claim covering `path`, if there is one: (claim, its task or None)."""
    name = canonical(path)
    for c in claims():
        if c["room"] == room and c["agent"] != agent_id and covers(c["path"], name):
            return c, (find(tasks(room), c["task"]) if c.get("task") else None)
    return None


def claim(agent_id, room, paths, task=None, auto=False):
    """Claim `paths` for an agent. Call it holding locked(). Paths a teammate holds are left
    out and returned, with who holds them."""
    kept, taken = [c for c in channel.load(CLAIMS, [])], []
    live = {a["id"]: a["room"] for a in channel.live_agents()}
    kept = [c for c in kept if live.get(c["agent"]) == c["room"]]  # forget the gone and the moved
    for p in paths:
        name = claim_name(p)
        other = next((c for c in kept if c["room"] == room and c["agent"] != agent_id
                      and (covers(c["path"], name) or covers(name, c["path"]))), None)
        if other:
            taken.append((name, other))
            continue
        kept = [c for c in kept if not (c["agent"] == agent_id and c["path"] == name)]
        where = repo_of(name.rstrip("/"))
        kept.append({"path": name, "agent": agent_id, "room": room, "task": task, "auto": auto, "ts": time.time(),
                     "repo": where[0] if where else None})
    channel.save(CLAIMS, kept)
    return taken


def release(agent_id, paths=None, task=None, under=None):
    """Let go of an agent's claims: the paths named, those for one task, those inside one
    folder, or all of them. Call it holding locked(). Returns how many it let go."""
    names = {claim_name(p) for p in paths} if paths else None
    all_claims = channel.load(CLAIMS, [])

    def goes(c):
        if c["agent"] != agent_id:
            return False
        if names is not None:
            return c["path"] in names
        if task is not None:
            return c.get("task") == task
        if under is not None:
            return c["path"].startswith(under.rstrip("/") + "/")
        return True
    kept = [c for c in all_claims if not goes(c)]
    if len(kept) != len(all_claims):
        channel.save(CLAIMS, kept)
    return len(all_claims) - len(kept)


def held(c, t):
    """How the guard and room_claim say whose a file is."""
    who = c["agent"]
    if t:
        return f"it's part of {who}'s task {t['id']} ({t['title']}, {t['status']})"
    return f"{who} has been working on it since {hhmm(c['ts'])}"


# ---- worktrees ----

def trees():
    return channel.load(WORKTREES, {})


def tree_of(agent_id, main):
    rec = trees().get(agent_id, {}).get(main)
    return rec if rec and os.path.isdir(rec["path"]) else None


def dirty(path):
    """The files with changes not committed in a checkout."""
    r = git("status", "--porcelain", "--untracked-files=normal", cwd=path)
    return [l[3:] for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def make_tree(agent_id, main):
    """The agent's own worktree of the repository whose main checkout is `main`: the one it has,
    or a new one on a branch made from the branch the main checkout is on. Returns (record,
    whether it's new)."""
    rec = tree_of(agent_id, main)
    if rec:
        return rec, False
    base = git("symbolic-ref", "--short", "-q", "HEAD", cwd=main).stdout.strip()
    if not base:
        raise Refused(f"{tilde(main)} isn't on a branch (a detached HEAD), so there's nothing to branch your "
                      "worktree from. Ask the user to check out a branch there.")
    name = channel.safe_name(os.path.basename(main))
    for n in range(1, 100):
        suffix = "" if n == 1 else f"-{n}"
        branch, path = f"tatami/{agent_id}{suffix}", os.path.join(TREES, name, agent_id + suffix)
        if not os.path.exists(path) and git("show-ref", "--verify", "-q", f"refs/heads/{branch}", cwd=main).returncode:
            break
    else:
        raise Refused(f"There are already 99 worktrees named after {agent_id} in {TREES}.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    made = git("worktree", "add", "-b", branch, path, base, cwd=main)
    if made.returncode:
        raise Refused(f"Couldn't make a worktree of {tilde(main)}: {made.stderr.strip()[-300:]}")
    rec = {"path": path, "branch": branch, "base": base, "made": time.time()}
    with channel.locked():
        all_trees = trees()
        all_trees.setdefault(agent_id, {})[main] = rec
        channel.save(WORKTREES, all_trees)
    return rec, True


def ahead(rec):
    """Commits on a worktree's branch that its base doesn't have yet."""
    r = git("rev-list", "--count", f"{rec['base']}..{rec['branch']}", cwd=rec["path"])
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0


def catch_up(rec):
    """Bring a worktree up to its base branch, which moves on as work lands and the user commits:
    straight away when it has nothing of its own yet. Returns what to tell its agent when it
    can't (it has commits or changes of its own), else None."""
    behind = git("rev-list", "--count", f"{rec['branch']}..{rec['base']}", cwd=rec["path"]).stdout.strip()
    if not behind.isdigit() or behind == "0":
        return None
    if not dirty(rec["path"]) and not ahead(rec):
        if git("merge", "--ff-only", "-q", rec["base"], cwd=rec["path"]).returncode == 0:
            return None
    return (f"Your worktree is {behind} commit{'s' if behind != '1' else ''} behind {rec['base']}: bring it up to "
            f"date first (commit your changes, then git -C {rec['path']} rebase {rec['base']}).")


def drop_tree(agent_id, main, force=False):
    """Take away a worktree once nothing in it is waiting: no changes, no commits to land. Its
    branch goes too. Returns whether it went."""
    rec = trees().get(agent_id, {}).get(main)
    if not rec:
        return False
    if os.path.isdir(rec["path"]):
        if not force and (dirty(rec["path"]) or ahead(rec)):
            return False
        if git("worktree", "remove", *(["--force"] if force else []), rec["path"], cwd=main).returncode:
            return False
    git("branch", "-D" if force else "-d", rec["branch"], cwd=main)
    with channel.locked():
        all_trees = trees()
        all_trees.get(agent_id, {}).pop(main, None)
        if not all_trees.get(agent_id):
            all_trees.pop(agent_id, None)
        channel.save(WORKTREES, all_trees)
    return True


def retire(agent_id):
    """An agent has closed: its claims go, its unfinished tasks go back on the plan for someone
    else, and its worktrees are kept under a name of their own ("dusk.1791000123"), so a later
    agent that gets the same id doesn't take over its work. Finished work in them still waits
    to land; tidy takes away the ones with nothing in them. Call it holding locked()."""
    release(agent_id)
    all_trees = trees()
    left = {}
    for main, rec in all_trees.pop(agent_id, {}).items():
        left[main] = f"{agent_id}.{int(rec['made'])}"
        all_trees.setdefault(left[main], {})[main] = rec
    if left:
        channel.save(WORKTREES, all_trees)
    for fn in os.listdir(TASKS) if os.path.isdir(TASKS) else []:
        room = fn[:-5] if fn.endswith(".json") else None
        items = tasks(room) if room else []
        changed = False
        for t in items:
            if t.get("owner") != agent_id:
                continue
            if t["status"] in OPEN:
                t.update(owner=None, status="open", note=f"{agent_id} closed before finishing it", updated=time.time())
                changed = True
            elif t["status"] == "done" and t.get("branch") and left:
                t.update(owner=next(iter(left.values())), updated=time.time())  # so room_land finds its branch
                changed = True
        if changed:
            save_tasks(room, items)


def tidy(live_ids):
    """The worktrees of agents that have closed: each one goes if nothing in it is waiting; one
    with work left stays, for the desk to show and an orchestrator or the user to land."""
    for agent_id, repos in list(trees().items()):
        if agent_id not in live_ids:
            for main in list(repos):
                drop_tree(agent_id, main)


# ---- the guard: what the mod asks before Claude edits a file ----

def teamed(agent, live):
    """Whether an agent shares its room with anyone right now."""
    return bool(agent["room"]) and any(a["room"] == agent["room"] and a["id"] != agent["id"] for a in live)


def tree_owner(main, top):
    """Whose worktree the checkout at `top` is, if it's one of ours."""
    top = os.path.realpath(top)
    return next((aid for aid, repos in trees().items() for m, rec in repos.items()
                 if m == main and os.path.realpath(rec["path"]) == top), None)


def guard(agent, path, live=None):
    """Whether `agent` may edit `path`: None if so (claiming it), else what to tell it."""
    live = channel.live_agents() if live is None else live
    where = repo_of(path)
    if where:
        main, top, rel = where
        rec = tree_of(agent["id"], main)
        in_main = os.path.realpath(top) == os.path.realpath(main)
        owner = None if in_main else tree_owner(main, top)
        if owner and owner != agent["id"]:
            mine = f" Yours is {rec['path']}." if rec else ""
            return (f"Tatami Room: {tilde(top)} is {owner}'s worktree, not yours: leave its files to {owner}.{mine}")
        ignored = in_main and git("check-ignore", "-q", rel, cwd=main).returncode == 0
        if in_main and not ignored and (rec or teamed(agent, live)):
            rec, new = make_tree(agent["id"], main) if not rec else (rec, False)
            there = os.path.join(rec["path"], rel)
            behind = catch_up(rec) if not os.path.exists(there) and os.path.exists(path) else None
            how = (" Use its absolute paths with your usual tools (Read, Edit, Bash with git -C); you don't need "
                   "to switch folders or use EnterWorktree.")
            if new:
                waiting = dirty(main)
                note = (f" The user's checkout has {len(waiting)} uncommitted change{'s' if len(waiting) > 1 else ''} "
                        f"that {'aren' if len(waiting) > 1 else 'isn'}'t in it." if waiting else "")
                return (f"Tatami Room: you share this room with others, so you don't edit {tilde(main)} itself. "
                        f"You have a worktree of your own now: {rec['path']} (branch {rec['branch']}, made from "
                        f"{rec['base']}).{note} Make this edit there instead: {there}. Do all your work in this "
                        f"repository there from now on, and commit there.{how} When your piece is done, room_task "
                        f"done, then room_land brings it into {tilde(main)}.")
            return (f"Tatami Room: {tilde(main)} is the user's checkout. You work in your worktree, "
                    f"{rec['path']} (branch {rec['branch']}): edit {there} instead.{how}"
                    + (f" {behind}" if behind else ""))
    if not agent["room"] or not teamed(agent, live):
        return None
    with channel.locked():
        other = holder(path, agent["id"], agent["room"])
        if not other:
            if where:  # a project's file is claimed as it's edited; scratch files and notes aren't anyone's
                items = tasks(agent["room"])
                mine = current(items, agent["id"])
                claim(agent["id"], agent["room"], [path], task=mine["id"] if mine else None, auto=True)
            return None
    c, t = other
    return (f"Tatami Room: {tilde(canonical(path))} isn't yours to edit: {held(c, t)}. Ask {c['agent']} in "
            f"the room (room_post to: {c['agent']}) or work on something else. When {c['agent']} is done with "
            "it, the claim lifts (or it can room_claim release), and the user can clear it on the desk.")


GIT_WRITES = re.compile(r"\bgit\b[^;&|]*?\b(commit|add|rm|mv|checkout|switch|restore|reset|stash|merge|rebase|"
                        r"cherry-pick|revert|pull|am|apply|clean)\b")


def guard_bash(agent, command):
    """A Bash command that would change git in the user's checkout of a repository the agent
    has a worktree of: what to tell it instead (else None)."""
    for main, rec in trees().get(agent["id"], {}).items():
        names = [main, tilde(main)]
        if not any(re.search(re.escape(n) + r"(/|\s|$|['\"])", command) for n in names):
            continue
        if rec["path"] in command or tilde(rec["path"]) in command:
            continue  # it names its worktree too: it knows where it is
        if GIT_WRITES.search(command):
            return (f"Tatami Room: that would change git in {tilde(main)}, the user's checkout. Your work goes in "
                    f"your worktree, {rec['path']} (branch {rec['branch']}): run it there "
                    f"(git -C {rec['path']} ...). room_land brings finished work into {tilde(main)}.")
    return None


# ---- the tools ----

def answer(agent, name, args, room):
    """room_task, room_claim and room_land. Returns (text, is_error)."""
    if not room and name != "room_land":
        return channel.ALONE, False
    try:
        if name == "room_task":
            return task_tool(agent, args, room), False
        if name == "room_claim":
            return claim_tool(agent, args, room), False
        if name == "room_land":
            return land_tool(agent, args, room), False
    except Refused as e:
        return str(e), True
    return f"Unknown tool: {name}", True


def say(room, frm, text, to=None, **more):
    """Post what the tools tell the room. These are about the plan, so a long one says where the rest is."""
    if len(text) > channel.MAX_TEXT:
        tail = " … (cut short here: room_task list has all of it)"
        text = text[:channel.MAX_TEXT - len(tail)] + tail
    msg = {"ts": time.time(), "from": frm, "text": text, **more}
    if to:
        msg["to"] = to
    channel.post(room, msg)


def task_tool(agent, args, room):
    action = str(args.get("action") or "list")
    live = channel.live_agents()
    here = {a["id"] for a in live if a["room"] == room}
    lead = channel.lead_of(room, live)
    if action == "list":
        return plan(room, everything=True) + idle(agent.id, room, live)
    with channel.locked():
        items = tasks(room)
        if action == "add":
            out = add_task(agent, args, room, items, here, lead)
        else:
            t = find(items, args.get("id"))
            if not t:
                raise Refused(f"No task {args.get('id') or '(no id given)'} in room '{room}'. room_task list shows the plan.")
            out = {"take": take_task, "update": update_task, "done": done_task}.get(action)
            if not out:
                raise Refused(f"Unknown action '{action}': use add, take, update, done or list.")
            out = out(agent, args, room, t, here, lead)
        save_tasks(room, items)
    return out + idle(agent.id, room, live)


def text_of(args, key, what):
    """What an agent wrote for a task, all of it: too long is refused rather than cut short, so
    no one works from half a spec without knowing."""
    text = str(args.get(key) or "").strip()
    if len(text) > LONGEST:
        raise Refused(f"{what} is {len(text)} characters, and it can be at most {LONGEST}. Shorten it, or send "
                      "the details with room_post.")
    return text


def idle(agent_id, room, live):
    """For the room's orchestrator, while there's work on the plan: its teammates on no unfinished
    task, so it doesn't plan around someone it hasn't noticed. Empty for everyone else."""
    if channel.lead_of(room, live) != agent_id:
        return ""
    items = tasks(room)
    busy = {t.get("owner") for t in items if t["status"] in OPEN}
    if not busy:
        return ""
    who = sorted(a["id"] for a in live if a["room"] == room and a["id"] != agent_id and a["id"] not in busy)
    if not who:
        return ""
    many = len(who) > 1
    return (f"\nNot on any task: {', '.join(who)}. Give {'each' if many else 'it'} a piece of the plan, or "
            f"tell {'them' if many else 'it'} to wait.")


def files_of(args):
    files = [str(f).strip() for f in (args.get("files") or []) if str(f).strip()][:50]
    bad = [f for f in files if not f.startswith(("/", "~"))]
    if bad:
        raise Refused(f"Give files as absolute paths (not {bad[0]}), so everyone means the same file.")
    return [claim_name(f) for f in files]


def add_task(agent, args, room, items, here, lead):
    title = str(args.get("title") or "").strip()
    if not title:
        raise Refused("A task needs a title: what it is, in a few words.")
    if len(title) > TITLE:
        raise Refused(f"Not added: the title is {len(title)} characters, and it can be at most {TITLE}. Say the "
                      "task in a few words and put the rest in done_when.")
    done_when = text_of(args, "done_when", "Not added: done_when")
    owner = channel.safe_name(str(args["owner"])) if args.get("owner") else None
    if owner in ("me", agent.id):
        owner = agent.id
    if owner and owner not in here:
        raise Refused(f"{owner} isn't in room '{room}'. In it: {', '.join(sorted(here))}.")
    if owner and owner != agent.id and lead and lead != agent.id:
        raise Refused(f"{lead} is this room's orchestrator, so it hands out the work. Add the task without an "
                      f"owner (it goes on the plan for {lead} to give out), or ask {lead}.")
    n = max([int(t["id"][1:]) for t in items if t["id"][1:].isdigit()] + [0]) + 1
    t = {"id": f"t{n}", "title": title, "done_when": done_when,
         "files": files_of(args), "owner": owner, "by": agent.id, "status": "doing" if owner == agent.id else "open",
         "note": "", "branch": None, "created": time.time(), "updated": time.time()}
    items.append(t)
    taken = claim(owner, room, t["files"], task=t["id"]) if owner and t["files"] else []
    if owner and owner != agent.id:  # a direct message, so it hears even mid-turn, or wakes for it
        say(room, agent.id, f"Task {t['id']} for you: {title}."
            + (f" Done when: {t['done_when']}." if t["done_when"] else "")
            + (f" Files: {', '.join(tilde(f) for f in t['files'])}." if t["files"] else "")
            + " Start with room_task take, or tell me why not.", to=owner)
    else:
        say(room, agent.id, f"Added task {t['id']} to the plan: {title}" + (" (mine)." if owner else " (no owner yet)."))
    out = f"Added {line(t)}."
    if taken:
        out += " " + " ".join(f"{tilde(p)} is already {c['agent']}'s, so it isn't claimed for this task." for p, c in taken)
    return out


def take_task(agent, args, room, t, here, lead):
    if t.get("owner") not in (None, agent.id) and t["owner"] in here:
        raise Refused(f"{t['id']} is {t['owner']}'s. Ask {lead or t['owner']} to hand it to you.")
    if t["status"] in ("done", "landed"):
        raise Refused(f"{t['id']} is already {t['status']}.")
    t.update(owner=agent.id, status="doing", updated=time.time())
    taken = claim(agent.id, room, t["files"], task=t["id"]) if t["files"] else []
    say(room, agent.id, f"Taking {t['id']}: {t['title']}.", to=lead if lead and lead != agent.id else None)
    out = f"{t['id']} is yours: {line(t)}."
    for p, c in taken:
        out += f" {tilde(p)} is still {c['agent']}'s, so you can't edit it until {c['agent']} lets go: ask in the room."
    return out


def update_task(agent, args, room, t, here, lead):
    owner = channel.safe_name(str(args["owner"])) if args.get("owner") else None
    note = text_of(args, "note", f"Not updated: the note on {t['id']}")
    mine = t.get("owner") == agent.id
    if not (mine or agent.id in (lead, t.get("by")) or not t.get("owner") or t["owner"] not in here):
        raise Refused(f"{t['id']} is {t['owner']}'s: only it, {('the orchestrator ' + lead) if lead else 'whoever added it'} "
                      "can change it.")
    news = []
    if owner and owner != t.get("owner"):
        if owner not in here:
            raise Refused(f"{owner} isn't in room '{room}'.")
        if lead and agent.id != lead and owner != agent.id:
            raise Refused(f"{lead} is the orchestrator, so it decides who does what. Ask it to hand {t['id']} on.")
        if t.get("owner"):
            release(t["owner"], task=t["id"])
        t["owner"] = owner
        t["status"] = "doing" if owner == agent.id else "open"
        claim(owner, room, t["files"], task=t["id"])
        news.append(f"it's {owner}'s now")
    status = args.get("status")
    if status in ("doing", "blocked", "open") and status != t["status"]:
        t["status"] = status
        news.append(status)
        if status == "open" and not owner and t.get("owner"):  # handed back: anyone may take it
            release(t["owner"], task=t["id"])
            t["owner"] = None
    if note:
        t["note"] = note
        news.append(f"note: {t['note']}")
    if not news:
        return f"Nothing changed: {line(t)}."
    t["updated"] = time.time()
    # Who hears it: the new owner, else the orchestrator, else whoever added the task.
    to = next((x for x in (owner, lead, t.get("by")) if x and x != agent.id and x in here), None)
    say(room, agent.id, f"{t['id']} ({t['title']}): {'; '.join(news)}.", to=to)
    return f"Updated {line(t)}."


def done_task(agent, args, room, t, here, lead):
    if t.get("owner") != agent.id:
        raise Refused(f"{t['id']} is {t.get('owner') or 'no one'}'s, not yours: only its owner says it's done.")
    note = text_of(args, "note", f"Not done: the note on {t['id']}")
    if not note:
        raise Refused("Say what changed and how you checked it (note), so whoever lands it knows what it's getting.")
    waiting = []
    for main, rec in trees().get(agent.id, {}).items():
        changed = dirty(rec["path"])
        if changed:
            raise Refused(f"Your worktree {rec['path']} has changes you haven't committed ({', '.join(changed[:5])}). "
                          "Commit what belongs to this task there first, then say it's done.")
        if ahead(rec):
            waiting.append((main, rec))
    t.update(status="done", note=note, updated=time.time(),
             branch=", ".join(rec["branch"] for _, rec in waiting) or None)
    if not waiting:
        release(agent.id, task=t["id"])
    lands = lead if lead and lead != agent.id else None
    text = f"Done with {t['id']} ({t['title']}): {note}"
    if waiting and lands:
        text += f" Ready to land: {', '.join(rec['branch'] for _, rec in waiting)} (room_land agent={agent.id})."
    # Marked as a done report, so it wakes whoever lands it even when its wake-ups have run out (mod.wake).
    say(room, agent.id, text, to=lands or (t.get("by") if t.get("by") in here and t.get("by") != agent.id else None),
        **({"done": t["id"]} if waiting else {}))
    if waiting and lands:
        return f"{t['id']} is done. {lands} lands it: it has been told. Your files stay yours until then."
    if waiting:
        return (f"{t['id']} is done. Now bring it into the user's checkout: room_land (it lands "
                f"{', '.join(rec['branch'] for _, rec in waiting)}).")
    return f"{t['id']} is done."


def invite_task(room, by, token, text):
    """The task a helper is brought in for, on the plan from the start: its owner is the invite
    until the helper's channel starts and takes it (adopt). Call it holding locked()."""
    items = tasks(room)
    first = text.strip().split("\n", 1)[0]
    first = re.split(r"(?<=[.!?])\s", first, 1)[0]
    n = max([int(t["id"][1:]) for t in items if t["id"][1:].isdigit()] + [0]) + 1
    t = {"id": f"t{n}", "title": first[:80] + ("…" if len(first) > 80 else ""), "done_when": "", "files": [],
         "owner": INVITED + token, "by": by, "status": "open", "note": "", "branch": None,
         "created": time.time(), "updated": time.time()}
    save_tasks(room, items + [t])
    return t["id"]


def adopt(agent_id, room, token):
    """A helper starting: the task it was brought in for is its own now. Call it holding locked()."""
    items = tasks(room)
    for t in items:
        if t.get("owner") == INVITED + token:
            t.update(owner=agent_id, status="doing", updated=time.time())
            save_tasks(room, items)
            return t["id"]
    return None


def claim_tool(agent, args, room):
    paths = [str(p).strip() for p in (args.get("paths") or []) if str(p).strip()][:50]
    with channel.locked():
        if args.get("release"):
            n = release(agent.id, paths or None)
            return f"Let go of {n} claim{'s' if n != 1 else ''}." if n else "You had no claims on those."
        if not paths:
            mine = [c for c in claims() if c["agent"] == agent.id]
            return ("Your claims: " + ", ".join(tilde(c["path"]) for c in mine)) if mine else "You have no claims."
        bad = [p for p in paths if not p.startswith(("/", "~"))]
        if bad:
            raise Refused(f"Give absolute paths (not {bad[0]}).")
        mine = current(tasks(room), agent.id)
        taken = claim(agent.id, room, paths, task=mine["id"] if mine else None)
    got = len(paths) - len(taken)
    out = f"Claimed {got} path{'s' if got != 1 else ''}." if got else "Claimed nothing."
    for p, c in taken:
        t = find(tasks(room), c["task"]) if c.get("task") else None
        out += f" {tilde(p)}: {held(c, t)}."
    return out


def land_tool(agent, args, room):
    live = channel.live_agents()
    lead = channel.lead_of(room, live) if room else None
    whose = channel.safe_name(str(args["agent"])) if args.get("agent") else agent.id
    all_trees = trees()
    if whose not in all_trees:
        waiting = waiting_trees(room, live)
        return (f"{'You have' if whose == agent.id else whose + ' has'} no worktree, so there's nothing to land."
                + (" Waiting to land: " + "; ".join(waiting) + "." if waiting else ""))
    if whose != agent.id:
        owner = next((a for a in live if a["id"] == whose), None)
        if lead != agent.id and (owner or lead):  # a closed agent's work: anyone may land it when no one leads
            raise Refused(f"Only the room's orchestrator lands someone else's work{f' ({lead})' if lead else ''}.")
        if owner and owner["room"] != room:
            raise Refused(f"{whose} isn't in your room.")
    elif lead and lead != agent.id and teamed({"id": agent.id, "room": room}, live):
        raise Refused(f"{lead} is this room's orchestrator, so it lands the room's work. Say your task is done "
                      "(room_task done) and it will land it.")
    repos = all_trees[whose]
    if args.get("repo"):
        want = repo_of(str(args["repo"]))
        repos = {m: r for m, r in repos.items() if want and m == want[0]}
    if len(repos) != 1:
        raise Refused(f"{whose} has worktrees of {len(repos) or 'no'} repositories here: say which with repo"
                      + (f" ({', '.join(tilde(m) for m in all_trees[whose])})." if all_trees[whose] else "."))
    main, rec = next(iter(repos.items()))
    return land(whose, main, rec, room, agent.id)


def waiting_trees(room, live):
    """The worktrees with commits not landed yet, said briefly."""
    ids = {a["id"]: a["room"] for a in live}
    out = []
    for aid, repos in trees().items():
        if aid in ids and ids[aid] != room:
            continue
        for main, rec in repos.items():
            if os.path.isdir(rec["path"]) and ahead(rec):
                out.append(f"{aid}'s {rec['branch']} ({ahead(rec)} commits) into {tilde(main)}"
                           + ("" if aid in ids else f", left by an agent that has closed (room_land agent={aid})"))
    return out


def land(whose, main, rec, room, by):
    """Rebase a worktree's branch onto its base, then fast-forward the base in the main checkout."""
    wt, branch, base = rec["path"], rec["branch"], rec["base"]
    changed = dirty(wt)
    if changed:
        raise Refused(f"{wt} has changes nobody has committed ({', '.join(changed[:5])}). "
                      f"{'Commit them there' if whose == by else f'{whose} commits them'} first, then land.")
    if not ahead(rec):
        return f"{branch} has nothing that {base} doesn't have already: nothing to land."
    rebased = git("rebase", base, cwd=wt)
    if rebased.returncode:
        conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=wt).stdout.split()
        git("rebase", "--abort", cwd=wt)
        raise Refused(f"{branch} doesn't rebase cleanly onto {base}: {', '.join(conflicts) or 'conflicts'}. "
                      f"{'You' if whose == by else whose} fix it in {wt}: git rebase {base}, settle the conflicts, "
                      "git rebase --continue, then land again. Nothing changed in the user's checkout.")
    on = git("symbolic-ref", "--short", "-q", "HEAD", cwd=main).stdout.strip()
    if on != base:
        raise Refused(f"{tilde(main)} is on {on or 'a detached HEAD'} now, not {base}, so landing would put the work "
                      f"on the wrong branch. {branch} is rebased and ready; ask the user (git merge --ff-only {branch}).")
    n = ahead(rec)
    merged = git("merge", "--ff-only", branch, cwd=main)
    if merged.returncode:
        why = (merged.stderr or merged.stdout).strip()
        raise Refused(f"Git wouldn't fast-forward {tilde(main)} to {branch}: {why[-400:]} Nothing was overwritten. "
                      "If it's changes the user hasn't committed, ask them; they're not yours to move.")
    head = git("rev-parse", "--short", "HEAD", cwd=main).stdout.strip()
    with channel.locked():
        items = tasks(room) if room else []
        landed = [t for t in items if t.get("owner") == whose and t["status"] == "done"]
        for t in landed:
            t.update(status="landed", updated=time.time())
        if room:
            save_tasks(room, items)
        release(whose, under=main)  # everything it did in this repository is in the user's checkout now
    names = ", ".join(t["id"] for t in landed)
    text = f"Landed {whose}'s {branch} in {tilde(main)}: {n} commit{'s' if n != 1 else ''}, {base} is at {head} now" \
           + (f" ({names} landed)." if names else ".")
    if room:
        say(room, by, text, to=whose if whose != by else None)
    return text + (" Your worktree stays for more work; it goes when you close." if whose == by else
                   f" {whose}'s worktree stays for more work; it goes when {whose} closes.")

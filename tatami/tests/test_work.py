"""Tests for the room's work (work.py): tasks, claims, worktrees and landing, on throwaway git
repositories with a scratch state folder.

  python3 -m unittest discover -s tatami/tests
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

SCRATCH = tempfile.mkdtemp(prefix="tatami-test-")
os.environ["TATAMI_HOME"] = os.path.join(SCRATCH, "state")
os.environ["TATAMI_WORKTREES"] = os.path.join(SCRATCH, "trees")
os.environ["TATAMI_DESK_DIR"] = os.path.join(SCRATCH, "desk")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hooks  # noqa: E402
import tatami_mcp as channel  # noqa: E402
import work  # noqa: E402


def contents(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sh(*args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Who:
    """What the tools take as the agent calling them."""
    def __init__(self, aid):
        self.id = aid


class Team(unittest.TestCase):
    """A scratch state folder and a one-commit repository, for each test."""

    def setUp(self):
        for d in ("state", "trees"):
            subprocess.run(["rm", "-rf", os.path.join(SCRATCH, d)], check=True)
        for d in (channel.AGENTS, channel.ROOMS, os.path.join(channel.HOME, "status")):
            os.makedirs(d)
        self.repo = os.path.join(SCRATCH, "proj")
        subprocess.run(["rm", "-rf", self.repo], check=True)
        os.makedirs(self.repo)
        sh("git", "init", "-q", "-b", "main", cwd=self.repo)
        sh("git", "config", "user.email", "t@example.com", cwd=self.repo)
        sh("git", "config", "user.name", "Test", cwd=self.repo)
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write("one\ntwo\nthree\n")
        with open(os.path.join(self.repo, ".gitignore"), "w") as f:
            f.write("local.cfg\n")
        sh("git", "add", ".", cwd=self.repo)
        sh("git", "commit", "-q", "-m", "start", cwd=self.repo)
        self.agents = {}

    def agent(self, aid, room=None):
        """A live agent record (this test's own process stands in for it)."""
        rec = {"id": aid, "agent": "claude", "cwd": SCRATCH, "room": room, "pid": os.getpid(),
               "started": channel.proc_start(os.getpid()), "seen": time.time(), "read_upto": {}}
        channel.save(os.path.join(channel.AGENTS, aid + ".json"), rec)
        members = channel.load(channel.MEMBERS, {})
        members[aid] = room
        channel.save(channel.MEMBERS, members)
        return self.me(aid)

    def me(self, aid):
        return next(a for a in channel.live_agents() if a["id"] == aid)

    def lead(self, room, aid):
        channel.save(channel.LEADS_FILE, {room: aid})

    def msgs(self, room):
        return channel.load_jsonl(os.path.join(channel.ROOMS, room + ".jsonl"))

    def commit(self, path, text, msg="change"):
        with open(path, "w") as f:
            f.write(text)
        cwd = os.path.dirname(path)
        sh("git", "add", os.path.basename(path), cwd=cwd)
        sh("git", "commit", "-q", "-m", msg, cwd=cwd)


class Room(Team):
    # ---- the guard ----

    def test_alone_edits_the_checkout(self):
        solo = self.agent("solo")
        self.assertIsNone(work.guard(solo, os.path.join(self.repo, "a.txt")))
        self.assertEqual(work.trees(), {})

    def test_teammates_get_worktrees(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        said = work.guard(rose, os.path.join(self.repo, "a.txt"))
        tree = work.tree_of("rose", self.repo)
        self.assertIsNotNone(tree)
        self.assertIn(tree["path"], said)
        self.assertIn(os.path.join(tree["path"], "a.txt"), said)
        self.assertEqual(tree["branch"], "tatami/rose")
        self.assertEqual(tree["base"], "main")
        self.assertTrue(os.path.isfile(os.path.join(tree["path"], "a.txt")))
        # in its own worktree it may edit, and the file is claimed for it
        self.assertIsNone(work.guard(rose, os.path.join(tree["path"], "a.txt")))
        self.assertEqual([c["path"] for c in work.claims()], [os.path.join(self.repo, "a.txt")])
        # the checkout stays the user's, even once it's on its own again
        self.assertIn("is the user's checkout", work.guard(rose, os.path.join(self.repo, "new.txt")))

    def test_ignored_files_stay_in_the_checkout(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        self.assertIsNone(work.guard(rose, os.path.join(self.repo, "local.cfg")))

    def test_a_teammates_file_is_refused(self):
        sky = self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        work.guard(sky, os.path.join(self.repo, "a.txt"))
        sky_tree = work.tree_of("sky", self.repo)["path"]
        self.assertIsNone(work.guard(sky, os.path.join(sky_tree, "a.txt")))
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        rose_tree = work.tree_of("rose", self.repo)["path"]
        said = work.guard(rose, os.path.join(rose_tree, "a.txt"))
        self.assertIn("isn't yours to edit", said)
        self.assertIn("sky", said)
        # nor may it edit in sky's worktree
        self.assertIn("is sky's worktree", work.guard(rose, os.path.join(sky_tree, "b.txt")))
        # once sky lets go, it can
        with channel.locked():
            work.release("sky")
        self.assertIsNone(work.guard(rose, os.path.join(rose_tree, "a.txt")))

    def test_claims_lapse_when_the_holder_leaves_the_room(self):
        sky = self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        outside = os.path.join(SCRATCH, "notes.md")
        self.assertIsNone(work.guard(sky, outside))
        self.assertIn("isn't yours", work.guard(rose, outside))
        self.agent("sky", "ume")  # dragged to another room
        self.agent("pine", "fuji")  # rose still has a teammate
        self.assertIsNone(work.guard(rose, outside))

    def test_bash_git_in_the_checkout(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        tree = work.tree_of("rose", self.repo)["path"]
        self.assertIn("user's checkout", work.guard_bash(rose, f"cd {self.repo} && git commit -am x"))
        self.assertIn("user's checkout", work.guard_bash(rose, f"git -C {self.repo} add a.txt"))
        self.assertIsNone(work.guard_bash(rose, f"git -C {self.repo} log --oneline"))
        self.assertIsNone(work.guard_bash(rose, f"git -C {tree} commit -am x"))

    # ---- the plan ----

    def test_orchestrator_hands_out_work(self):
        self.agent("lead", "fuji")
        self.agent("sky", "fuji")
        self.agent("rose", "fuji")
        self.lead("fuji", "lead")
        f = os.path.join(self.repo, "a.txt")
        text, err = work.answer(Who("sky"), "room_task", {"action": "add", "title": "x", "owner": "rose"}, "fuji")
        self.assertTrue(err)
        self.assertIn("orchestrator", text)
        text, err = work.answer(Who("lead"), "room_task", {"action": "add", "title": "Fix a", "owner": "rose",
                                                           "done_when": "tests pass", "files": [f]}, "fuji")
        self.assertFalse(err, text)
        last = self.msgs("fuji")[-1]
        self.assertEqual((last["from"], last["to"]), ("lead", "rose"))
        self.assertIn("t1", last["text"])
        # the task's files are rose's now
        sky_tree = (work.guard(self.me("sky"), f), work.tree_of("sky", self.repo)["path"])[1]
        self.assertIn("rose's task t1", work.guard(self.me("sky"), os.path.join(sky_tree, "a.txt")))
        # sky can't take rose's task, rose can
        self.assertTrue(work.answer(Who("sky"), "room_task", {"action": "take", "id": "t1"}, "fuji")[1])
        self.assertFalse(work.answer(Who("rose"), "room_task", {"action": "take", "id": "t1"}, "fuji")[1])
        self.assertEqual(work.find(work.tasks("fuji"), "t1")["status"], "doing")
        self.assertIn("t1 [doing] Fix a", work.plan("fuji"))

    def test_done_then_land_by_the_orchestrator(self):
        self.agent("lead", "fuji")
        rose = self.agent("rose", "fuji")
        self.lead("fuji", "lead")
        f = os.path.join(self.repo, "a.txt")
        work.answer(Who("lead"), "room_task", {"action": "add", "title": "Fix a", "owner": "rose", "files": [f]}, "fuji")
        work.answer(Who("rose"), "room_task", {"action": "take", "id": "t1"}, "fuji")
        work.guard(rose, f)
        tree = work.tree_of("rose", self.repo)["path"]
        with open(os.path.join(tree, "a.txt"), "w") as fh:
            fh.write("one\nTWO\nthree\n")
        text, err = work.answer(Who("rose"), "room_task", {"action": "done", "id": "t1", "note": "changed two"}, "fuji")
        self.assertTrue(err)
        self.assertIn("haven't committed", text)
        sh("git", "commit", "-qam", "two", cwd=tree)
        self.assertTrue(work.answer(Who("rose"), "room_task", {"action": "done", "id": "t1"}, "fuji")[1])  # no note
        text, err = work.answer(Who("rose"), "room_task", {"action": "done", "id": "t1", "note": "changed two"}, "fuji")
        self.assertFalse(err, text)
        self.assertEqual((self.msgs("fuji")[-1]["to"]), "lead")
        # rose doesn't land its own work while there's an orchestrator
        text, err = work.answer(Who("rose"), "room_land", {}, "fuji")
        self.assertTrue(err)
        # the user committed something else meanwhile: landing rebases onto it
        self.commit(os.path.join(self.repo, "b.txt"), "b\n", "user's own")
        text, err = work.answer(Who("lead"), "room_land", {"agent": "rose"}, "fuji")
        self.assertFalse(err, text)
        self.assertEqual(contents(f), "one\nTWO\nthree\n")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "b.txt")))
        self.assertEqual(sh("git", "log", "--format=%s", "-3", cwd=self.repo).split("\n"), ["two", "user's own", "start"])
        self.assertEqual(work.find(work.tasks("fuji"), "t1")["status"], "landed")
        self.assertEqual(work.claims(), [])

    def test_peers_land_their_own(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        tree = work.tree_of("rose", self.repo)["path"]
        self.commit(os.path.join(tree, "c.txt"), "c\n")
        self.assertTrue(work.answer(Who("sky"), "room_land", {"agent": "rose"}, "fuji")[1])
        text, err = work.answer(Who("rose"), "room_land", {}, "fuji")
        self.assertFalse(err, text)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "c.txt")))

    def test_landing_never_overwrites_the_users_changes(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        tree = work.tree_of("rose", self.repo)["path"]
        self.commit(os.path.join(tree, "a.txt"), "one\nROSE\nthree\n")
        with open(os.path.join(self.repo, "a.txt"), "w") as fh:  # the user, typing
            fh.write("one\nmine\nthree\n")
        text, err = work.answer(Who("rose"), "room_land", {}, "fuji")
        self.assertTrue(err)
        self.assertIn("Nothing was overwritten", text)
        self.assertEqual(contents(os.path.join(self.repo, "a.txt")), "one\nmine\nthree\n")

    def test_a_conflict_stays_in_the_worktree(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        tree = work.tree_of("rose", self.repo)["path"]
        self.commit(os.path.join(tree, "a.txt"), "one\nROSE\nthree\n")
        self.commit(os.path.join(self.repo, "a.txt"), "one\nUSER\nthree\n")
        before = sh("git", "rev-parse", "HEAD", cwd=self.repo)
        text, err = work.answer(Who("rose"), "room_land", {}, "fuji")
        self.assertTrue(err)
        self.assertIn("a.txt", text)
        self.assertEqual(sh("git", "rev-parse", "HEAD", cwd=self.repo), before)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=tree), "")  # the rebase was undone

    def test_helpers_take_their_task(self):
        self.agent("sky", "fuji")
        with channel.locked():
            tid = work.invite_task("fuji", "sky", "ab" * 16, "Port the glow. Then tidy up.")
        self.assertIn("a helper that's starting", work.plan("fuji"))
        self.agent("helper", "fuji")
        with channel.locked():
            self.assertEqual(work.adopt("helper", "fuji", "ab" * 16), tid)
        t = work.find(work.tasks("fuji"), tid)
        self.assertEqual((t["owner"], t["status"], t["title"]), ("helper", "doing", "Port the glow."))

    def test_closed_agents_leave_only_waiting_work(self):
        self.agent("sky", "fuji")
        rose = self.agent("rose", "fuji")
        pine = self.agent("pine", "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        work.guard(pine, os.path.join(self.repo, "a.txt"))
        self.commit(os.path.join(work.tree_of("pine", self.repo)["path"], "p.txt"), "p\n")
        work.tidy({"sky"})
        self.assertIsNone(work.tree_of("rose", self.repo))  # nothing in it: gone, branch too
        self.assertNotIn("tatami/rose", sh("git", "branch", cwd=self.repo))
        self.assertIsNotNone(work.tree_of("pine", self.repo))  # a commit to land: kept


class Channel(Team):
    """The channel itself, as Claude Code runs it: the new tools are listed and answer."""

    def test_over_stdio(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.agent("sky", "fuji")
        env = dict(os.environ, TATAMI_ID="rose", TATAMI_ROOM="fuji")
        env.pop("WSL_INTEROP", None)  # no window to look for
        calls = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                 {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                 {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "room_task", "arguments": {"action": "add", "title": "Fix a", "owner": "me"}}},
                 {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "room_members"}}]
        out = subprocess.run([sys.executable, os.path.join(here, "tatami_mcp.py")], env=env, cwd=SCRATCH,
                             input="".join(json.dumps(c) + "\n" for c in calls), capture_output=True, text=True,
                             timeout=30)
        replies = {r["id"]: r for r in map(json.loads, out.stdout.splitlines())}
        self.assertIn("room_task", replies[1]["result"]["instructions"])
        self.assertEqual({t["name"] for t in replies[2]["result"]["tools"]},
                         {"room_post", "room_read", "room_members", "room_invite", "room_task", "room_claim", "room_land"})
        self.assertIn("Added t1", replies[3]["result"]["content"][0]["text"])
        self.assertIn("t1 [doing] Fix a (owner: rose", replies[4]["result"]["content"][0]["text"])


class ModGuard(Team):
    """`tatami mod guard`, as the mod runs it from inside Claude: it finds its agent by process."""

    def test_guard_command(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        other = subprocess.Popen(["sleep", "60"])  # a teammate's process
        self.addCleanup(other.kill)
        channel.save(os.path.join(channel.AGENTS, "sky.json"),
                     {"id": "sky", "agent": "claude", "cwd": SCRATCH, "room": "fuji", "pid": other.pid,
                      "started": channel.proc_start(other.pid), "seen": time.time(), "read_upto": {}})
        self.agent("rose", "fuji")
        channel.save(channel.MEMBERS, {"sky": "fuji", "rose": "fuji"})

        def ask(q):
            out = subprocess.run([sys.executable, os.path.join(here, "mod.py"), "guard"], input=json.dumps(q),
                                 capture_output=True, text=True, timeout=30)
            return json.loads(out.stdout)
        said = ask({"tool": "Edit", "path": os.path.join(self.repo, "a.txt")})
        self.assertIn("worktree of your own", said["deny"])
        tree = work.tree_of("rose", self.repo)["path"]
        self.assertEqual(ask({"tool": "Edit", "path": os.path.join(tree, "a.txt")}), {})
        self.assertIn("user's checkout", ask({"tool": "Bash", "command": f"git -C {self.repo} commit -am x"})["deny"])
        poll = json.loads(subprocess.run([sys.executable, os.path.join(here, "mod.py"), "poll"],
                                         capture_output=True, text=True, timeout=30).stdout)
        self.assertTrue(poll["guarded"])
        self.assertEqual(poll["worktrees"][0]["path"], tree)


class OnePath(unittest.TestCase):
    """Claude's status comes from the mod: the hooks earlier versions put in settings come out."""

    def test_old_settings_hooks_come_out(self):
        settings = os.path.join(SCRATCH, "settings.json")
        mine = {"type": "command", "command": "python3 ~/my-hook.py"}
        ours = {"type": "command", "command": '"$HOME/.local/bin/tatami" hook'}
        with open(settings, "w") as f:
            json.dump({"model": "opus", "hooks": {"Stop": [{"hooks": [ours, mine]}],
                                                  "PostToolUse": [{"hooks": [ours]}]}}, f)
        was, hooks.SETTINGS = hooks.SETTINGS, settings
        try:
            self.assertTrue(hooks.remove_settings_hooks())
            self.assertFalse(hooks.remove_settings_hooks())  # nothing left of ours
        finally:
            hooks.SETTINGS = was
        with open(settings) as f:
            self.assertEqual(json.load(f), {"model": "opus", "hooks": {"Stop": [{"hooks": [mine]}]}})


class StopGate(Team):
    """The status hooks hold up the end of a turn, once, for unfinished business."""

    def stop(self, aid, active=False):
        agent = self.me(aid)
        status = channel.load(os.path.join(channel.HOME, "status", aid + ".json"), {})
        out = hooks.mail({"hook_event_name": "Stop", "stop_hook_active": active}, agent, status)
        channel.save(os.path.join(channel.HOME, "status", aid + ".json"), status)
        return out

    def test_a_task_in_progress(self):
        self.agent("sky", "fuji")
        self.agent("rose", "fuji")
        work.answer(Who("rose"), "room_task", {"action": "add", "title": "Fix a", "owner": "me"}, "fuji")
        out = self.stop("rose")
        self.assertEqual(out["decision"], "block")
        self.assertIn("t1", out["reason"])
        self.assertIsNone(self.stop("rose"))  # once
        work.answer(Who("rose"), "room_task", {"action": "update", "id": "t1", "status": "blocked", "note": "?"}, "fuji")
        self.assertIsNone(self.stop("rose"))

    def test_work_waiting_for_the_orchestrator(self):
        self.agent("lead", "fuji")
        rose = self.agent("rose", "fuji")
        self.lead("fuji", "lead")
        work.answer(Who("lead"), "room_task", {"action": "add", "title": "Fix a", "owner": "rose"}, "fuji")
        work.answer(Who("rose"), "room_task", {"action": "take", "id": "t1"}, "fuji")
        work.guard(rose, os.path.join(self.repo, "a.txt"))
        self.commit(os.path.join(work.tree_of("rose", self.repo)["path"], "a.txt"), "x\n")
        work.answer(Who("rose"), "room_task", {"action": "done", "id": "t1", "note": "x"}, "fuji")
        channel.save(os.path.join(channel.AGENTS, "lead.json"),
                     dict(channel.load(os.path.join(channel.AGENTS, "lead.json"), {}), read_upto={"fuji": time.time()}))
        out = self.stop("lead")
        self.assertEqual(out["decision"], "block")
        self.assertIn("room_land", out["reason"])
        self.assertIsNone(self.stop("lead"))


if __name__ == "__main__":
    unittest.main()

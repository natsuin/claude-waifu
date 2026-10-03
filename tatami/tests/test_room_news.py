"""Tests for what keeps a room's plan in step with who's in it: the desk telling a room who it
brought in, the orchestrator hearing who's on no task and what's done for it to land, and what
agents write never being cut short without them knowing.

  python3 -m unittest discover -s tatami/tests
"""
import json
import os
import subprocess
import sys
import time
import unittest

from test_work import SCRATCH, Team, Who, board, channel, hooks, mod, work


def serve(aid, calls):
    """Run the channel as agent `aid` and make tool calls ({name, arguments}); their answers."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, TATAMI_ID=aid)
    env.pop("WSL_INTEROP", None)  # no window to look for
    rpc = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}]
    rpc += [{"jsonrpc": "2.0", "id": i + 2, "method": "tools/call", "params": c} for i, c in enumerate(calls)]
    out = subprocess.run([sys.executable, os.path.join(here, "tatami_mcp.py")], env=env, cwd=SCRATCH,
                         input="".join(json.dumps(c) + "\n" for c in rpc), capture_output=True, text=True, timeout=30)
    res = {r["id"]: r["result"] for r in map(json.loads, out.stdout.splitlines()) if r["id"] > 1}
    return [(res[i + 2]["content"][0]["text"], res[i + 2].get("isError", False)) for i in range(len(calls))]


class Joined(Team):
    """The user brings an agent into a room on the desk."""

    def setUp(self):
        super().setUp()
        self.agent("wine", "fuji")
        self.agent("rouge", "fuji")
        self.agent("cherry")

    def test_the_orchestrator_hears_and_wakes(self):
        self.lead("fuji", "wine")
        self.assertIsNone(board.change("/api/move", {"agent": "cherry", "room": "fuji"}))
        said = self.msgs("fuji")[-1]
        self.assertEqual((said["from"], said.get("via"), said.get("to")), (channel.USER, "desk", "wine"))
        self.assertIn("I've brought cherry into this room, and it isn't on any task here yet. wine:", said["text"])
        self.assertIn("the user sent you a message", mod.wake(self.me("wine"), "fuji", self.msgs("fuji")))
        self.assertIsNone(mod.wake(self.me("rouge"), "fuji", self.msgs("fuji")))  # it isn't rouge's to act on

    def test_a_team_card_drop_counts_too(self):
        self.lead("fuji", "wine")
        board.change("/api/team", {"agent": "cherry", "with": "rouge"})
        self.assertEqual(self.me("cherry")["room"], "fuji")
        self.assertEqual(self.msgs("fuji")[-1].get("to"), "wine")

    def test_back_with_its_task(self):
        self.lead("fuji", "wine")
        board.change("/api/move", {"agent": "cherry", "room": "fuji"})
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Pane", "owner": "cherry"}, "fuji")
        board.change("/api/move", {"agent": "cherry", "room": None})
        board.change("/api/move", {"agent": "cherry", "room": "fuji"})
        self.assertEqual(self.msgs("fuji")[-1]["text"],
                         "I've brought cherry back into this room. wine: it still owns t1 on the plan.")

    def test_peers_hear_it_without_a_wake(self):
        board.change("/api/move", {"agent": "cherry", "room": "fuji"})
        said = self.msgs("fuji")[-1]
        self.assertNotIn("to", said)
        self.assertEqual(said["text"], "I've brought cherry into this room. It isn't on any task here yet.")
        self.assertIsNone(mod.wake(self.me("wine"), "fuji", self.msgs("fuji")))

    def test_nothing_to_tell(self):
        self.lead("fuji", "wine")
        board.change("/api/move", {"agent": "rouge", "room": "fuji"})  # already there
        self.agent("sky")
        board.change("/api/team", {"agent": "cherry", "with": "sky"})  # a new room, no one else in it
        new = self.me("cherry")["room"]
        self.assertEqual(self.msgs("fuji"), [])
        self.assertEqual(self.msgs(new), [])


class Idle(Team):
    """The orchestrator hears who's on no task while there's work on the plan."""

    def setUp(self):
        super().setUp()
        for aid in ("wine", "rouge", "cherry"):
            self.agent(aid, "fuji")
        self.lead("fuji", "wine")

    def test_named_when_the_work_is_split(self):
        text, err = work.answer(Who("wine"), "room_task", {"action": "add", "title": "Desk", "owner": "rouge"}, "fuji")
        self.assertFalse(err)
        self.assertTrue(text.endswith("\nNot on any task: cherry. Give it a piece of the plan, or tell it to wait."))
        self.assertIn("Not on any task: cherry.", work.answer(Who("wine"), "room_task", {"action": "list"}, "fuji")[0])
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Pane", "owner": "cherry"}, "fuji")
        self.assertNotIn("Not on any task", work.answer(Who("wine"), "room_task", {"action": "list"}, "fuji")[0])

    def test_only_the_orchestrator_and_only_with_work_on(self):
        self.assertNotIn("Not on any task", work.answer(Who("wine"), "room_task", {"action": "list"}, "fuji")[0])
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Desk", "owner": "rouge"}, "fuji")
        self.assertNotIn("Not on any task", work.answer(Who("rouge"), "room_task", {"action": "list"}, "fuji")[0])

    def test_room_members(self):
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Desk", "owner": "rouge"}, "fuji")
        [(text, _)] = serve("wine", [{"name": "room_members"}])
        self.assertTrue(text.endswith("\nNot on any task: cherry. Give it a piece of the plan, or tell it to wait."))


class DoneReachesTheLead(Team):
    """Testing-Room, 2026-10-03: rouge said t4 was done at 00:54, but wine, its orchestrator, had
    been woken 3 times in the half hour before, so nothing woke it and t4 sat unlanded overnight."""

    def setUp(self):
        super().setUp()
        self.agent("wine", "fuji")
        self.agent("sky", "fuji")
        self.rouge = self.agent("rouge", "fuji")

    def finish(self, by="wine"):
        """rouge does t1, handed to it by `by`, and says it's done; wine has used its wake-ups."""
        work.answer(Who(by), "room_task", {"action": "add", "title": "Reorder", "owner": "rouge"}, "fuji")
        work.answer(Who("rouge"), "room_task", {"action": "take", "id": "t1"}, "fuji")
        work.guard(self.rouge, os.path.join(self.repo, "a.txt"))
        self.commit(os.path.join(work.tree_of("rouge", self.repo)["path"], "a.txt"), "x\n")
        now = time.time()
        for aid in ("wine", "sky"):
            channel.save(mod.status_path(self.me(aid)), {"state": "done", "told": now, "woke": [now - 900, now - 600, now - 60]})
        channel.post("fuji", {"ts": time.time(), "from": "rouge", "to": by, "text": "Nearly there."})
        self.assertIsNone(mod.wake(self.me(by), "fuji", self.msgs("fuji")))  # out of wake-ups
        work.answer(Who("rouge"), "room_task", {"action": "done", "id": "t1", "note": "reordered"}, "fuji")

    def test_the_orchestrator_wakes_anyway(self):
        self.lead("fuji", "wine")
        self.finish()
        said = mod.wake(self.me("wine"), "fuji", self.msgs("fuji"))
        self.assertIn("rouge's t1 is done in room 'fuji' and waiting for you to land", said)
        status = channel.load(mod.status_path(self.me("wine")), {})
        self.assertEqual(len(status["woke"]), 3)  # it didn't use up a wake-up
        self.assertIsNone(mod.wake(self.me("wine"), "fuji", self.msgs("fuji")))  # and it's told once

    def test_not_once_its_landed(self):
        self.lead("fuji", "wine")
        self.finish()
        work.answer(Who("wine"), "room_land", {"agent": "rouge"}, "fuji")  # in a turn of its own, say
        self.assertIsNone(mod.wake(self.me("wine"), "fuji", self.msgs("fuji")))

    def test_only_for_whoever_lands_it(self):
        self.finish(by="sky")  # no orchestrator: rouge lands its own, and sky only hears about it
        self.assertEqual(self.msgs("fuji")[-1].get("to"), "sky")
        self.assertIsNone(mod.wake(self.me("sky"), "fuji", self.msgs("fuji")))

    def test_room_read_and_members_lead_with_it(self):
        self.lead("fuji", "wine")
        self.finish()
        [(read, _), (again, _), (members, _)] = serve("wine", [{"name": "room_read"}, {"name": "room_read"},
                                                              {"name": "room_members"}])
        waiting = ("Finished and waiting for you to land: t1 Reorder (rouge's tatami/rouge: "
                   "room_land agent=rouge).")
        self.assertTrue(read.startswith(waiting + "\n\nRoom 'fuji'"), read)
        self.assertEqual(again, f"No new messages in room 'fuji'.\n{waiting}")
        self.assertIn("- t1 [done, waiting to land] Reorder", members)
        self.assertNotIn("Nothing left to do", members)  # what room_members said about Testing-Room's t4
        [(read, _)] = serve("sky", [{"name": "room_read"}])
        self.assertNotIn("waiting for you to land", read)  # it isn't sky's to land

    def test_left_when_they_close(self):
        """What haze found the next day: rouge and wine had both closed, with t4 waiting for no one."""
        self.lead("fuji", "wine")
        self.finish()
        for aid in ("rouge", "wine"):  # their windows close
            os.remove(os.path.join(channel.AGENTS, aid + ".json"))
            with channel.locked():
                work.retire(aid)
        owner = work.find(work.tasks("fuji"), "t1")["owner"]
        self.assertTrue(owner.startswith("rouge."))
        [(read, _)] = serve("sky", [{"name": "room_read"}])  # no orchestrator now: anyone here may land it
        self.assertTrue(read.startswith(f"Finished and waiting for you to land: t1 Reorder ({owner}'s tatami/rouge: "
                                        f"room_land agent={owner})."), read)
        gate = hooks.mail({"hook_event_name": "Stop"}, self.me("sky"), {})
        self.assertIn(f"room_land agent={owner}", gate["reason"])
        text, err = work.answer(Who("sky"), "room_land", {"agent": owner}, "fuji")
        self.assertFalse(err, text)
        self.assertEqual(work.find(work.tasks("fuji"), "t1")["status"], "landed")


class NotCutShort(Team):
    """Too long is refused, with what to do instead; up to the limit, it's kept whole."""

    def setUp(self):
        super().setUp()
        for aid in ("wine", "rouge"):
            self.agent(aid, "fuji")

    def test_done_when(self):
        spec = "Check it with screenshots, then commit on your branch. " * 25  # about 1400 characters
        text, err = work.answer(Who("wine"), "room_task", {"action": "add", "title": "Desk", "owner": "rouge",
                                                            "done_when": spec}, "fuji")
        self.assertFalse(err, text)
        self.assertEqual(work.tasks("fuji")[0]["done_when"], spec.strip())
        self.assertIn(spec.strip() + ".", self.msgs("fuji")[-1]["text"])  # the hand-off has all of it too
        text, err = work.answer(Who("wine"), "room_task", {"action": "add", "title": "Pane", "owner": "rouge",
                                                            "done_when": "x" * 2001}, "fuji")
        self.assertTrue(err)
        self.assertIn("Not added: done_when is 2001 characters, and it can be at most 2000.", text)
        self.assertEqual(len(work.tasks("fuji")), 1)

    def test_title(self):
        text, err = work.answer(Who("wine"), "room_task", {"action": "add", "title": "x" * 201}, "fuji")
        self.assertTrue(err)
        self.assertIn("at most 200", text)

    def test_note_changes_nothing_when_refused(self):
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Desk", "owner": "rouge"}, "fuji")
        text, err = work.answer(Who("rouge"), "room_task", {"action": "update", "id": "t1", "status": "blocked",
                                                             "note": "y" * 2001}, "fuji")
        self.assertTrue(err)
        self.assertEqual(work.tasks("fuji")[0]["status"], "open")
        text, err = work.answer(Who("rouge"), "room_task", {"action": "done", "id": "t1", "note": "y" * 2001}, "fuji")
        self.assertTrue(err)
        self.assertIn("Not done: the note on t1 is 2001 characters", text)

    def test_hand_off_says_where_the_rest_is(self):
        files = [f"/home/someone/a/fairly/long/folder/name/for/a/file/number_{i:02d}.txt" for i in range(50)]
        work.answer(Who("wine"), "room_task", {"action": "add", "title": "Many", "owner": "rouge",
                                               "done_when": "z" * 2000, "files": files}, "fuji")
        said = self.msgs("fuji")[-1]["text"]
        self.assertLessEqual(len(said), channel.MAX_TEXT)
        self.assertTrue(said.endswith("(cut short here: room_task list has all of it)"))

    def test_room_post(self):
        (long, err), (ok, err2) = serve("wine", [{"name": "room_post", "arguments": {"text": "w" * 4001}},
                                                  {"name": "room_post", "arguments": {"text": "w" * 4000}}])
        self.assertTrue(err)
        self.assertIn("Not posted: the message is 4001 characters", long)
        self.assertFalse(err2, ok)
        self.assertEqual([len(m["text"]) for m in self.msgs("fuji")], [4000])


if __name__ == "__main__":
    unittest.main()

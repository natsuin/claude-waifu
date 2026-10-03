"""Tests for what keeps a room's plan in step with who's in it: the desk telling a room who it
brought in, and the orchestrator hearing who's on no task.

  python3 -m unittest discover -s tatami/tests
"""
import json
import os
import subprocess
import sys
import unittest

from test_work import SCRATCH, Team, Who, board, channel, mod, work


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


if __name__ == "__main__":
    unittest.main()

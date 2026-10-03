"""Tests for the app's terminals (term.py): the agent outlives the app, and the app gets its
screen back when it attaches again. A stand-in `claude` echoes what's typed.

  python3 -m unittest discover -s tatami/tests
"""
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERM = os.path.join(HERE, "term.py")


class Terminal(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.mkdtemp(prefix="tatami-term-")
        home, bin_dir = os.path.join(self.scratch, "home"), os.path.join(self.scratch, "bin")
        os.makedirs(home)
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "claude"), "w") as f:
            f.write('#!/bin/sh\necho "agent up in $(pwd) as $TATAMI_SESSION"\nexec cat\n')
        os.chmod(os.path.join(bin_dir, "claude"), 0o755)
        self.env = dict(os.environ, HOME=home, PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        TATAMI_HOME=os.path.join(self.scratch, "state"),
                        TATAMI_DESK_DIR=os.path.join(self.scratch, "desk"))
        self.addCleanup(self.end_holders)

    def end_holders(self):
        """A test that failed half-way mustn't leave a holder behind."""
        terms = os.path.join(self.scratch, "state", "terms")
        for fn in os.listdir(terms) if os.path.isdir(terms) else []:
            if fn.endswith(".json"):
                with open(os.path.join(terms, fn)) as f:
                    try:
                        os.kill(json.load(f)["pid"], 15)
                    except (OSError, ValueError, KeyError):
                        pass

    def attach(self, session):
        return subprocess.Popen([sys.executable, TERM, session, "claude"], env=self.env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read_until(self, proc, text, timeout=15):
        got, end = b"", time.time() + timeout
        while text.encode() not in got:
            left = end - time.time()
            self.assertGreater(left, 0, f"never saw {text!r} in {got[-300:]!r}")
            if select.select([proc.stdout], [], [], left)[0]:
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    self.fail(f"ended before {text!r}: {got[-300:]!r}")
                got += chunk
        return got

    def listed(self):
        out = subprocess.run([sys.executable, TERM, "--list"], env=self.env, capture_output=True, text=True)
        return [json.loads(l) for l in out.stdout.splitlines()]

    def test_the_agent_outlives_the_app(self):
        app = self.attach("app-test1")
        first = self.read_until(app, "as app-test1")
        self.assertIn(b"Starting Claude", first)
        self.assertIn(f"agent up in {os.path.join(self.scratch, 'desk')}".encode(), first)
        app.stdin.write(b"hello there\n")
        app.stdin.flush()
        self.read_until(app, "hello there")
        app.stdin.close()  # the app quits
        app.wait(timeout=10)
        self.assertEqual(self.listed(), [{"session": "app-test1", "kind": "claude"}])

        again = self.attach("app-test1")  # the app is back: the screen so far, then live
        back = self.read_until(again, "hello there")
        self.assertIn(b"agent up", back)
        again.stdin.write(b"\x1b]7373;resize;120;40\x07still here\n")
        again.stdin.flush()
        self.assertNotIn(b"7373", self.read_until(again, "still here"))

        again.stdin.write(b"\x1b]7373;end\x07")  # End in the app
        again.stdin.flush()
        again.wait(timeout=10)
        for _ in range(50):
            if not self.listed():
                break
            time.sleep(0.1)
        self.assertEqual(self.listed(), [])


if __name__ == "__main__":
    unittest.main()

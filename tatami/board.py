#!/usr/bin/env python3
"""Tatami Room board: a web page that shows every running agent as a card. Agents on a team
sit in their team's room; the rest wait on their own along the top. Drag a card into a room
and that agent joins the room's team channel; drop one card onto another and the two of them
get a new room.

It only reads and writes the team channel's plain files in ~/.local/state/tatami. It
can't run commands or reach any terminal. It listens on this PC only (127.0.0.1), and
every request needs the secret token that's in the page's address, so other programs,
other devices and other websites can't use it.

  python3 board.py [--port 7373]    (or run ./tatami, which also opens it in your browser)
"""
import hmac
import json
import os
import re
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import tatami_mcp as channel  # same folder: shares the file layout and helpers

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(channel.HOME, "board.token")
SEEN_FILE = os.path.join(channel.HOME, "board.seen")  # touched while a desk window is open (tatami hold)
WAIFU_CONFIG = os.path.expanduser("~/.config/waifu/config.json")
TINTS = {"red": "#411010", "amber": "#412910", "olive": "#414110", "lime": "#294110",
         "green": "#104110", "jade": "#104129", "teal": "#104141", "sky": "#102941",
         "blue": "#101041", "violet": "#291041", "magenta": "#411041", "rose": "#411029"}


def token():
    os.makedirs(channel.HOME, exist_ok=True)
    if not os.path.exists(TOKEN_FILE):
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(24))
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def girls_hidden():
    """`waifu off` hides every girl for screen sharing, so the board hides them too."""
    return bool(channel.load(channel.WAIFU_STATE, {}).get("off"))


def agents():
    """The running agents, as the page shows them. A room of None means on its own. With the
    hooks on, `status` says whether each one is working, done (your turn) or asking you.
    `unread` counts the room's messages it hasn't read: one waiting for you won't see them
    until you talk to it."""
    hidden, home = girls_hidden(), os.path.expanduser("~")
    rooms = {}
    def unread(rec):
        if not rec["room"]:
            return 0
        if rec["room"] not in rooms:
            rooms[rec["room"]] = channel.load_jsonl(os.path.join(channel.ROOMS, rec["room"] + ".jsonl"))
        return len(channel.unread(rec, rec["room"], rooms[rec["room"]]))
    return [{"id": rec["id"], "agent": rec.get("agent", "claude"), "room": rec["room"],
             "unread": unread(rec), "helper_of": rec.get("invited_by"),
             "color": rec.get("color"), "tint": TINTS.get(rec.get("color") or "", "#2a2233"),
             "folder": "~" if rec.get("cwd") == home else os.path.basename(rec.get("cwd", "")),
             "seen": rec.get("seen", 0), "girl": bool(rec.get("girl")) and not hidden,
             "status": channel.load(os.path.join(channel.HOME, "status", rec["id"] + ".json"), {}).get("state"),
             # its window's handle, found by the agent itself, which the app uses to bring it up
             "hwnd": rec["hwnd"] if isinstance(rec.get("hwnd"), int) else None,
             # set when the agent runs in a terminal inside the Tatami Room app
             "session": rec["session"] if re.fullmatch(r"[a-z0-9-]{1,40}", str(rec.get("session"))) else None}
            for rec in channel.live_agents()]


def state():
    people = agents()
    colors = channel.room_colors(channel.live_rooms(people))  # oldest room first, so rooms stay put
    rooms = []
    for name in colors:
        msgs = channel.load_jsonl(os.path.join(channel.ROOMS, name + ".jsonl"))[-6:]
        rooms.append({"name": name, "color": channel.PALETTE[colors[name]],
                      "members": [a for a in people if a["room"] == name],
                      "recent": [{"from": m["from"], "to": m.get("to"), "text": clip(m["text"]),
                                  "ts": m["ts"]} for m in msgs]})
    return {"rooms": rooms, "alone": [a for a in people if not a["room"]], "now": time.time(), "usage": usage()}


def usage():
    """Your Claude usage (the 5-hour and weekly windows), as the Tatami Room status line last
    saw it. A window whose reset time has passed has started over."""
    limits = channel.load(os.path.join(channel.HOME, "usage.json"), {}).get("rate_limits") or {}
    out = {}
    for key in ("five_hour", "seven_day"):
        w = limits.get(key) or {}
        if isinstance(w.get("used_percentage"), (int, float)):
            over = (w.get("resets_at") or 0) and w["resets_at"] < time.time()
            out[key] = {"used": 0 if over else w["used_percentage"], "resets": None if over else w.get("resets_at")}
    return out


def clip(text, n=280):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def room_name(raw):
    raw = str(raw or "")
    return channel.safe_name(raw) if any(c.isalnum() for c in raw) else None


def known_agent(raw):
    aid = channel.safe_name(str(raw or ""))
    return aid if raw and os.path.isfile(os.path.join(channel.AGENTS, aid + ".json")) else None


def change(path, body):
    """Make one change to the channel's files. Returns (status, error) when it can't.
    Call it holding the channel's lock."""
    if path == "/api/room":
        room = room_name(body.get("room"))
        if not room:
            return 400, "A room name needs at least one letter or number."
        rooms = channel.load(channel.ROOMS_FILE, [])
        if body.get("remove"):  # only empty rooms; their messages stay on disk
            if any(a["room"] == room for a in channel.live_agents()):
                return 409, "Move its agents out first."
            channel.save(channel.ROOMS_FILE, [r for r in rooms if r != room])
        elif room not in rooms:
            channel.save(channel.ROOMS_FILE, rooms + [room])
        return None
    agent = known_agent(body.get("agent"))
    if not agent:
        return 404, "No agent with that id."
    members = channel.load(channel.MEMBERS, {})
    if path == "/api/move":  # into a room, or with no room: on its own
        room = room_name(body.get("room"))
        if body.get("room") and not room:
            return 400, "A room name needs at least one letter or number."
        members[agent] = room
    else:  # /api/team: one card dropped onto another
        other = known_agent(body.get("with"))
        if not other or other == agent:
            return 404, "No agent with that id."
        people = channel.live_agents()
        room = next((a["room"] for a in people if a["id"] == other), None)
        if not room:  # the other one was on its own too: a new room for the two of them
            room = channel.fresh_room(channel.live_rooms(people))
            members[other] = room
        members[agent] = room
    channel.save(channel.MEMBERS, members)
    return None


def looked_at():
    """Note that a desk window is open. WSL stops a distro soon after its last terminal
    closes, so `tatami hold` keeps it up for as long as this keeps being touched."""
    try:
        if time.time() - os.path.getmtime(SEEN_FILE) < 10:
            return
    except OSError:
        pass
    with open(SEEN_FILE, "w"):
        pass


def publish(url):
    """Leave the desk's address where the Windows shortcuts can read it (next to waifu's
    launcher scripts), so the Tatami Room shortcut can open it."""
    launcher = channel.load(WAIFU_CONFIG, {}).get("launcher_dir")
    if launcher and os.path.isdir(launcher):
        with open(os.path.join(launcher, "board.url"), "w") as f:
            f.write(url + "\r\n")


def girl_file(agent_id):
    """The dot-art girl for an agent's Claude Waifu window, looked up by id only."""
    rec = channel.load(os.path.join(channel.AGENTS, channel.safe_name(agent_id) + ".json"), {})
    pool = channel.load(WAIFU_CONFIG, {}).get("pool")
    if not rec.get("girl") or not pool or girls_hidden():
        return None
    path = os.path.join(pool, "dots", os.path.basename(rec["girl"]).rsplit(".", 1)[0] + ".png")
    return path if os.path.isfile(path) else None


class Board(BaseHTTPRequestHandler):
    server_version = "TatamiRoom/0.2"

    def log_message(self, *args):  # keep the terminal quiet
        pass

    def allowed(self):
        """Only this PC, only our own page, only with the token."""
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False  # blocks DNS-rebinding tricks from other websites
        given = parse_qs(urlparse(self.path).query).get("token", [""])[0] or self.headers.get("X-Tatami-Token", "")
        return hmac.compare_digest(given.encode(), self.server.token.encode())

    def send(self, code, body, kind="application/json", nonce=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if nonce:  # the page: only its own script and style run, and it only talks to this server
            self.send_header("Content-Security-Policy",
                             f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                             "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                             "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        if path == "/":
            nonce = secrets.token_urlsafe(16)
            with open(os.path.join(HERE, "board.html"), encoding="utf-8") as f:
                page = f.read().replace("__TOKEN__", self.server.token).replace("__NONCE__", nonce)
            return self.send(200, page.encode(), "text/html; charset=utf-8", nonce)
        if path == "/api/state":
            looked_at()
            return self.send(200, state())
        if path == "/api/events":
            return self.events()
        if path.startswith("/girl/"):
            f = girl_file(path[len("/girl/"):])
            if f:
                with open(f, "rb") as fh:
                    return self.send(200, fh.read(), "image/png")
        return self.send(404, {"error": "not found"})

    def events(self):
        """Server-sent events: the desk's state each time it changes, so the page and the app hear
        about a move or a new agent straight away instead of asking every few seconds."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        last, sent = None, time.time()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            while True:
                looked_at()  # a desk is open, which keeps WSL up (tatami hold)
                s = state()
                now = json.dumps({k: v for k, v in s.items() if k != "now"}, sort_keys=True)
                if now != last:
                    last, sent = now, time.time()
                    self.wfile.write(b"data: " + json.dumps(s).encode() + b"\n\n")
                    self.wfile.flush()
                elif time.time() - sent > 15:  # now and then, to notice a reader that has gone
                    sent = time.time()
                    self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                time.sleep(0.4)
        except OSError:  # the page or the app went away
            return

    def do_POST(self):
        origin = self.headers.get("Origin")
        port = self.server.server_address[1]
        if not self.allowed() or origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self.send(403, {"error": "forbidden"})
        length = self.headers.get("Content-Length") or "0"
        if not length.isdigit() or int(length) > 10_000:
            return self.send(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(int(length)) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.send(400, {"error": "bad json"})
        path = urlparse(self.path).path
        if path not in ("/api/room", "/api/move", "/api/team"):
            return self.send(404, {"error": "not found"})
        with channel.locked():  # the agents write these files too
            failed = change(path, body)
        if failed:
            return self.send(failed[0], {"error": failed[1]})
        return self.send(200, state())


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 7373
    for d in (channel.ROOMS, channel.AGENTS):
        os.makedirs(d, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Board)
    server.token = token()
    url = f"http://127.0.0.1:{port}/?token={server.token}"
    publish(url)
    print(f"Tatami Room: {url}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

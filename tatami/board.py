#!/usr/bin/env python3
"""Tatami Room board: a web page that shows every running agent as a mat. Agents on a team
sit in their team's room; the rest wait on their own along the top. Drag a mat into a room
and that agent joins the room's team channel; drop one mat onto another and the two of them
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
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import tatami_mcp as channel  # same folder: shares the file layout and helpers

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(channel.HOME, "board.token")
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
    """The running agents, as the page shows them. A room of None means on its own."""
    hidden, home = girls_hidden(), os.path.expanduser("~")
    return [{"id": rec["id"], "agent": rec.get("agent", "claude"), "room": rec["room"],
             "color": rec.get("color"), "tint": TINTS.get(rec.get("color") or "", "#2a2233"),
             "folder": "~" if rec.get("cwd") == home else os.path.basename(rec.get("cwd", "")),
             "seen": rec.get("seen", 0), "girl": bool(rec.get("girl")) and not hidden}
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
    return {"rooms": rooms, "alone": [a for a in people if not a["room"]], "now": time.time()}


def clip(text, n=280):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def room_name(raw):
    raw = str(raw or "")
    return channel.safe_name(raw) if any(c.isalnum() for c in raw) else None


def known_agent(raw):
    aid = channel.safe_name(str(raw or ""))
    return aid if raw and os.path.isfile(os.path.join(channel.AGENTS, aid + ".json")) else None


def fresh_room(live):
    """A name for a new team, the way a ryokan names its rooms: a flower or plant, in the first
    colour no live room has. A name used before starts over: its old messages move to rooms/old.
    Call it holding the channel's lock."""
    used = set(channel.assign_colors(live).values())
    free = [c for c in channel.PALETTE if c not in used] or list(channel.PALETTE)
    names = [n for c in free for n in channel.FLOWERS[c]]
    name, n = next((x for x in names if x not in live), None), 2
    while name is None:  # every name is taken: number them
        name = next((f"{x}-{n}" for x in names if f"{x}-{n}" not in live), None)
        n += 1
    old = os.path.join(channel.ROOMS, name + ".jsonl")
    if os.path.exists(old):
        os.makedirs(os.path.join(channel.ROOMS, "old"), exist_ok=True)
        os.replace(old, os.path.join(channel.ROOMS, "old", f"{name}-{int(time.time())}.jsonl"))
    return name


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
                return 409, "Move its mats out first."
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
    else:  # /api/team: one mat dropped onto another
        other = known_agent(body.get("with"))
        if not other or other == agent:
            return 404, "No agent with that id."
        people = channel.live_agents()
        room = next((a["room"] for a in people if a["id"] == other), None)
        if not room:  # the other one was on its own too: a new room for the two of them
            room = fresh_room(channel.live_rooms(people))
            members[other] = room
        members[agent] = room
    channel.save(channel.MEMBERS, members)
    return None


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
            return self.send(200, state())
        if path.startswith("/girl/"):
            f = girl_file(path[len("/girl/"):])
            if f:
                with open(f, "rb") as fh:
                    return self.send(200, fh.read(), "image/png")
        return self.send(404, {"error": "not found"})

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
    print(f"Tatami Room: http://127.0.0.1:{port}/?token={server.token}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

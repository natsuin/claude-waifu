#!/usr/bin/env python3
"""Tatami Room board: a web page that shows every running agent as a mat, grouped into
rooms. Drag a mat into another room and that agent joins that room's team channel.

It only reads and writes the team channel's plain files in ~/.local/state/tatami. It
can't run commands or reach any terminal. It listens on this PC only (127.0.0.1), and
every request needs the secret token that's in the page's address, so other programs,
other devices and other websites can't use it.

  python3 board.py [--port 7373]    (or run ./tatami, which also opens it in your browser)
"""
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import tatami_mcp as channel  # same folder: shares the file layout and helpers

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(channel.HOME, "board.token")
ROOMS_FILE = os.path.join(channel.HOME, "rooms.json")  # rooms made on the board, even when empty
WAIFU_CONFIG = os.path.expanduser("~/.config/waifu/config.json")
TINTS = {"red": "#411010", "amber": "#412910", "olive": "#414110", "lime": "#294110",
         "green": "#104110", "jade": "#104129", "teal": "#104141", "sky": "#102941",
         "blue": "#101041", "violet": "#291041", "magenta": "#411041", "rose": "#411029"}
ROOM_COLORS = ["#ff85c0", "#c3a6ff", "#7ee8b5", "#8ecbff", "#ffc38a", "#ff9ed2", "#8ef0e6", "#ffe08a"]
LOCK = threading.Lock()  # the board's own changes to members.json and rooms.json, one at a time


def token():
    os.makedirs(channel.HOME, exist_ok=True)
    if not os.path.exists(TOKEN_FILE):
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(24))
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def room_color(name):
    return ROOM_COLORS[int(hashlib.sha1(name.encode()).hexdigest(), 16) % len(ROOM_COLORS)]


def girls_hidden():
    """`waifu off` hides every girl for screen sharing, so the board hides them too."""
    return bool(channel.load(channel.WAIFU_STATE, {}).get("off"))


def agents():
    out, members, hidden = [], channel.load(channel.MEMBERS, {}), girls_hidden()
    for fn in sorted(os.listdir(channel.AGENTS)) if os.path.isdir(channel.AGENTS) else []:
        rec = channel.load(os.path.join(channel.AGENTS, fn), {})
        if rec.get("id") and channel.alive(rec):
            out.append({"id": rec["id"], "agent": rec.get("agent", "claude"), "room": channel.room_of(rec, members),
                        "color": rec.get("color"), "tint": TINTS.get(rec.get("color") or "", "#2a2233"),
                        "folder": os.path.basename(rec.get("cwd", "")), "seen": rec.get("seen", 0),
                        "girl": bool(rec.get("girl")) and not hidden})
    return out


def state():
    people = agents()
    names = list(dict.fromkeys(channel.load(ROOMS_FILE, []) + [a["room"] for a in people]))
    rooms = []
    for name in names:
        msgs = channel.load_jsonl(os.path.join(channel.ROOMS, name + ".jsonl"))[-6:]
        rooms.append({"name": name, "color": room_color(name),
                      "members": [a for a in people if a["room"] == name],
                      "recent": [{"from": m["from"], "to": m.get("to"), "text": clip(m["text"]),
                                  "ts": m["ts"]} for m in msgs]})
    return {"rooms": rooms, "now": time.time()}


def clip(text, n=280):
    return text if len(text) <= n else text[:n - 1].rstrip() + "\u2026"


def girl_file(agent_id):
    """The dot-art girl for an agent's Claude Waifu window, looked up by id only."""
    rec = channel.load(os.path.join(channel.AGENTS, channel.safe_name(agent_id) + ".json"), {})
    pool = channel.load(WAIFU_CONFIG, {}).get("pool")
    if not rec.get("girl") or not pool or girls_hidden():
        return None
    path = os.path.join(pool, "dots", os.path.basename(rec["girl"]).rsplit(".", 1)[0] + ".png")
    return path if os.path.isfile(path) else None


class Board(BaseHTTPRequestHandler):
    server_version = "TatamiRoom/0.1"

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
        raw = str(body.get("room") or "")
        room = channel.safe_name(raw) if any(c.isalnum() for c in raw) else None
        if path not in ("/api/room", "/api/move"):
            return self.send(404, {"error": "not found"})
        if not room:
            return self.send(400, {"error": "A room name needs at least one letter or number."})
        with LOCK:
            rooms = channel.load(ROOMS_FILE, [])
            if path == "/api/room" and body.get("remove"):  # only empty rooms; their messages stay on disk
                if any(a["room"] == room for a in agents()):
                    return self.send(409, {"error": "Move its mats out first."})
                channel.save(ROOMS_FILE, [r for r in rooms if r != room])
                return self.send(200, state())
            if path == "/api/move":
                agent = channel.safe_name(str(body.get("agent") or ""))
                if not os.path.isfile(os.path.join(channel.AGENTS, agent + ".json")):
                    return self.send(404, {"error": "No agent with that id."})
                members = channel.load(channel.MEMBERS, {})
                members[agent] = room
                channel.save(channel.MEMBERS, members)
            if room not in rooms:
                channel.save(ROOMS_FILE, rooms + [room])
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

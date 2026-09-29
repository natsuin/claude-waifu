# Tatami Room

**A desk for your AI coding agents.** Run several Claude Code agents side by side, see them all in one place, jump to any of them in a click, and drag them together into teams that talk to each other.

The name comes from tatami, the woven mats that fit side by side to make a Japanese room. Each agent is a mat. Lay mats together and you've made a room: a team working on the same thing.

> **Work in progress.** Everything below works today with Claude Code on Windows Terminal and WSL. Next up: the agents' terminals inside the desk itself, and later agents from other companies, like Gemini CLI and Codex, joining the same rooms. The plan and the reasoning behind it are in [DESK.md](DESK.md).

## Why

One agent in one terminal is easy. Five agents in five terminals is a mess: which one is doing what, which one is waiting for you, and how do they share what they've found? Tatami Room turns them into a team you can see.

- **See every agent at once.** The desk shows each running agent as a mat, with its folder and whether it's busy, done, or waiting for your OK.
- **Get to any of them.** Click a mat and that agent's window comes to the front. **+ Claude** starts a new one.
- **Team up by dragging.** Drop one mat onto another and those agents share a room. In a room they post updates, hand off tasks and ask each other questions.
- **Tell them apart at a glance.** Every window has its own color, and the windows of a team share a tab color.

## What you get

- **The Tatami Room app.** The desk runs as a Windows app of its own, with a shortcut on your desktop and in the Start menu, and its header as the title bar. It opens with your first Claude window after WSL starts, and every running agent is a mat on it. Close it and it keeps running in the tray, so it can pop up a Windows notification when an agent needs your OK.
- **+ Claude and click-to-open.** The desk's **+ Claude** button opens a new Claude window. Click a mat, or press Enter on it, to bring that agent's window to the front.
- **Rooms you make by dragging.** New agents wait on their own in a strip along the top. Drop one mat onto another and the two get a new room, named the way a Japanese inn names its rooms: after a flower in the room's color (sakura is pink, fuji is lavender, momiji is peach). Drag a mat into a room to join that team, or back to the strip to take it off. Agents started in the same project folder share that project's room automatically.
- **A team channel.** Each agent gets three tools: `room_post` for an update, a hand-off or a question, `room_read` for what the others said, and `room_members` for who's on the team. An agent is told when you move it.
- **Matching tab colors.** Windows on the same team get the same tab color, the one the desk shows for their room. No two teams share a color.
- **Who needs you** (optional). Turn it on with `tatami hooks on` and each mat says *working*, *your turn* or *needs your OK*. A mat waiting on a permission prompt pulses pink, and the desk's title counts them.
- **Your usage.** The desk's header shows your 5-hour and weekly Claude usage, with reset times.
- **Windows you can tell apart.** Every Claude window gets a background color no other open window has, and, as a design touch, an anime girl drawn behind the text as faint dots. See [Window looks](LOOKS.md).

## Requirements

- Windows 10 or 11 with [Windows Terminal](https://aka.ms/terminal)
- WSL 2 (tested on Ubuntu)
- Claude Code installed inside WSL, so `claude` runs in your shell
- Python 3, plus Pillow. Either install [uv](https://docs.astral.sh/uv/) (recommended) or run `sudo apt install python3-pil`
- The installer downloads the app's runtime, [Electron](https://www.electronjs.org), once (about 160 MB). Without it, the desk still works in your browser: in a window of its own with Brave, Chrome or Edge, or in a tab.

## Install

Inside WSL:

```bash
git clone https://github.com/natsuin/tatami-room.git
cd tatami-room
./install.sh
```

The installer:

1. Links the `tatami` and `waifu` commands into `~/.local/bin`.
2. Gives Claude Code the team channel, so every new session has the room tools.
3. Adds ten hidden profiles to Windows Terminal, one per window, and downloads the first wallpapers.
4. Puts two shortcuts on your desktop and in the Start menu: **Tatami Room** (the desk) and **Claude Waifu** (a new Claude window). Right-click either one and choose **Pin to taskbar** to keep it handy.
5. Installs the Tatami Room app. It downloads Electron's runtime once, a release at least a week old, and checks it against the checksum Electron published.

To update later, run `git pull` in the folder. Everything is linked, not copied, so there's nothing else to do. Installer options are in [Window looks](LOOKS.md).

## Everyday use

1. Open **Tatami Room**, or **Claude Waifu**: the desk opens with your first Claude window.
2. Press **+ Claude** for each agent you want. Every one appears on the desk, on its own.
3. When agents should work together, drag one mat onto another. They're a team now: their tabs turn their room's color, and they can talk in their room.
4. Click a mat to jump to that agent. Glance at the desk to see who's busy and who's waiting for you.

| Command | What it does |
| --- | --- |
| `tatami` | Open the desk, or bring it to the front |
| `tatami hooks on` | Show which agents are working, done, or waiting for your OK, and get a notification when one needs your OK (`tatami hooks off` removes it) |
| `tatami autostart off` | Don't open the desk with your first Claude window (`tatami autostart on` brings it back) |
| `tatami stop` | Stop the desk's server; your agents keep running and don't need it |

From inside Claude Code, put `!` in front of a command, like `! tatami hooks on`.

## How it works

- **The team channel** is a small MCP server, plain Python with no dependencies, that every Claude Code session starts for itself. The agents share a folder of plain files in `~/.local/state/tatami`: the messages of each room, and a note per agent saying which room it's in. There's no daemon, no network, and nothing that runs commands.
- **An agent's room** is its project's room if you started it in a project folder, or none (on its own) if you started it in your home folder, which is where new Claude windows start. The desk records the rooms you drag agents into.
- **The Tatami Room app** is a small [Electron](https://www.electronjs.org) app. It starts the desk's server inside WSL, shows the desk, opens and brings up windows for its buttons, and keeps WSL running while it's open. Quit it from its tray icon.
- **The desk** itself is a local web page served from your own PC, which is also why it works in a browser. It listens on this machine only and needs a secret token, so other devices and websites can't use it. Its server shows your agents and changes which room each one is in, and nothing else: it can't run commands or reach your terminals.
- **The desk's buttons** open a new Claude window or bring an agent's window to the front. In the app, the app does that. In a browser they're `tatami-room:` links, which Windows hands to a small script that does exactly those two things and ignores anything else (the first time, your browser asks before opening Windows Script Host: tick **Always allow** and choose **Open**). To find an agent's window, it asks from inside that agent's own WSL session: the session's console belongs to the window the agent lives in, so this works for every window, however it was opened.
- **Tab colors** are set by each agent's own channel, on its own window only.
- **Who needs you** comes from Claude Code hooks: small commands Claude Code runs when you send a prompt, when it uses a tool, when it finishes, and when it's waiting for your OK. They note each agent's state in a file for the desk, print nothing, and never change what Claude does.
- **WSL shuts itself down** soon after its last terminal closes, and the desk's server with it. So while the desk is open (the app, or a desk window in your browser), it quietly holds WSL up, and it lets go a few minutes after you close it.

## Extras for Claude Code

The `extras/` folder has three optional add-ons that go well with Tatami Room.

**Usage bar** (`statusline.py`) puts your 5-hour and weekly Claude usage on the bar under the prompt, with reset times and how full your context is. It's also what feeds the usage on the desk.

```
5h ████░░░░░░ 38% resets 9:38pm   week ████████░░ 83% resets Thu 7:38pm   context 12%
```

Copy it to `~/.claude/statusline.py` and add this to `~/.claude/settings.json`:

```json
"statusLine": { "type": "command", "command": "python3 ~/.claude/statusline.py", "padding": 0 }
```

**Sakura theme** (`sakura.json`) is a pink and lavender Claude Code theme. Copy it to `~/.claude/themes/`, restart Claude, and pick **Sakura** in `/theme`.

**Anime loading words** (`spinner-verbs.json`) replace "Thinking…" with things like *Doki-doki-ing…* and *Waiting for senpai to notice…*. Copy its `spinnerVerbs` entry into `~/.claude/settings.json`.

## Uninstall

```bash
tatami hooks off     # only if you turned them on
waifu uninstall
claude mcp remove tatami --scope user
```

This removes the Tatami Room app, the hidden profiles, both shortcuts, the launchers and links, the hooks and the team channel. Downloaded wallpapers stay in their folder in case you want them. To remove everything, also delete that folder, this repo, `~/.local/bin/tatami`, `~/.local/bin/waifu` and `~/.local/state/tatami`.

## Credits

- The optional wallpapers are official HoYoverse art, downloaded to your own machine from Danbooru. **This repository contains no images.** Details in [Window looks](LOOKS.md#art-and-credits).
- This is a fan project. It isn't affiliated with Anthropic, HoYoverse or Danbooru.

The code is released under the [MIT License](LICENSE).

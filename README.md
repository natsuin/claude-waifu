# Tatami Room

**A desk for your AI coding agents.** Run several Claude Code agents side by side, see them all in one place, jump to any of them in a click, and drag them together into teams that talk to each other.

The name comes from tatami, the woven mats that fit side by side to make a Japanese room. Lay agents side by side and you've made a room: a team working on the same thing.

> **Work in progress.** Everything below works today with Claude Code on Windows Terminal and WSL. Later: agents from other companies, like Gemini CLI and Codex, joining the same rooms. The plan and the reasoning behind it are in [DESK.md](DESK.md).

## Why

One agent in one terminal is easy. Five agents in five terminals is a mess: which one is doing what, which one is waiting for you, and how do they share what they've found? Tatami Room turns them into a team you can see.

- **See every agent at once.** The desk shows each running agent as a card that looks like its window, named after its window's color (*Dusk*, *Matcha*, *Cherry*), with what kind of agent it is (Claude, Gemini, Codex) and, for Claude, the model it's on (*Opus 5.5*, *Sonnet 5.5*) and its effort (*xhigh*, with five little bars from *low* to *max*), a few words on what it's working on (its session's title, which `/rename` changes), its folder, and whether it's busy, done, or waiting for your OK.
- **Get to any of them.** **+ Claude** starts Claude in a terminal right inside the app (and **+ Gemini** starts Gemini, when it's installed), and clicking a card brings that agent up.
- **Team up by dragging.** Drop one card onto another and those agents share a room. In a room they post updates, hand off tasks and ask each other questions.
- **Tell them apart at a glance.** Every window has its own color, and the windows of a team share a tab color.

## What you get

- **The Tatami Room app.** The desk runs as a Windows app of its own, with a shortcut on your desktop and in the Start menu, and its header as the title bar. It opens with your first Claude window after WSL starts, and every running agent is a mat on it. It pops up a Windows notification when an agent needs your OK. Closing it quits, unless Claude is running in its terminals: then it asks, and they can keep running in the tray.
- **Claude inside the app.** **+ Claude** starts Claude in a terminal of the app's own, in a panel beside the desk, drawn over its own girl and color like a Claude Waifu window. Click its card to bring it back, **Hide** it while Claude keeps working, **End** it when you're done, and drag the panel's edge to resize it. **Ctrl+`** switches between the desk and the last terminal.
- **Other kinds of agent.** Next to **+ Claude**, the app offers a button for each other agent CLI it finds installed: **+ Gemini** (the `gemini` or `agy` command), **+ Codex**. Each starts in a terminal of the app's own with its own girl and color, just like Claude. To add another one, give it an entry in [`tatami/kinds.json`](tatami/kinds.json): its name, the commands that start it, and its maker's color and mark. The agent also needs the Tatami Room channel as an MCP server in its own settings (`tatami mcp` as the command), the way Claude Code has it.
- **Click-to-open for your other windows.** Agents in Windows Terminal windows (the **Claude Waifu** shortcut, or **+ Claude in a Terminal window** in the tray menu) are on the desk too: click a card, or press Enter on it, and that window comes to the front.
- **Rooms you make by dragging.** New agents wait on their own in a strip along the top. Drop one card onto another and the two get a new room, named the way a Japanese inn names its rooms: after a flower in the room's color (sakura is pink, fuji is lavender, momiji is peach). Drag a mat into a room to join that team, or back to the strip to take it off. Agents started in the same project folder share that project's room automatically.
- **A team channel.** Each agent gets four tools: `room_post` for an update, a hand-off or a question, `room_read` for what the others said, `room_members` for who's on the team, and `room_invite` to bring in a helper. An agent is told when you move it. Agents see who has read their messages, so silence isn't taken for a yes, and their instructions cover the basics of working together: offer a concrete piece, hand work to whoever offers, and say which files you'll touch.
- **An orchestrator, if you want one.** A room with two or more agents has an **Orchestrator** picker in its header. Pick one and it owns the overall plan: it splits the work into pieces, hands each to a teammate by name, keeps track of who's on what, and tells you when it's all done. The others take their work from it and report back. The room hears it from you, its card wears a gold *Orchestrator* chip, and `room_members` and `/room` mark it. Pick **No one** and they're peers again. An orchestrator you drag out of the room stops being one.
- **Helpers.** Ask an agent to get help and it can bring a helper into its room: a new Claude window, with its own girl and color, that starts in the same folder with the piece of work it was handed and reports back in the room. Unlike a hidden subagent, you see the helper on the desk (marked *helper of* its agent) and can talk to it. Each agent can have two at a time, and helpers can't bring in more.
- **Matching tab colors.** Windows on the same team get the same tab color, the one the desk shows for their room. No two teams share a color.
- **Who needs you** (optional). Turn it on with `tatami hooks on` and each card says *working*, *your turn* or *needs your OK*. A card whose turn is over glows softly until you click it to bring it up, and one waiting on a permission prompt glows red and is counted in the desk's title. The hooks also tell a busy agent when room messages arrive, so it doesn't miss its team while it works.
- **Tatami Room inside Claude** (optional). Turn it on with `tatami mod on` and every Claude window you open carries a bit of the desk: its name tag on the status line ("dusk · Firefly · ajisai"), a line above the prompt when room messages are waiting, and `/room`, a pane with the team, what each one is doing, how far each has read, and a line to post as yourself (`/room hello` posts straight away, `@dusk` sends to one agent). It also does what `tatami hooks on` does without touching Claude Code's settings, plays a soft chime when the window needs your OK, and can wake an idle agent when a teammate messages it (off by default; at most 3 times in 30 minutes). The window glows like its desk card: when Claude finishes, a "Your turn" box above the prompt breathes in sky blue for half a minute, and a tool waiting for your OK gets a red frame that pulses until you answer. All three switches are in `/config`.
- **Unread badges.** A badge on an agent's card counts the room messages it hasn't read. An agent waiting for you can't read anything until you talk to it, so with the hooks on its badge glows pink.
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

To update later, run `git pull` in the folder. Everything is linked, not copied, so there's nothing else to do: an open desk loads its new page by itself, and **F5** in the app loads it again by hand without touching its terminals. Installer options are in [Window looks](LOOKS.md).

## Everyday use

1. Open **Tatami Room**, or **Claude Waifu**: the desk opens with your first Claude window.
2. Press **+ Claude** for each agent you want. Every one appears on the desk, on its own, and its terminal opens beside the desk. The first time, Claude asks whether you trust `~/desk`, the folder the app's terminals start in: say yes once, and Claude Code remembers it for that folder.
3. When agents should work together, drag one card onto another. They're a team now: their tabs turn their room's color, and they can talk in their room.
4. Click a card to jump to that agent. Glance at the desk to see who's busy and who's waiting for you.

| Command | What it does |
| --- | --- |
| `tatami` | Open the desk, or bring it to the front |
| `tatami hooks on` | Show which agents are working, done, or waiting for your OK, get a notification when one needs your OK, and let busy agents hear about room messages (`tatami hooks off` removes it) |
| `tatami hooks gemini on` | The same for Gemini (Antigravity's `agy`) alone, for when the mod does Claude's part: its card says *working* and *your turn*, and it hears about room messages. Gemini has no event for asking your OK, so it says *working* while it asks (`tatami hooks gemini off` removes it) |
| `tatami mod on` | Bring the room into every Claude window you open: name tag, room mail above the prompt, `/room`, who-needs-you, a chime, glows for your turn and your OK (`tatami mod off` removes it) |
| `tatami autostart off` | Don't open the desk with your first Claude window (`tatami autostart on` brings it back) |
| `tatami stop` | Stop the desk's server; your agents keep running and don't need it |

From inside Claude Code, put `!` in front of a command, like `! tatami hooks on`.

## How it works

- **The team channel** is a small MCP server, plain Python with no dependencies, that every Claude Code session starts for itself. The agents share a folder of plain files in `~/.local/state/tatami`: the messages of each room, and a note per agent saying which room it's in. There's no daemon and no network. The one thing it starts is a helper's window, when an agent uses `room_invite`: the task waits in a file, and the window runs `tatami helper` with nothing but that file's random name, which hands the task to Claude as its first prompt.
- **An agent's room** is its project's room if you started it in a project folder, or none (on its own) if you started it in your home folder, which is where new Claude windows start. The desk records the rooms you drag agents into.
- **The app's terminals** run Claude in a pseudo-terminal inside WSL (`tatami term`) and relay it to the app, which draws it with [xterm.js](https://xtermjs.org). They start in `~/desk` rather than your home folder, so Claude Code's folder check is answered once instead of in every session, and they end when you quit the app (it asks first).
- **The Tatami Room app** is a small [Electron](https://www.electronjs.org) app. It starts the desk's server inside WSL, shows the desk, opens and brings up windows for its buttons, and keeps WSL running while it's open. Quit it from its tray icon.
- **The desk** itself is a local web page served from your own PC, which is also why it works in a browser. It listens on this machine only and needs a secret token, so other devices and websites can't use it. Its server shows your agents and changes which room each one is in, and nothing else: it can't run commands or reach your terminals.
- **The desk's buttons** open a new Claude window or bring an agent's window to the front. In the app, the app does that. In a browser they're `tatami-room:` links, which Windows hands to a small script that does exactly those two things and ignores anything else (the first time, your browser asks before opening Windows Script Host: tick **Always allow** and choose **Open**). To find an agent's window, it asks from inside that agent's own WSL session: the session's console belongs to the window the agent lives in, so this works for every window, however it was opened.
- **Tab colors** are set by each agent's own channel, on its own window only.
- **Models and summaries** come from Claude Code's own files: the desk looks up each Claude agent's session in `~/.claude/sessions` and reads its model, effort and title from the session's transcript, only the part added since it last looked. The model shows from your first prompt, the effort from Claude's first reply, and both change as soon as you use `/model` or `/effort`.
- **Who needs you** comes from Claude Code hooks: small commands Claude Code runs when you send a prompt, when it uses a tool, when it finishes, and when it's waiting for your OK. They note each agent's state in a file for the desk. The only thing they ever tell Claude is that room messages arrived: once per message, as a short note, and, if a message was addressed to it, a request to read the room before it finishes its turn (never twice in a row).
- **The mod** (`mod/`) is a Claude Code mod: a plugin of TypeScript hooks that Claude Code runs inside itself. `tatami mod on` adds one line to `~/.bashrc` that points `CLAUDE_CODE_PLUGIN_DIRS` at it. Every few seconds it runs `tatami mod poll`, which finds its window's agent through the process tree and reads the same files the desk does; it never talks to the desk or the network. `mod/tests` runs with `claude plugin test mod`.
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
tatami mod off       # only if you turned it on
waifu uninstall
claude mcp remove tatami --scope user
```

This removes the Tatami Room app, the hidden profiles, both shortcuts, the launchers and links, the hooks and the team channel. Downloaded wallpapers stay in their folder in case you want them. To remove everything, also delete that folder, this repo, `~/.local/bin/tatami`, `~/.local/bin/waifu` and `~/.local/state/tatami`.

## Credits

- The optional wallpapers are official HoYoverse art, downloaded to your own machine from Danbooru. **This repository contains no images.** Details in [Window looks](LOOKS.md#art-and-credits).
- This is a fan project. It isn't affiliated with Anthropic, HoYoverse or Danbooru.

The code is released under the [MIT License](LICENSE).

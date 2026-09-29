# Tatami Room

**A desk for your AI coding agents.** Run several Claude Code agents side by side, see them all in one place, and drag them together into teams that talk to each other. Every window gets its own anime girl and its own color, so you can tell your agents apart at a glance.

The name comes from tatami, the woven mats that fit side by side to make a Japanese room. Each agent is a mat. Lay mats together and you've made a room: a team working on the same thing.

> **Work in progress.** Everything below works today with Claude Code on Windows Terminal and WSL. Next up: agents from other companies, like Gemini CLI and Codex, joining the same rooms. The plan and the reasoning behind it are in [DESK.md](DESK.md).

## Why

One agent in one terminal is easy. Five agents in five identical terminals is a mess: which one is doing what, which one is waiting for you, and how do they share what they've found? Tatami Room turns them into a team you can see.

- **See every agent at once.** The desk shows each running agent as a mat, with its folder and whether it's busy, done, or waiting for your OK.
- **Team up by dragging.** Drop one mat onto another and those agents share a room. In a room they post updates, hand off tasks and ask each other questions.
- **Tell them apart at a glance.** Every window has its own girl and background color, and the windows of a team share a tab color.

## What you get

### The desk

- **A Tatami Room window** that opens with your first Claude window after WSL starts, or any time from its own shortcut. It's your board: every running agent is a mat.
- **Rooms you make by dragging.** New agents wait on their own in a strip along the top. Drop one mat onto another and the two get a new room, named the way a Japanese inn names its rooms: after a flower in the room's color (sakura is pink, fuji is lavender, momiji is peach). Drag a mat into a room to join that team, or back to the strip to take it off. Agents started in the same project folder share that project's room automatically.
- **A team channel.** Each agent gets three tools: `room_post` for an update, a hand-off or a question, `room_read` for what the others said, and `room_members` for who's on the team. An agent is told when you move it.
- **Matching tab colors.** Windows on the same team get the same tab color, the one the desk shows for their room. No two teams share a color.
- **Who needs you** (optional). Turn it on with `tatami hooks on` and each mat says *working*, *your turn* or *needs your OK*. A mat waiting on a permission prompt pulses pink, and the desk's title counts them.
- **Your usage.** The desk's header shows your 5-hour and weekly Claude usage, with reset times.

### Window looks

- **A Claude Waifu shortcut** on your desktop and in the Start menu. It opens a new window and starts Claude right away. When you exit Claude you're left in a normal shell.
- **A different girl in every window**, from Genshin Impact, Honkai: Star Rail or Zenless Zone Zero, redrawn as faint negative braille dots: only the line art and dark areas get dots, so your code stays easy to read. Only official art is used, pulled from Danbooru's `official_art` tag. Pieces must be wide, safe-rated and girls only: no male characters, and no event posters covered in text. Prefer the real picture? `waifu style image`.
- **A different color per window.** Twelve dark hues are dealt like a shuffled deck, so every color is used before any repeats, and no two open windows share one.
- **Windows that stay as they are.** Open windows never change; only new windows get the next girl. Fresh wallpapers download quietly every day.

## Requirements

- Windows 10 or 11 with [Windows Terminal](https://aka.ms/terminal)
- WSL 2 (tested on Ubuntu)
- Claude Code installed inside WSL, so `claude` runs in your shell
- Python 3, plus Pillow for the dot art. Either install [uv](https://docs.astral.sh/uv/) (recommended) or run `sudo apt install python3-pil`
- For the desk in a window of its own: Brave, Chrome or Edge as your default browser. With another browser, the desk opens in a tab.
- Optional: the Claude desktop app. If it's installed, setup uses its icon for the Claude Waifu shortcut and tabs

## Install

Inside WSL:

```bash
git clone https://github.com/natsuin/tatami-room.git
cd tatami-room
./install.sh
```

The installer:

1. Links the `waifu` and `tatami` commands into `~/.local/bin`.
2. Gives Claude Code the team channel, so every new session has the room tools.
3. Finds your Windows folders and Windows Terminal's settings, and downloads 20 wallpapers into `%USERPROFILE%\TerminalGirls`.
4. Adds ten hidden profiles to Windows Terminal, one per window.
5. Puts two shortcuts on your desktop and in the Start menu: **Claude Waifu** (a new Claude window) and **Tatami Room** (the desk). Right-click either one and choose **Pin to taskbar** to keep it handy.

Options:

- `./install.sh --pool /mnt/d/Wallpapers` keeps the wallpapers somewhere else. The folder must be on a Windows drive.
- `./install.sh --no-claude` opens a plain shell in new windows instead of starting Claude.

To update later, run `git pull` in the folder. Everything is linked, not copied, so there's nothing else to do.

## Everyday use

1. Open **Claude Waifu**. Claude starts in a new window, and the first window since WSL started opens the desk beside it.
2. Open more windows for more agents. Each one appears on the desk, on its own.
3. When agents should work together, drag one mat onto another. They're a team now: their tabs turn their room's color, and they can talk in their room.
4. Glance at the desk to see who's busy and who's waiting for you.

From inside Claude Code, put `!` in front of a command, like `! waifu next`.

### The desk

| Command | What it does |
| --- | --- |
| `tatami` | Open the desk, or bring it to the front |
| `tatami hooks on` | Show which agents are working, done, or waiting for your OK (`tatami hooks off` removes it) |
| `tatami autostart off` | Don't open the desk with your first Claude window (`tatami autostart on` brings it back) |
| `tatami stop` | Stop the desk's server; your agents keep running and don't need it |

### Window looks

| Command | What it does |
| --- | --- |
| `waifu` | Give this window a different girl |
| `waifu info` | Who's in this window, which game, and where HoYoverse posted it |
| `waifu keep` | Keep this girl forever (the daily cleanup skips her) |
| `waifu ban` | Never show this girl again, and swap her out |
| `waifu fetch 12` | Download 12 more wallpapers right now |
| `waifu style image` | Show full-color pictures instead of dots (`waifu style dots` to go back) |
| `waifu opacity 25` | Make the art fainter or bolder (percent) |
| `waifu off` / `waifu on` | Hide every girl (on the desk too), for screen sharing, and bring them back |
| `waifu open` | Open the wallpaper folder in Explorer |
| `waifu launch` | Open a new Claude Waifu window from inside WSL |
| `waifu uninstall` | Remove the profiles, shortcuts and launchers |

You can also drop your own `.png` or `.jpg` wallpapers into the folder. They join the rotation.

## How it works

### The desk

- **The team channel** is a small MCP server, plain Python with no dependencies, that every Claude Code session starts for itself. The agents share a folder of plain files in `~/.local/state/tatami`: the messages of each room, and a note per agent saying which room it's in. There's no daemon, no network, and nothing that runs commands.
- **An agent's room** is its project's room if you started it in a project folder, or none (on its own) if you started it in your home folder, which is where Claude Waifu windows start. The desk records the rooms you drag agents into.
- **The desk** is a local web page served from your own PC. It listens on this machine only and needs a secret token, so other devices and websites can't use it. It shows your agents and changes which room each one is in, and nothing else: it can't run commands or reach your terminals.
- **Tab colors** are set by each agent's own channel, on its own window only, through `waifu`, which owns Windows Terminal's settings.
- **Who needs you** comes from Claude Code hooks: small commands Claude Code runs when you send a prompt, when it uses a tool, when it finishes, and when it's waiting for your OK. They note each agent's state in a file for the desk, print nothing, and never change what Claude does.
- **WSL shuts itself down** soon after its last terminal closes, and the desk's server with it. So while a desk window is open, it quietly holds WSL up, and it lets go a few minutes after you close the desk.

### Window looks

Windows Terminal can only give a background image to a *profile*, and every tab using that profile shares it. So setup adds ten hidden profiles, called slots, and each slot holds its own girl and color.

- The shortcut opens a new window on the slot that's already loaded and starts Claude. Then `waifu advance` loads the next slot, ready for your next window. Because the picture is loaded ahead of time, it's there the moment the window opens.
- Each window knows its own slot, because Windows Terminal tells the shell through `WT_PROFILE_ID`. So `waifu next` only changes the window you run it in, and a team's tab color only goes on its own members' windows.
- With ten slots, your 11th window reuses the first slot. Keep ten or fewer Claude Waifu windows open and every open window stays exactly as it is.
- Windows opened the normal way, for example from the Ubuntu icon, share one default profile, so they all show the same girl and don't get tab colors. Their agents still show up on the desk.

Your settings live in `~/.config/waifu/config.json`, and waifu's memory of what's been shown in `~/.local/state/waifu/`.

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

This removes the hidden profiles, both shortcuts, the launchers, the hooks and the team channel. Your wallpapers stay in their folder in case you want them. To remove everything, also delete that folder, this repo, `~/.local/bin/waifu`, `~/.local/bin/tatami` and `~/.local/state/tatami`.

## Art and credits

- All artwork belongs to HoYoverse (miHoYo). **This repository contains no images.** waifu downloads official art from [Danbooru](https://danbooru.donmai.us) onto your own machine, for personal use as a wallpaper. `waifu info` links to where each piece was originally posted. Please don't redistribute the downloaded images.
- waifu uses Danbooru's public API gently: one scan of each game's official art per week, with a pause between pages, plus a handful of downloads a day.
- This is a fan project. It isn't affiliated with Anthropic, HoYoverse or Danbooru.

The code is released under the [MIT License](LICENSE).

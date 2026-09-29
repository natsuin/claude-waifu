# Tatami Room

**Every Claude Code window gets its own anime girl and its own color, and a desk where your agents team up.**

Tatami Room is a small add-on for [Claude Code](https://code.claude.com) on Windows Terminal + WSL. The name comes from tatami, the woven mats that fit side by side to make a Japanese room: each agent window is a mat, and laying them together makes a room for a project.

It has two parts:

- **Window looks (ready to use).** Open a window from the **Claude Waifu** shortcut and Claude starts right away, with a girl from Genshin Impact, Honkai: Star Rail or Zenless Zone Zero drawn behind your text as faint braille dots. The window also gets a background color no other open window has, so you can tell your sessions apart at a glance. Windows that are already open never change. Only new windows get the next girl.
- **The desk (work in progress).** A board that shows every running agent as a mat, and a team channel so agents on the same project can talk to each other. Drag mats together to team agents up. See [The desk](#the-desk-work-in-progress) below, and [DESK.md](DESK.md) for the plan.

## What you get

- **A Claude Waifu shortcut** on your desktop and in the Start menu. It opens a new window and starts Claude immediately. When you exit Claude you're left in a normal shell.
- **A different girl in every window.** Only official art is used, pulled from Danbooru's `official_art` tag. Pieces must be wide, safe-rated and girls only: no male characters, and no event posters covered in text.
- **Art that stays in the background.** Each wallpaper is redrawn as negative braille dots: only the line art and dark areas get dots, so your code stays easy to read. Prefer the real picture? `waifu style image`.
- **A different color per window.** Twelve dark hues are dealt like a shuffled deck, so every color is used before any repeats, and no two open windows share one.
- **Fresh wallpapers every day**, downloaded quietly in the background.

## Requirements

- Windows 10 or 11 with [Windows Terminal](https://aka.ms/terminal)
- WSL 2 (tested on Ubuntu)
- Claude Code installed inside WSL, so `claude` runs in your shell
- Python 3, plus Pillow for the dot art. Either install [uv](https://docs.astral.sh/uv/) (recommended) or run `sudo apt install python3-pil`
- Optional: the Claude desktop app. If it's installed, setup uses its icon for the shortcut and tabs

## Install

Inside WSL:

```bash
git clone https://github.com/natsuin/tatami-room.git
cd tatami-room
./install.sh
```

Setup does four things:

1. Finds your Windows folders and Windows Terminal's settings.
2. Downloads 20 wallpapers into `%USERPROFILE%\TerminalGirls`.
3. Adds ten hidden profiles to Windows Terminal.
4. Puts a **Claude Waifu** shortcut on your desktop and in the Start menu. Right-click it and choose **Pin to taskbar** to keep it handy.

Options:

- `./install.sh --pool /mnt/d/Wallpapers` keeps the wallpapers somewhere else. The folder must be on a Windows drive.
- `./install.sh --no-claude` opens a plain shell instead of starting Claude.

To update later, run `git pull` in the folder. `waifu` is linked, not copied, so there's nothing else to do.

## Everyday commands

Run these inside a Claude Waifu window. From inside Claude Code, put `!` in front, like `! waifu next`.

| Command | What it does |
| --- | --- |
| `waifu` | Give this window a different girl |
| `waifu info` | Who's in this window, which game, and where HoYoverse posted it |
| `waifu keep` | Keep this girl forever (the daily cleanup skips her) |
| `waifu ban` | Never show this girl again, and swap her out |
| `waifu fetch 12` | Download 12 more wallpapers right now |
| `waifu style image` | Show full-color pictures instead of dots (`waifu style dots` to go back) |
| `waifu opacity 25` | Make the art fainter or bolder (percent) |
| `waifu off` / `waifu on` | Hide every girl, for screen sharing, and bring them back |
| `waifu open` | Open the wallpaper folder in Explorer |
| `waifu launch` | Open a new Claude Waifu window from inside WSL |
| `waifu uninstall` | Remove the profiles, shortcut and launcher |

You can also drop your own `.png` or `.jpg` wallpapers into the folder. They join the rotation.

## The desk (work in progress)

Two pieces work today:

- **The team channel**, an MCP server that gives agents three tools: `room_post`, `room_read` and `room_members`. Agents working in the same project folder share a room automatically.
- **The board**, a local page that shows each running agent as a mat, grouped by room. Drag a mat into another room to team agents up, or make an empty room with **+ Room**.

`install.sh` doesn't set these up yet. To try them, run this inside the repo folder:

```bash
claude mcp add --scope user tatami -- python3 "$PWD/tatami/tatami_mcp.py"
ln -sf "$PWD/tatami/tatami" ~/.local/bin/tatami
```

New Claude sessions pick up the channel. Run `tatami` to open the board in your browser, and `tatami stop` to close it; your agents keep running without it. The board listens on your PC only, needs a secret token, and can't run commands or touch your terminals. It only arranges agents into rooms.

Next up: a matching tab color for windows in the same room, then Gemini CLI and Codex joining rooms alongside Claude.

## How the window looks work

Windows Terminal can only give a background image to a *profile*, and every tab using that profile shares it. So setup adds ten hidden profiles, called slots, and each slot holds its own girl and color.

- The shortcut opens a new window on the slot that's already loaded and starts Claude. Then `waifu advance` loads the next slot, ready for your next window. Because the picture is loaded ahead of time, it's there the moment the window opens.
- Each window knows its own slot, because Windows Terminal tells the shell through `WT_PROFILE_ID`. So `waifu next` only changes the window you run it in.
- With ten slots, your 11th window reuses the first slot. Keep ten or fewer Claude Waifu windows open and every open window stays exactly as it is.
- Windows opened the normal way, for example from the Ubuntu icon, share one default profile, so they all show the same girl.

Your settings live in `~/.config/waifu/config.json`, and waifu's memory of what's been shown in `~/.local/state/waifu/`.

## Extras for Claude Code

The `extras/` folder has three optional add-ons that go well with the wallpapers.

**Usage bar** (`statusline.py`) puts your 5-hour and weekly Claude usage on the bar under the prompt, with reset times and how full your context is:

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
waifu uninstall
```

This removes the hidden profiles, the shortcut and the launcher. Your wallpapers stay in their folder in case you want them. Delete that folder, this repo and `~/.local/bin/waifu` to remove everything. If you set up the desk, also run `claude mcp remove tatami -s user` and delete `~/.local/bin/tatami` and `~/.local/state/tatami`.

## Art and credits

- All artwork belongs to HoYoverse (miHoYo). **This repository contains no images.** waifu downloads official art from [Danbooru](https://danbooru.donmai.us) onto your own machine, for personal use as a wallpaper. `waifu info` links to where each piece was originally posted. Please don't redistribute the downloaded images.
- waifu uses Danbooru's public API gently: one scan of each game's official art per week, with a pause between pages, plus a handful of downloads a day.
- This is a fan project. It isn't affiliated with Anthropic, HoYoverse or Danbooru.

The code is released under the [MIT License](LICENSE).

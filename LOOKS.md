# Window looks

Tatami Room's design touch: every Claude window gets a background color no other open window has, and, if you like, an anime girl drawn behind your text. It's how you tell your agents apart at a glance. The `waifu` command runs it; [install.sh](install.sh) sets it up with the rest of Tatami Room.

## What you get

- **A different color per window.** Twelve dark shades that sit with the sakura look (cherry, rouge, wine, plum, mauve, orchid, grape, iris, indigo, dusk, haze and matcha green) are dealt like a shuffled deck, so every color is used before any repeats, and no two open windows share one. Windows on the same team also share a tab color (see the [README](README.md)).
- **A different girl per window**, from Genshin Impact, Honkai: Star Rail or Zenless Zone Zero, redrawn as faint negative braille dots: only the line art and dark areas get dots, so your code stays easy to read. The picture is stretched to fill the window, so a big or full-screen window draws every dot bigger; the dots fade as it grows (down to 40% of their usual strength), and come back when it shrinks. Prefer the real picture? `waifu style image`.
- **Official art only**, pulled from Danbooru's `official_art` tag. Pieces must be wide, safe-rated and girls only: no male characters, and no event posters covered in text.
- **Windows that stay as they are.** Open windows never change; only new windows get the next girl. Fresh wallpapers download quietly every day.

## Commands

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
| `waifu off` / `waifu on` | Hide every girl (on the desk too), for screen sharing, and bring them back |
| `waifu open` | Open the wallpaper folder in Explorer |
| `waifu launch` | Open a new Claude Waifu window from inside WSL |
| `waifu uninstall` | Remove the profiles, shortcuts and launchers |

You can also drop your own `.png` or `.jpg` wallpapers into the folder (`%USERPROFILE%\TerminalGirls` unless you chose another with `./install.sh --pool`). They join the rotation.

## Setup options

`./install.sh` passes these on to `waifu setup`:

- `--pool /mnt/d/Wallpapers` keeps the wallpapers somewhere else. The folder must be on a Windows drive.
- `--no-claude` opens a plain shell in new windows instead of starting Claude.

## How it works

Windows Terminal can only give a background image to a *profile*, and every tab using that profile shares it. So setup adds ten hidden profiles, called slots, and each slot holds its own girl and color.

- The Claude Waifu shortcut (and the desk's **+ Claude** button) opens a new window on the slot that's already loaded and starts Claude. Then `waifu advance` loads the next slot, ready for your next window. Because the picture is loaded ahead of time, it's there the moment the window opens.
- Each window knows its own slot, because Windows Terminal tells the shell through `WT_PROFILE_ID`. So `waifu next` only changes the window you run it in, and a team's tab color only goes on its members' windows.
- With ten slots, your 11th window reuses the first slot. Keep ten or fewer Claude Waifu windows open and every open window stays exactly as it is.
- Windows opened the normal way, for example from the Ubuntu icon, share one default profile, so they all show the same girl and don't get tab colors. Their agents still show up on the desk.

Your settings live in `~/.config/waifu/config.json`, and waifu's memory of what's been shown in `~/.local/state/waifu/`.

## Art and credits

- All artwork belongs to HoYoverse (miHoYo). **This repository contains no images.** waifu downloads official art from [Danbooru](https://danbooru.donmai.us) onto your own machine, for personal use as a wallpaper. `waifu info` links to where each piece was originally posted. Please don't redistribute the downloaded images.
- waifu uses Danbooru's public API gently: one scan of each game's official art per week, with a pause between pages, plus a handful of downloads a day.

#!/usr/bin/env bash
# Tatami Room installer. Run it inside WSL from the cloned repo:  ./install.sh
# It links the waifu and tatami commands, gives Claude Code the team channel, and runs
# `waifu setup`: the window looks, and the Claude Waifu and Tatami Room shortcuts.
# Options are passed to `waifu setup`: --pool DIR (where wallpapers go), --no-claude
# (open a plain shell instead of starting Claude).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

[ -n "${WSL_DISTRO_NAME:-}" ] || { echo "Run this inside WSL (Windows Subsystem for Linux)."; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required."; exit 1; }
if ! python3 -c 'import PIL' 2>/dev/null && ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "The dot art needs Pillow. Install uv (https://docs.astral.sh/uv/) or: sudo apt install python3-pil"
  exit 1
fi

# Links, not copies, so `git pull` in this folder updates everything.
chmod +x "$here/waifu" "$here/tatami/tatami" "$here/tatami/hooks.py"
mkdir -p "$HOME/.local/bin"
ln -sf "$here/waifu" "$HOME/.local/bin/waifu"
ln -sf "$here/tatami/tatami" "$HOME/.local/bin/tatami"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Note: add ~/.local/bin to your PATH to run 'waifu' and 'tatami' by name." ;; esac

# The team channel: every new Claude Code session gets the room_post, room_read and
# room_members tools. Registered through the link, so moving this folder can't break it.
if command -v claude >/dev/null; then
  claude mcp remove tatami --scope user >/dev/null 2>&1 || true
  claude mcp add --scope user tatami -- "$HOME/.local/bin/tatami" mcp
else
  echo "Claude Code isn't installed yet. Once it is, run: claude mcp add --scope user tatami -- $HOME/.local/bin/tatami mcp"
fi

"$HOME/.local/bin/waifu" setup "$@"
echo
echo "Tatami Room is ready. Open Claude Waifu from your desktop or Start menu: the desk opens with your first window."
echo "Optional: run 'tatami hooks on' so the desk shows which agents are busy and which are waiting for you."

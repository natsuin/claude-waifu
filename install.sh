#!/usr/bin/env bash
# Tatami Room installer (sets up the window looks). Run it inside WSL from the cloned repo:  ./install.sh
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

# A link, not a copy, so `git pull` in this folder updates waifu too.
chmod +x "$here/waifu"
mkdir -p "$HOME/.local/bin"
ln -sf "$here/waifu" "$HOME/.local/bin/waifu"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Note: add ~/.local/bin to your PATH to run 'waifu' by name." ;; esac

"$HOME/.local/bin/waifu" setup "$@"

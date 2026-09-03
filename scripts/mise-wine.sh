#!/usr/bin/env bash
# Launcher: Monkey Island Special Edition (GOG) via Flatpak WineHQ
set -e
GAME_DIR="$HOME/Projects/monkeyisland/tsomir/extracted"
cd "$GAME_DIR"
exec flatpak run --user --filesystem=host \
  --command=wine org.winehq.Wine/x86_64/stable \
  "$GAME_DIR/MISE.exe" "$@"

#!/usr/bin/env bash
# Launcher: Monkey Island Special Edition (GOG) en MODO VENTANA via WineHQ Flatpak
# Usa el escritorio virtual de Wine (/desktop=WxH) para forzar windowed.
#
# Uso:
#   ./mise-wine-windowed.sh              # 1280x720
#   ./mise-wine-windowed.sh 1024x768     # tamaño personalizado
#   WINE_DESKTOP=1366x768 ./mise-wine-windowed.sh
#
# Variables de entorno:
#   WINE_DESKTOP  tamaño WxH del escritorio virtual (default 1280x720)

set -e

GAME_DIR="$HOME/Projects/monkeyisland/tsomir/extracted"

# Tamaño del escritorio virtual
SIZE="${1:-${WINE_DESKTOP:-1280x720}}"

cd "$GAME_DIR"

# /desktop=WxH crea un escritorio virtual del tamaño indicado.
# El juego corre DENTRO de esa ventana, no a pantalla completa.
exec flatpak run --user --filesystem=host \
    --command=wine org.winehq.Wine/x86_64/stable \
    explorer /desktop="$SIZE" "$GAME_DIR/MISE.exe" "$@"

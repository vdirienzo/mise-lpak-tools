#!/usr/bin/env bash
# capture_screenshot.sh — Captura la pantalla actual con ffmpeg/x11grab.
#
# Uso:
#   ./capture_screenshot.sh ruta/salida.png
#   ./capture_screenshot.sh            # guarda en /tmp/screenshot.png
#
# Variables:
#   SCREEN_SIZE  tamaño WxH (default: autodetecta con xrandr)

OUT="${1:-/tmp/screenshot.png}"
DISPLAY="${DISPLAY:-:0}"

if [[ -z "$SCREEN_SIZE" ]]; then
    # Autodetecta desde xrandr (modo con '*' al final = activo).
    DETECTED=$(xrandr --display "$DISPLAY" 2>/dev/null \
        | awk '/\*/ {print $1; exit}')
    SIZE="${DETECTED:-1366x768}"
else
    SIZE="$SCREEN_SIZE"
fi

echo "Capturando ${SIZE} de ${DISPLAY} → ${OUT}"

ffmpeg -loglevel error -f x11grab -video_size "$SIZE" -framerate 1 \
       -i "$DISPLAY" -frames:v 1 -update 1 -y "$OUT" 2>&1 \
    | tail -3

if [[ -f "$OUT" ]]; then
    echo "Screenshot guardado en: $OUT ($(du -h "$OUT" | cut -f1))"
else
    echo "ERROR: no se pudo capturar"
    exit 1
fi


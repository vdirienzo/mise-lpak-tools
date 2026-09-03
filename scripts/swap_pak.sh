#!/usr/bin/env bash
# swap_pak.sh — Alterna entre Monkey1.pak original y modificado.
#
# Uso:
#   ./swap_pak.sh original   # restaura el pak original
#   ./swap_pak.sh mod        # pone el pak modificado
#   ./swap_pak.sh status     # muestra cuál está activo

set -e

GAME_DIR="$HOME/Projects/monkeyisland/tsomir/extracted"
ORIG_PAK_BACKUP="$HOME/Projects/monkeyisland/tsomir/test_roundtrip/Monkey1_rebuild.pak"
MOD_PAK="$HOME/Projects/monkeyisland/tsomir/test_mod/Monkey1_mod.pak"
ACTIVE_PAK="$GAME_DIR/Monkey1.pak"

case "${1:-status}" in
    original)
        if [[ ! -f "$ORIG_PAK_BACKUP" ]]; then
            echo "ERROR: no existe backup original en $ORIG_PAK_BACKUP"
            exit 1
        fi
        cp "$ORIG_PAK_BACKUP" "$ACTIVE_PAK"
        echo "✓ Pak ORIGINAL restaurado (hash = $(sha256sum "$ACTIVE_PAK" | cut -c1-16)...)"
        ;;
    mod)
        if [[ ! -f "$MOD_PAK" ]]; then
            echo "ERROR: no existe pak modificado en $MOD_PAK"
            exit 1
        fi
        cp "$MOD_PAK" "$ACTIVE_PAK"
        echo "✓ Pak MODIFICADO activado (hash = $(sha256sum "$ACTIVE_PAK" | cut -c1-16)...)"
        ;;
    status)
        echo "Pak activo: $ACTIVE_PAK"
        echo "Hash:       $(sha256sum "$ACTIVE_PAK" 2>/dev/null | cut -c1-16)..."
        if cmp -s "$ACTIVE_PAK" "$ORIG_PAK_BACKUP"; then
            echo "Estado:     ORIGINAL"
        elif cmp -s "$ACTIVE_PAK" "$MOD_PAK"; then
            echo "Estado:     MODIFICADO"
        else
            echo "Estado:     DESCONOCIDO (no es ni el original ni el mod)"
        fi
        ;;
    *)
        echo "Uso: $0 [original|mod|status]"
        exit 1
        ;;
esac

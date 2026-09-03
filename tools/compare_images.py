#!/usr/bin/env python3
"""
compare_images.py — Compara dos screenshots y genera un diff visual.

Uso:
  ./compare_images.py before.png after.png
  ./compare_images.py before.png after.png --out diff.png

Genera:
  - diff.png: imagen de diferencias (rojo donde difieren)
  - reporte en stdout con porcentaje de pixeles distintos
"""

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError:
    print("ERROR: requiere Pillow. pip install Pillow", file=sys.stderr)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--out", type=Path, default=None,
                   help="Imagen de salida con el diff (default: <before>_diff.png)")
    p.add_argument("--threshold", type=int, default=10,
                   help="Umbral de diferencia por canal (0-255)")
    args = p.parse_args()

    if not args.before.is_file() or not args.after.is_file():
        print("ERROR: falta alguna imagen", file=sys.stderr)
        return 1

    before = Image.open(args.before).convert("RGB")
    after = Image.open(args.after).convert("RGB")

    if before.size != after.size:
        print(f"AVISO: tamaños distintos: {before.size} vs {after.size}")

    # Diff absoluto.
    diff = ImageChops.difference(before, after)

    # Convierte diff a binario (donde hay diferencias significativas).
    # diff es RGB, primero lo pasamos a gris (máximo de los canales),
    # después binarizamos con el threshold.
    threshold = args.threshold
    diff_gray = diff.convert("L")
    mask = diff_gray.point(lambda v: 255 if v > threshold else 0)
    diff_count = sum(1 for p in mask.getdata() if p == 255)
    total = before.size[0] * before.size[1]
    pct = 100.0 * diff_count / total

    print(f"Imagenes: {args.before} vs {args.after}")
    print(f"Tamaño: {before.size}")
    print(f"Pixel threshold: {threshold}")
    print(f"Píxeles diferentes: {diff_count:,} / {total:,} ({pct:.2f}%)")

    # Imagen de salida: original "before" con las diferencias resaltadas en rojo.
    out = before.copy()
    red_overlay = Image.new("RGB", before.size, (255, 0, 0))
    out.paste(red_overlay, mask=mask)

    out_path = args.out or args.before.with_name(
        f"{args.before.stem}_diff{args.before.suffix}")
    out.save(out_path)
    print(f"Diff guardado en: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

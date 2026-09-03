#!/usr/bin/env python3
"""
png_to_dxt.py — Convierte PNG a .dxt (DXT5 o DXT1) listo para el juego MISE.

Pipeline:
  PNG (RGBA o RGB)
    ↓ comprimir con DXT5 nativo (range-fit, ver dxt5_compress.py)
  bytes DXT5
    ↓ prepend header .dxt (4 bytes magic + 4 width + 4 height)
  archivo .dxt compatible con el motor MISE

Limitaciones:
  - Compresión con pérdida (artefactos menores en bordes/transparencias)
  - Dimensiones deben ser múltiplos de 4 (se paddea replicando)
  - Para calidad superior, usar quicktex/librerías externas

Uso:
  ./png_to_dxt.py input.png output.dxt                    # detecta formato del original
  ./png_to_dxt.py input.png output.dxt --format dxt5      # fuerza DXT5 (con alpha)
  ./png_to_dxt.py input.png output.dxt --format dxt1      # fuerza DXT1 (sin alpha)
  ./png_to_dxt.py input.png output.dxt --size 256x256     # fuerza dimensiones
"""

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from PIL import Image
    import numpy as np
    from dxt5_compress import compress_dxt5, compress_dxt1
except ImportError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)

try:
    import etcpak
    _HAS_ETCPAK = True
except ImportError:
    _HAS_ETCPAK = False


def _arr_to_rgba_bytes(arr):
    """Convierte (H, W, 3) o (H, W, 4) numpy array a bytes RGBA planos."""
    h, w = arr.shape[:2]
    if arr.shape[2] == 4:
        return np.ascontiguousarray(arr, dtype=np.uint8).tobytes()
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., :3] = arr
    rgba[..., 3] = 255
    return rgba.tobytes()


def png_to_dxt(in_path, out_path, fmt="auto", size=None):
    """Convierte PNG a .dxt. Devuelve (width, height, formato_elegido).

    Usa etcpak (más rápido y mejor calidad) si está disponible; si no,
    cae al compresor range-fit de dxt5_compress.py.
    """
    img = Image.open(in_path)

    # Convertir a RGBA o RGB según el formato
    if fmt == "auto":
        fmt = "dxt5" if img.mode in ("RGBA", "LA", "PA") else "dxt1"

    if fmt == "dxt5":
        if img.mode != "RGBA":
            img = img.convert("RGBA")
    else:  # dxt1
        if img.mode == "RGBA":
            # Descartar alpha para DXT1 (no soporta alpha completo, solo 1-bit)
            # O convertir premultiplicado
            bg = Image.new("RGB", img.size, (0, 0, 0))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

    if size:
        # size override (generalmente no usado: el caller ya redimensionó)
        img = img.resize(size, Image.NEAREST)

    w, h = img.size
    arr = np.array(img)

    if _HAS_ETCPAK:
        raw = _arr_to_rgba_bytes(arr)
        if fmt == "dxt5":
            compressed = etcpak.compress_to_dxt5(raw, w, h)
            magic = b"DXT5"
        else:
            compressed = etcpak.compress_to_dxt1(raw, w, h)
            magic = b"DXT1"
    else:
        if fmt == "dxt5":
            compressed = compress_dxt5(arr)
            magic = b"DXT5"
        else:
            compressed = compress_dxt1(arr)
            magic = b"DXT1"

    dxt_bytes = magic + struct.pack("<II", w, h) + compressed

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(dxt_bytes)

    return w, h, fmt


def main():
    p = argparse.ArgumentParser(description="Convierte PNG a .dxt (DXT5/DXT1).")
    p.add_argument("input", type=Path, help="Archivo PNG de entrada")
    p.add_argument("output", type=Path, help="Archivo .dxt de salida")
    p.add_argument("--format", choices=["auto", "dxt5", "dxt1"], default="auto",
                   help="Formato DXT (default: auto según el PNG)")
    p.add_argument("--size", default=None,
                   help="Forzar tamaño WxH (ej: 256x256). El PNG se redimensiona.")
    args = p.parse_args()

    if not args.input.is_file():
        print(f"ERROR: {args.input} no existe", file=sys.stderr)
        return 1

    size = None
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            size = (int(w), int(h))
        except ValueError:
            print(f"ERROR: --size debe ser WxH (ej: 256x256)", file=sys.stderr)
            return 1

    try:
        w, h, fmt = png_to_dxt(args.input, args.output, fmt=args.format, size=size)
        print(f"✓ {args.input} → {args.output} ({w}x{h} {fmt.upper()})")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
dxt_to_png.py — Convierte archivos .dxt del juego a .png para edición.

Los archivos .dxt del MISE tienen un formato custom de 12 bytes:
  - 4 bytes: magic ("DXT5" o "DXT1" en ASCII)
  - 4 bytes: width (u32 LE)
  - 4 bytes: height (u32 LE)
  - resto: datos DXT comprimidos (sin header DDS estándar)

Este script envuelve el archivo en un DDS estándar de 124 bytes y usa Pillow
para descomprimir el DXT a RGBA, guardándolo como PNG estándar editable por
cualquier herramienta (GIMP, Photoshop, Stable Diffusion, etc.).

Uso:
  ./dxt_to_png.py input.dxt output.png
  ./dxt_to_png.py input.dxt output.png --no-alpha   # descarta alpha en el output

Batch:
  ./dxt_to_png.py --batch input_dir/ output_dir/
  ./dxt_to_png.py --batch input_dir/ output_dir/ --filter melee
"""

import argparse
import struct
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow no instalado. pip install Pillow", file=sys.stderr)
    sys.exit(1)


DXT_MAGIC_SIZE = 4
DXT_HEADER_SIZE = 12
DDS_HEADER_SIZE = 124
DDS_MAGIC = b"DDS "

# DDS flags
DDSD_CAPS         = 0x00000001
DDSD_HEIGHT       = 0x00000002
DDSD_WIDTH        = 0x00000004
DDSD_PIXELFORMAT  = 0x00001000
DDSD_LINEARSIZE   = 0x00080000
DDPF_FOURCC       = 0x00000004
DDSCAPS_TEXTURE   = 0x00001000


def dxt_to_dds(dxt_bytes):
    """Envuelve bytes .dxt en un .dds estándar (128 bytes header + data)."""
    if len(dxt_bytes) < DXT_HEADER_SIZE:
        raise ValueError(f"Archivo .dxt demasiado pequeño: {len(dxt_bytes)} bytes")

    magic = dxt_bytes[:4]
    if magic not in (b"DXT1", b"DXT3", b"DXT5"):
        raise ValueError(f"Magic inválido: {magic!r}")

    width, height = struct.unpack("<II", dxt_bytes[4:12])
    data = dxt_bytes[DXT_HEADER_SIZE:]

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE

    # Header de 124 bytes después del magic "DDS " (4 bytes)
    dds_header = struct.pack(
        "<7I",
        124,              # dwSize
        flags,            # dwFlags
        height,           # dwHeight
        width,            # dwWidth
        len(data),        # dwPitchOrLinearSize
        0,                # dwDepth
        0,                # dwMipMapCount
    )
    dds_header += b"\x00" * 44                  # dwReserved1[11]
    dds_header += struct.pack(
        "<4I",
        32,                                      # pf_dwSize
        DDPF_FOURCC,                              # pf_dwFlags
        int.from_bytes(magic, "little"),          # pf_dwFourCC
        0,                                        # pf_dwRGBBitCount
    )
    dds_header += b"\x00" * 16                  # bitmasks (4 × 4)
    dds_header += struct.pack(
        "<5I",
        DDSCAPS_TEXTURE,                          # dwCaps1
        0,                                        # dwCaps2
        0,                                        # dwDDSX
        0,                                        # dwReserved
        0,                                        # dwReserved2
    )

    assert len(dds_header) == DDS_HEADER_SIZE

    return DDS_MAGIC + dds_header + data


def convert_file(in_path, out_path, drop_alpha=False):
    """Convierte un .dxt a .png."""
    dxt_bytes = Path(in_path).read_bytes()
    dds_bytes = dxt_to_dds(dxt_bytes)

    from io import BytesIO
    img = Image.open(BytesIO(dds_bytes))
    img.load()

    if drop_alpha and img.mode == "RGBA":
        img = img.convert("RGB")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")

    return img.size, img.mode


def main():
    p = argparse.ArgumentParser(
        description="Convierte archivos .dxt (MISE) a PNG editable."
    )
    p.add_argument("input", help="Archivo .dxt o carpeta (con --batch)")
    p.add_argument("output", help="Archivo .png o carpeta destino (con --batch)")
    p.add_argument("--batch", action="store_true",
                   help="Procesar carpeta completa")
    p.add_argument("--filter", default=None,
                   help="Con --batch: solo procesar archivos cuyo nombre contenga este texto")
    p.add_argument("--no-alpha", action="store_true",
                   help="Guardar PNG sin canal alpha")
    args = p.parse_args()

    if args.batch:
        in_dir = Path(args.input)
        out_dir = Path(args.output)
        if not in_dir.is_dir():
            print(f"ERROR: {in_dir} no es un directorio", file=sys.stderr)
            return 1
        out_dir.mkdir(parents=True, exist_ok=True)

        pattern = "*.dxt"
        files = sorted(in_dir.rglob(pattern))
        if args.filter:
            files = [f for f in files if args.filter.lower() in str(f).lower()]

        if not files:
            print(f"Ningún .dxt encontrado en {in_dir}")
            return 0

        print(f"Encontrados {len(files)} archivos .dxt")
        ok = 0
        fail = 0
        for f in files:
            rel = f.relative_to(in_dir)
            out_path = out_dir / rel.with_suffix(".png")
            try:
                size, mode = convert_file(f, out_path, drop_alpha=args.no_alpha)
                ok += 1
                if ok <= 3 or ok % 10 == 0:
                    print(f"  ✓ {rel} → {size} {mode}")
            except Exception as e:
                fail += 1
                print(f"  ✗ {rel}: {e}")

        print(f"\n✓ {ok} convertidos")
        if fail:
            print(f"✗ {fail} fallaron")
    else:
        try:
            size, mode = convert_file(args.input, args.output, drop_alpha=args.no_alpha)
            print(f"✓ {args.input} → {args.output} ({size[0]}x{size[1]} {mode})")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
lpak_sprite_convert.py — Conversor unificado de sprites del pak LPAK.

Combina dxt_to_png.py y png_to_dxt.py con awareness del pak. Permite:

  extract   — extrae un asset del pak (.dxt) como PNG
  inject    — convierte un PNG a .dxt y lo prepara para override
  batch     — procesa varios a la vez

Uso:
  ./lpak_sprite_convert.py extract <ruta/asset.dxt> salida.png
  ./lpak_sprite_convert.py extract <ruta/asset.dxt> salida.png --pak otro.pak

  ./lpak_sprite_convert.py inject png_editado.png <ruta/asset.dxt>
  ./lpak_sprite_convert.py inject png_editado.png <ruta/asset.dxt> --size 256x256

  ./lpak_sprite_convert.py batch --room 28 --op extract --out ./pngs
  ./lpak_sprite_convert.py batch --room 28 --op inject --src ./pngs
"""

import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from PIL import Image
    import numpy as np
    from dxt_to_png import dxt_to_dds
    from dxt5_compress import compress_dxt5, compress_dxt1
    from dxt_to_png import DXT_HEADER_SIZE
except ImportError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)


PAK_DEFAULT = Path(__file__).parent.parent / "extracted" / "Monkey1.pak"
EXTRACTED_DEFAULT = Path(__file__).parent.parent / "extracted"
ROOM_ASSETS_CACHE = Path("/tmp/room_assets.json")


def parse_pak_header(pak_file):
    """Lee el header del pak y devuelve la tabla de entries + nombres."""
    raw = pak_file.read(40)
    magic = raw[:4]
    if magic not in (b"KAPL", b"LPAK"):
        raise ValueError(f"Magic inválido: {magic!r}")

    pak_file.seek(40)
    pak_file.read(10396)
    entries = []
    for i in range(2599):
        e = struct.unpack("<IIIII", pak_file.read(20))
        entries.append(e)

    pak_file.seek(62416)
    name_block = pak_file.read(130444)
    names = []
    for e in entries:
        end = name_block.find(b"\x00", e[1])
        if end == -1:
            end = len(name_block)
        names.append(name_block[e[1]:end].decode())

    return entries, names


def read_dxt_from_pak(pak_path, asset_path):
    """Lee los bytes .dxt de un asset del pak."""
    with pak_path.open("rb") as f:
        entries, names = parse_pak_header(f)
        if asset_path not in names:
            raise FileNotFoundError(f"Asset no existe en pak: {asset_path}")
        idx = names.index(asset_path)
        e = entries[idx]
        abs_off = e[0] + 192860
        f.seek(abs_off)
        return f.read(e[2])


def cmd_extract(args):
    pak = args.pak
    if not pak.is_file():
        print(f"ERROR: pak no existe: {pak}", file=sys.stderr)
        return 1

    dxt_bytes = read_dxt_from_pak(pak, args.asset)
    if dxt_bytes[:3] != b"DXT":
        print(f"ERROR: {args.asset} no es DXT (magic={dxt_bytes[:4]!r})", file=sys.stderr)
        return 1
    magic = dxt_bytes[:4]
    width, height = struct.unpack("<II", dxt_bytes[4:12])
    data = dxt_bytes[12:]

    # Wrap en DDS y abrir con Pillow
    dds = dxt_to_dds(dxt_bytes)
    from io import BytesIO
    img = Image.open(BytesIO(dds))
    img.load()

    if args.drop_alpha:
        img = img.convert("RGB")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    print(f"✓ {args.asset} → {out_path} ({width}x{height} {magic.decode()})")


def cmd_inject(args):
    pak = args.pak
    if not pak.is_file():
        print(f"ERROR: pak no existe: {pak}", file=sys.stderr)
        return 1

    # Detectar formato DXT mirando el archivo original del pak
    orig_dxt = read_dxt_from_pak(pak, args.asset)
    orig_magic = orig_dxt[:4]
    orig_w, orig_h = struct.unpack("<II", orig_dxt[4:12])
    fmt = "dxt5" if orig_magic == b"DXT5" else "dxt1"

    # Cargar PNG y (opcionalmente) redimensionar
    img = Image.open(args.input)
    if fmt == "dxt5":
        if img.mode != "RGBA":
            img = img.convert("RGBA")
    else:
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (0, 0, 0))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

    if (img.width, img.height) != (orig_w, orig_h):
        print(f"AVISO: redimensionando {img.size} → ({orig_w}, {orig_h})")
        img = img.resize((orig_w, orig_h), Image.NEAREST)

    arr = np.array(img)
    if fmt == "dxt5":
        compressed = compress_dxt5(arr)
    else:
        compressed = compress_dxt1(arr)

    new_dxt = orig_magic + struct.pack("<II", orig_w, orig_h) + compressed

    # Si el nuevo .dxt es mayor que el original, no se puede in-place
    if len(new_dxt) > len(orig_dxt):
        print(f"ERROR: nuevo ({len(new_dxt)}) > original ({len(orig_dxt)}). "
              f"Use el script de reconstrucción de pak en lugar de override in-place.",
              file=sys.stderr)
        return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(new_dxt)
    print(f"✓ {args.input} → {out_path} ({orig_w}x{orig_h} {fmt.upper()}, "
          f"{len(orig_dxt) - len(new_dxt)} bytes más pequeño)")


def cmd_batch(args):
    import json

    if ROOM_ASSETS_CACHE.exists():
        with ROOM_ASSETS_CACHE.open() as f:
            room_assets = json.load(f)
    else:
        print("ERROR: /tmp/room_assets.json no existe. Ejecutá lpak_room_override.py "
              "--list primero para generarlo.", file=sys.stderr)
        return 1

    # Aceptar tanto "33" como "33_dock"
    room_key = None
    for k in room_assets:
        if k == args.room or k == args.room.split("_")[0]:
            room_key = k
            break
    if room_key is None:
        print(f"ERROR: room {args.room} no existe. Usá --list para ver.", file=sys.stderr)
        return 1

    r = room_assets[room_key]
    assets = r["assets"]

    # Filtrar por --filter si se pasa
    if args.filter:
        assets = [a for a in assets if args.filter.lower() in a.lower()]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.op == "extract":
        for asset in assets:
            if not asset.endswith(".dxt"):
                continue
            try:
                dxt_bytes = read_dxt_from_pak(args.pak, asset)
                dds = dxt_to_dds(dxt_bytes)
                from io import BytesIO
                img = Image.open(BytesIO(dds))
                img.load()
                out_path = out_dir / asset.replace("/", "__").replace(".dxt", ".png")
                img.save(out_path, format="PNG")
                print(f"  ✓ {asset} → {out_path.name}")
            except Exception as e:
                print(f"  ✗ {asset}: {e}")

    elif args.op == "inject":
        for asset in assets:
            if not asset.endswith(".dxt"):
                continue
            png_name = asset.replace("/", "__").replace(".dxt", ".png")
            png_path = Path(args.src) / png_name
            if not png_path.is_file():
                print(f"  - {asset}: PNG no encontrado en {png_path}")
                continue
            # Reusar cmd_inject con paths construidos
            args_orig = args
            class FakeArgs:
                pass
            fake = FakeArgs()
            fake.pak = args.pak
            fake.input = png_path
            fake.asset = asset
            fake.output = args.pak.parent / asset
            fake.drop_alpha = args.drop_alpha
            try:
                cmd_inject(fake)
            except SystemExit:
                pass


def main():
    p = argparse.ArgumentParser(description="Conversor unificado de sprites LPAK.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # extract
    pe = sub.add_parser("extract", help="Extrae un asset del pak como PNG")
    pe.add_argument("asset", help="Ruta del asset dentro del pak (ej: art/rooms/images/85_melee/layer0_chunk_0_0.dxt)")
    pe.add_argument("output", help="PNG de salida")
    pe.add_argument("--pak", type=Path, default=PAK_DEFAULT)
    pe.add_argument("--drop-alpha", action="store_true")
    pe.set_defaults(func=cmd_extract)

    # inject
    pi = sub.add_parser("inject", help="Inyecta un PNG como .dxt del juego")
    pi.add_argument("input", type=Path, help="PNG de entrada")
    pi.add_argument("asset", help="Ruta destino dentro del pak (ej: art/...)")
    pi.add_argument("--pak", type=Path, default=PAK_DEFAULT)
    pi.add_argument("--output", type=Path, default=None,
                   help="Dónde escribir el .dxt (default: <extracted>/<asset>)")
    pi.add_argument("--drop-alpha", action="store_true")
    pi.set_defaults(func=cmd_inject)

    # batch
    pb = sub.add_parser("batch", help="Procesa todos los assets de un room")
    pb.add_argument("--room", required=True, help="Room ID")
    pb.add_argument("--op", choices=["extract", "inject"], required=True)
    pb.add_argument("--src", type=Path, help="Para inject: carpeta con PNGs")
    pb.add_argument("--out", type=Path, help="Para extract: carpeta destino para PNGs")
    pb.add_argument("--filter", help="Filtrar por substring en el nombre")
    pb.add_argument("--pak", type=Path, default=PAK_DEFAULT)
    pb.add_argument("--drop-alpha", action="store_true")
    pb.set_defaults(func=cmd_batch)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

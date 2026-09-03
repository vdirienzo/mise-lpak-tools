#!/usr/bin/env python3
"""
lpak_room_override.py — Sobrescribe TODOS los sprites de un room con un color.

Usa el parser de .room.xml (binario) para encontrar todos los assets del room
y los reemplaza por un sprite sólido del color elegido.

Uso:
  ./lpak_room_override.py 28                  # room 28 (SCUMM Bar) en rojo
  ./lpak_room_override.py 28 --color 00ff00   # verde
  ./lpak_room_override.py 28 --color 0000ff   # azul
  ./lpak_room_override.py 28 --pak /path/to/Monkey1.pak
  ./lpak_room_override.py 85 --skin pirate    # también sobrescribe piratas
  ./lpak_room_override.py --list              # lista todos los rooms

Cuando el motor carga este room, usa los .dxt sueltos en lugar del pak.
"""

import argparse
import os
import re
import struct
import sys
from pathlib import Path


PAK_DEFAULT = Path(__file__).parent.parent / "extracted" / "Monkey1.pak"
EXTRACTED_DEFAULT = Path(__file__).parent.parent / "extracted"
ROOM_ASSETS_CACHE = Path("/tmp/room_assets.json")


def parse_pak_header(pak_file):
    """Lee el header del pak y devuelve la tabla de entries + nombres."""
    raw = pak_file.read(40)
    magic = raw[:4]
    if magic == b"KAPL":
        endian = "little"
    elif magic == b"LPAK":
        endian = "big"
    else:
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


def parse_room_xml(pak_file, entries, names, room_idx):
    """Lee el .room.xml en el idx dado y extrae la lista de assets referenciados."""
    e = entries[room_idx]
    abs_off = e[0] + 192860
    pak_file.seek(abs_off)
    data = pak_file.read(e[2])

    room_id = struct.unpack("<I", data[:4])[0]
    paths = re.findall(rb"art/[^\x00]+\.(?:dxt|xml|png)", data)
    paths = [p.decode() for p in paths]
    return room_id, paths


def build_room_assets_map(pak_path):
    """Construye el mapa room_id -> [asset paths] para todos los rooms."""
    if ROOM_ASSETS_CACHE.exists():
        import json
        with ROOM_ASSETS_CACHE.open() as f:
            return json.load(f)

    room_assets = {}
    with pak_path.open("rb") as f:
        entries, names = parse_pak_header(f)
        for i, n in enumerate(names):
            if n.startswith("art/rooms/") and n.endswith(".room.xml"):
                room_id, paths = parse_room_xml(f, entries, names, i)
                room_assets[str(room_id)] = {
                    "name": n,
                    "idx": i,
                    "assets": paths,
                }
    import json
    with ROOM_ASSETS_CACHE.open("w") as f:
        json.dump(room_assets, f, indent=2)
    return room_assets


def color_to_dxt_block(r, g, b, dxt5=True):
    """Genera un bloque DXT de 16 bytes del color RGB dado."""
    if not dxt5:
        # DXT1 (8 bytes)
        rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        c0 = rgb565 & 0xFF
        c1 = (rgb565 >> 8) & 0xFF
        # 2 bits por píxel, 16 píxeles = 4 bytes, todos apuntan a color0
        return bytes([c0, c1, 0xFF, 0xFF, 0xAA, 0xAA, 0xAA, 0xAA])
    # DXT5 (16 bytes): 8 alpha + 4 color + 4 color indices
    rgb565 = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    c0 = rgb565 & 0xFF
    c1 = (rgb565 >> 8) & 0xFF
    return bytes([
        0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # alpha: 255, 255, índices 0
        c0, c1, c0, c1,                                 # color0 y color1
        0x00, 0x00, 0x00, 0x00,                         # índices = 0
    ])


def hex_to_rgb(hexstr):
    """Convierte 'ff0000' a (255, 0, 0)."""
    h = hexstr.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Hex inválido: {hexstr}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def override_dxt(pak_path, extracted_path, asset_path, rgb):
    """Sobrescribe un .dxt en extracted/ con un sprite sólido del color."""
    r, g, b = rgb
    with pak_path.open("rb") as f:
        entries, names = parse_pak_header(f)
        if asset_path not in names:
            return False, "no encontrado en pak"
        idx = names.index(asset_path)
        e = entries[idx]
        abs_off = e[0] + 192860
        f.seek(abs_off)
        data = f.read(e[2])
        if data[:3] != b"DXT":
            return False, "no es DXT"
        dxt5 = data[:4] == b"DXT5"
        header = data[:12]
        data_len = e[2] - 12

    block = color_to_dxt_block(r, g, b, dxt5=dxt5)
    new_data = block * (data_len // len(block))
    remainder = data_len % len(block)
    if remainder:
        new_data += block[:remainder]

    out_path = extracted_path / asset_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        f.write(header + new_data)
    return True, e[2]


def main():
    p = argparse.ArgumentParser(
        description="Sobrescribe todos los sprites de un room con un color sólido."
    )
    p.add_argument("room_id", nargs="?", help="ID del room (ej: 28 para SCUMM bar)")
    p.add_argument("--color", default="ff0000",
                   help="Color hex sin # (default: ff0000 = rojo)")
    p.add_argument("--pak", type=Path, default=PAK_DEFAULT,
                   help="Ruta al Monkey1.pak")
    p.add_argument("--extracted", type=Path, default=EXTRACTED_DEFAULT,
                   help="Carpeta extracted/ (donde se crean los overrides)")
    p.add_argument("--skin", nargs="*", default=None,
                   help="También sobrescribir sprites que contengan estas palabras (ej: pirate door)")
    p.add_argument("--list", action="store_true", help="Lista todos los rooms")
    p.add_argument("--dry-run", action="store_true", help="Solo muestra lo que haría")
    p.add_argument("--restore", action="store_true",
                   help="Borra los overrides de este room (o 'all' para todos). "
                        "Útil para volver al pak original.")
    args = p.parse_args()

    if not args.pak.is_file():
        print(f"ERROR: pak no existe: {args.pak}", file=sys.stderr)
        return 1

    print(f"Pak: {args.pak}")
    print(f"Extracted: {args.extracted}")
    print(f"Color: #{args.color}")

    room_assets = build_room_assets_map(args.pak)
    print(f"Rooms conocidos: {len(room_assets)}")

    if args.list:
        for rid in sorted(room_assets.keys(), key=int):
            r = room_assets[rid]
            print(f"  Room {rid:>4}  ({len(r['assets']):>2} assets)  {r['name']}")
        return 0

    # --- Restore mode ---
    if args.restore:
        if args.room_id == "all":
            # Borrar todos los .dxt dentro de extracted/art/
            target_dir = args.extracted / "art"
            if not target_dir.is_dir():
                print(f"ERROR: no existe {target_dir}", file=sys.stderr)
                return 1
            files = sorted(target_dir.rglob("*.dxt"))
            if not files:
                print("Nada para restaurar.")
                return 0
            print(f"\n=== Restaurar TODOS los overrides ({len(files)} archivos) ===")

            if not args.dry_run:
                resp = input("¿Borrar TODOS los overrides listados? [s/N] ")
                if resp.lower() != "s":
                    print("Cancelado.")
                    return 0
            for f in files:
                print(f"  borrando {f.relative_to(args.extracted)}")
                if not args.dry_run:
                    f.unlink()
            suffix = " (DRY-RUN, no se borró nada)" if args.dry_run else ""
            print(f"\n✓ {len(files)} overrides eliminados{suffix}. El juego usará el pak original.")
            return 0

        if not args.room_id:
            print("ERROR: con --restore especificá un room_id o 'all'",
                  file=sys.stderr)
            return 1
        if args.room_id not in room_assets:
            print(f"ERROR: room {args.room_id} no existe. Usá --list para ver los disponibles.",
                  file=sys.stderr)
            return 1

        r = room_assets[args.room_id]
        print(f"\n=== Restaurar room {args.room_id}: {r['name']} ===")

        if not args.dry_run:
            resp = input("¿Borrar los overrides listados? [s/N] ")
            if resp.lower() != "s":
                print("Cancelado.")
                return 0

        count = 0
        for asset in sorted(set(r["assets"])):
            # El pak guarda rutas tipo "art/rooms/images/28_bar/..."
            # en extracted se traduce a <extracted>/art/rooms/images/28_bar/...
            # pero el script a veces usa rutas con prefijo distinto. Probamos
            # ambas variantes.
            candidates = [
                args.extracted / asset,
                args.extracted / asset.split("/", 1)[1] if "/" in asset else None,
            ]
            for p in candidates:
                if p is None:
                    continue
                if p.is_file():
                    print(f"  borrando {p.relative_to(args.extracted)}")
                    if not args.dry_run:
                        p.unlink()
                    count += 1
                    break
        if count == 0:
            print("  (no había overrides para este room)")
        else:
            suffix = " (DRY-RUN, no se borró nada)" if args.dry_run else ""
            print(f"\n✓ {count} overrides eliminados{suffix}. El juego usará el pak original.")
        return 0

    if not args.room_id:
        print("ERROR: especificá un room_id (o usá --list)", file=sys.stderr)
        return 1

    if args.room_id not in room_assets:
        print(f"ERROR: room {args.room_id} no existe. Usá --list para ver los disponibles.")
        return 1

    rgb = hex_to_rgb(args.color)
    r = room_assets[args.room_id]

    print(f"\n=== Room {args.room_id}: {r['name']} ===")
    print(f"Assets del room ({len(r['assets'])}):")

    to_override = set(r["assets"])

    # Si pidió skin keywords, agregar sprites que las contengan
    if args.skin:
        print(f"\nBuscando sprites que contengan: {args.skin}")
        with args.pak.open("rb") as f:
            entries, names = parse_pak_header(f)
        for kw in args.skin:
            kw_lower = kw.lower()
            for n in names:
                if not n.endswith(".dxt"):
                    continue
                if kw_lower in n.lower():
                    if entries[names.index(n)][2] >= 50000:  # solo grandes
                        to_override.add(n)

    print(f"\nTotal a sobrescribir: {len(to_override)}")
    for a in sorted(to_override):
        print(f"  {a}")

    if args.dry_run:
        print("\n[DRY-RUN] No escribí nada.")
        return 0

    print(f"\nSobrescribiendo con #{args.color} = RGB{rgb}...")
    count_ok = 0
    count_fail = 0
    for a in sorted(to_override):
        ok, info = override_dxt(args.pak, args.extracted, a, rgb)
        if ok:
            count_ok += 1
        else:
            count_fail += 1
            print(f"  ! {a}: {info}")

    print(f"\n✓ {count_ok} overrides creados")
    if count_fail:
        print(f"✗ {count_fail} fallaron")
    print(f"\nReiniciá el juego para ver el efecto.")


if __name__ == "__main__":
    sys.exit(main())

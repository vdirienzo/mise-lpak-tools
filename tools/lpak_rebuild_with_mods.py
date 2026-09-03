#!/usr/bin/env python3
"""
lpak_rebuild_with_mods.py — Reconstruye el pak LPAK completo con mods.

Toma el pak original (intacto), una carpeta con assets modificados (.dxt),
y genera un nuevo pak con los assets reemplazados en sus offsets originales.

Uso:
  ./lpak_rebuild_with_mods.py --original Monkey1.pak.original \
                              --mods ./work/modified_assets/ \
                              --output Monkey1.pak

Estructura esperada de --mods:
  mods/
    art/rooms/images/85_melee/layer0_chunk_0_0.dxt
    art/costumes/images/1_guybrush-skin/costumes_a0.dxt
    ...

Cada .dxt debe tener exactamente las mismas dimensiones que el original.
Si el .dxt es más grande que el original, ABORTA (no se puede hacer in-place).
"""

import argparse
import shutil
import struct
import sys
from pathlib import Path


HEADER_FMT = "<" + "I" + "f" + "I" * 8
HEADER_SIZE = struct.calcsize(HEADER_FMT)
ENTRY_FMT = "<" + "I" * 5
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)
NAME_BLOCK_SIZE = 130444


def parse_pak(pak_path):
    """Lee header + index + entries + nombres del pak."""
    with pak_path.open("rb") as f:
        header_raw = f.read(HEADER_SIZE)
        # Saltar el index (10396 bytes entre header y entries)
        f.read(10396)
        entries = []
        for _ in range(2599):
            entries.append(struct.unpack(ENTRY_FMT, f.read(ENTRY_SIZE)))
        name_block = f.read(NAME_BLOCK_SIZE)
        names = []
        for e in entries:
            end = name_block.find(b"\x00", e[1])
            if end == -1:
                end = len(name_block)
            names.append(name_block[e[1]:end].decode("utf-8", errors="replace"))
    return header_raw, entries, names, name_block


def find_entry(entries, names, asset_path):
    for i, n in enumerate(names):
        if n == asset_path:
            e = entries[i]
            return {
                "idx": i,
                "abs_offset": e[0] + 192860,  # startOfData del header
                "size": e[2],
                "entry_offset": 10436 + i * ENTRY_SIZE,
            }
    return None


def main():
    p = argparse.ArgumentParser(
        description="Reconstruye el pak LPAK con assets modificados."
    )
    p.add_argument("--original", type=Path, required=True,
                   help="Pak original (intacto, de backup)")
    p.add_argument("--mods", type=Path, required=True,
                   help="Carpeta con assets modificados (estructura: mods/art/...)")
    p.add_argument("--output", type=Path, required=True,
                   help="Pak de salida")
    p.add_argument("--dry-run", action="store_true",
                   help="Solo lista lo que se modificaría")
    args = p.parse_args()

    if not args.original.is_file():
        print(f"ERROR: pak original no existe: {args.original}", file=sys.stderr)
        return 1
    if not args.mods.is_dir():
        print(f"ERROR: carpeta de mods no existe: {args.mods}", file=sys.stderr)
        return 1

    print(f"Original: {args.original}")
    print(f"Mods:     {args.mods}")
    print(f"Output:   {args.output}")

    header_raw, entries, names, name_block = parse_pak(args.original)
    print(f"\nPak parseado: {len(entries)} entries")

    # Buscar todos los .dxt en mods/
    mod_files = sorted(args.mods.rglob("*.dxt"))
    if not mod_files:
        print(f"Ningún .dxt encontrado en {args.mods}")
        return 1
    print(f"Encontrados {len(mod_files)} archivos .dxt en mods/\n")

    # Validar que cada mod exista en el pak y quepa
    to_apply = []
    skipped = []
    errors = []
    for mod_path in mod_files:
        rel = mod_path.relative_to(args.mods).as_posix()
        entry = find_entry(entries, names, rel)
        if entry is None:
            skipped.append((rel, "no existe en pak"))
            continue
        mod_size = mod_path.stat().st_size
        if mod_size > entry["size"]:
            errors.append((rel, f"nuevo {mod_size}B > original {entry['size']}B"))
            continue
        to_apply.append((mod_path, rel, entry, mod_size))
        print(f"  ✓ {rel} ({mod_size}/{entry['size']} bytes)")

    print(f"\nResumen: {len(to_apply)} aplicar, {len(skipped)} no encontrados, {len(errors)} errores")

    if skipped:
        print("\nSaltados (no están en el pak):")
        for r, msg in skipped[:20]:
            print(f"  - {r}: {msg}")
        if len(skipped) > 20:
            print(f"  ... y {len(skipped) - 20} más")

    if errors:
        print("\nERRORES (aborta):")
        for r, msg in errors:
            print(f"  ✗ {r}: {msg}")
        return 1

    if args.dry_run:
        print("\n[DRY-RUN] No escribí nada.")
        return 0

    # Verificar dimensiones (el .dxt debe tener mismas dims que el original)
    print("\nVerificando dimensiones...")
    for mod_path, rel, entry, _ in to_apply:
        with mod_path.open("rb") as f:
            hdr = f.read(12)
        if hdr[:3] != b"DXT":
            errors.append((rel, "magic no es DXT"))
            continue
        w_mod, h_mod = struct.unpack("<II", hdr[4:12])
        # Leer dimensiones del original desde el pak
        with args.original.open("rb") as f:
            f.seek(entry["abs_offset"])
            hdr_orig = f.read(12)
        w_orig, h_orig = struct.unpack("<II", hdr_orig[4:12])
        if (w_mod, h_mod) != (w_orig, h_orig):
            errors.append((rel, f"dims {w_mod}x{h_mod} != orig {w_orig}x{h_orig}"))
            print(f"  ✗ {rel}: dimensiones {w_mod}x{h_mod} != {w_orig}x{h_orig}")
        else:
            print(f"  ✓ {rel}: {w_mod}x{h_mod}")

    if errors:
        print("\nERRORES de validación:")
        for r, msg in errors:
            print(f"  ✗ {r}: {msg}")
        return 1

    # Construir el pak de salida
    print(f"\nConstruyendo {args.output}...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.original, args.output)

    with args.output.open("r+b") as f:
        for mod_path, rel, entry, mod_size in to_apply:
            # 1. Sobrescribir los bytes del asset.
            f.seek(entry["abs_offset"])
            data = mod_path.read_bytes()
            f.write(data)
            # Rellenar con ceros si el mod es más pequeño.
            if mod_size < entry["size"]:
                f.write(b"\x00" * (entry["size"] - mod_size))

            # 2. Actualizar dataSize y dataSize2 en la entry (offset 8 y 12 dentro).
            f.seek(entry["entry_offset"] + 8)
            f.write(struct.pack("<II", mod_size, mod_size))

    print(f"\n✓ Pak reconstruido: {args.output}")
    print(f"  {len(to_apply)} assets reemplazados")
    print(f"  Tamaño: {args.output.stat().st_size} bytes "
          f"(original: {args.original.stat().st_size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

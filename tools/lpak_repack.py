#!/usr/bin/env python3
"""
lpak_repack.py — Reemplaza assets dentro de un .pak LPAK in-place.

Estrategia (basada en timfel/monkey/packpak.c):
  1. Lee el header del pak.
  2. Localiza la entry cuyo nombre coincida con el archivo a inyectar.
  3. Sobrescribe los bytes en disco en el mismo offset.
  4. Si el nuevo archivo es más pequeño que el original, rellena con ceros
     (para no desplazar las entries siguientes).
  5. Actualiza dataSize y dataSize2 en la tabla de entries.
  6. Si el nuevo archivo es MAYOR que el original, ABORTA (no es in-place).

Uso:
  ./lpak_repack.py Monkey1.pak nuevo_layer0.dxt art/rooms/images/85_melee/layer0_chunk_0_0.dxt
"""

import argparse
import struct
import sys
from pathlib import Path


HEADER_FMT = "<I" + "f" + "I" * 8
HEADER_SIZE = struct.calcsize(HEADER_FMT)
ENTRY_FMT = "<" + "I" * 5
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)


def read_header(pak_file):
    raw = pak_file.read(HEADER_SIZE)
    magic = raw[:4]
    if magic == b"KAPL":
        endian = "little"
    elif magic == b"LPAK":
        endian = "big"
    else:
        raise ValueError(f"Magic inválido: {magic!r}")
    f = struct.unpack("<f" + "I" * 8, raw[4:])
    return {
        "magic": magic.decode("ascii"),
        "endian": endian,
        "version": f[0],
        "startOfIndex": f[1],
        "startOfFileEntries": f[2],
        "startOfFileNames": f[3],
        "startOfData": f[4],
        "sizeOfIndex": f[5],
        "sizeOfFileEntries": f[6],
        "sizeOfFileNames": f[7],
        "sizeOfData": f[8],
        "numEntries": f[6] // ENTRY_SIZE,
    }


def read_entries(pak_file, header):
    pak_file.seek(header["startOfFileEntries"])
    raw = pak_file.read(header["sizeOfFileEntries"])
    return [struct.unpack(ENTRY_FMT, raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
            for i in range(header["numEntries"])]


def find_entry_by_name(pak_file, header, target_name):
    """Busca una entry por nombre exacto."""
    pak_file.seek(header["startOfFileNames"])
    name_block = pak_file.read(header["sizeOfFileNames"])
    pak_file.seek(header["startOfFileEntries"])
    entries_raw = pak_file.read(header["sizeOfFileEntries"])
    for i in range(header["numEntries"]):
        e_data = entries_raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
        file_data_pos, file_name_pos, data_size, data_size2, compressed = \
            struct.unpack(ENTRY_FMT, e_data)
        end = name_block.find(b"\x00", file_name_pos)
        if end == -1:
            end = len(name_block)
        name = name_block[file_name_pos:end].decode("utf-8", errors="replace")
        if name == target_name:
            return {
                "idx": i,
                "abs_offset": file_data_pos + header["startOfData"],
                "old_size": data_size,
                "old_size2": data_size2,
                "compressed": compressed,
                "entry_offset_in_table":
                    header["startOfFileEntries"] + i * ENTRY_SIZE,
            }
    return None


def main():
    p = argparse.ArgumentParser(description="Reemplazo in-place en pak LPAK.")
    p.add_argument("pak", type=Path, help="Pak a modificar (se sobreescribe)")
    p.add_argument("source", type=Path, help="Archivo nuevo a inyectar")
    p.add_argument("target", help="Ruta exacta del asset dentro del pak (ej: art/rooms/images/85_melee/layer0_chunk_0_0.dxt)")
    p.add_argument("--dry-run", action="store_true",
                   help="Solo muestra lo que haría, sin escribir")
    p.add_argument("--yes", "-y", action="store_true",
                   help="No pide confirmación")
    args = p.parse_args()

    if not args.pak.is_file():
        print(f"ERROR: pak no existe: {args.pak}", file=sys.stderr)
        return 1
    if not args.source.is_file():
        print(f"ERROR: source no existe: {args.source}", file=sys.stderr)
        return 1

    new_data = args.source.read_bytes()
    print(f"Archivo a inyectar: {args.source} ({len(new_data)} bytes)")

    with args.pak.open("r+b") as f:
        header = read_header(f)
        entry = find_entry_by_name(f, header, args.target)

        if entry is None:
            print(f"ERROR: no se encontró '{args.target}' en el pak")
            return 1

        print(f"Entry encontrada: idx={entry['idx']} offset={entry['abs_offset']} "
              f"tamaño_original={entry['old_size']}")

        if len(new_data) > entry["old_size"]:
            print(f"ERROR: el nuevo archivo ({len(new_data)}) es MAYOR que el "
                  f"original ({entry['old_size']}). Este script solo hace "
                  f"reemplazo in-place; para paquetes más grandes hay que "
                  f"reconstruir el pak completo.")
            return 1

        if len(new_data) < entry["old_size"]:
            print(f"AVISO: el nuevo archivo es MENOR ({len(new_data)} < "
                  f"{entry['old_size']}). Rellenando con ceros.")

        if not args.yes and not args.dry_run:
            resp = input("¿Continuar y modificar el pak? [s/N] ")
            if resp.lower() != "s":
                print("Cancelado.")
                return 0

        if args.dry_run:
            print(f"[DRY-RUN] Escribiría {len(new_data)} bytes en "
                  f"offset {entry['abs_offset']}")
            print(f"[DRY-RUN] Actualizaría dataSize en offset "
                  f"{entry['entry_offset_in_table']}")
            return 0

        # 1. Sobrescribe los bytes del asset.
        f.seek(entry["abs_offset"])
        f.write(new_data)
        # Rellena con ceros si es más pequeño.
        if len(new_data) < entry["old_size"]:
            f.write(b"\x00" * (entry["old_size"] - len(new_data)))

        # 2. Actualiza dataSize y dataSize2 en la tabla de entries.
        # La entry tiene 5 uint32: fileDataPos, fileNamePos, dataSize, dataSize2, compressed.
        # dataSize está en el offset +8 desde el inicio de la entry (los 2 primeros uint32
        # son fileDataPos y fileNamePos, NO se tocan).
        f.seek(entry["entry_offset_in_table"] + 8)
        f.write(struct.pack("<II", len(new_data), len(new_data)))

    print(f"Listo: {len(new_data)} bytes escritos en '{args.target}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
lpak_inspect.py — Inspector de archivos LPAK (Monkey Island Special Edition).

Lee el header de un .pak y muestra:
  - Magic, versión
  - Offsets y tamaños de cada sección
  - Lista de archivos contenidos (nombre, offset real, tamaño)

Basado en el formato RE'd por bgbennyboy/Monkey-Island-Explorer y
timfel/monkey/extractpak.c.

Uso:
  ./lpak_inspect.py ruta/al/Monkey1.pak
  ./lpak_inspect.py ruta/al/Monkey1.pak --filter meleetown
  ./lpak_inspect.py ruta/al/Monkey1.pak --filter scene --limit 30
"""

import argparse
import struct
import sys
from pathlib import Path


# Formato del header: 4 bytes magic + 4 bytes float + 8×4 bytes uint32 = 40 bytes.
# "<"  = little-endian. "I" = uint32, "f" = float32.
HEADER_FMT = "<I" + "f" + "I" * 8
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # debería ser 40
assert HEADER_SIZE == 40, f"Header size esperado 40, got {HEADER_SIZE}"

# Formato de cada entry: 5 uint32 LE = 20 bytes.
ENTRY_FMT = "<I I I I I"
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)
assert ENTRY_SIZE == 20, f"Entry size esperado 20, got {ENTRY_SIZE}"


def read_header(f):
    """Lee y valida el header del pak. Devuelve dict con los campos."""
    raw = f.read(HEADER_SIZE)
    if len(raw) != HEADER_SIZE:
        raise ValueError(f"Archivo demasiado pequeño: leí {len(raw)} bytes, esperaba {HEADER_SIZE}")

    # Los primeros 4 bytes son el magic en su ORDEN tal como están en disco.
    # "KAPL" en disco = little-endian (PC).
    # "LPAK" en disco = big-endian (XBOX 360).
    magic_on_disk = raw[:4]
    if magic_on_disk == b"KAPL":
        endianness = "little"
    elif magic_on_disk == b"LPAK":
        endianness = "big"
    else:
        raise ValueError(f"Magic inválido en disco: {magic_on_disk!r}")

    version, start_of_index, start_of_file_entries, \
        start_of_file_names, start_of_data, size_of_index, \
        size_of_file_entries, size_of_file_names, size_of_data = \
        struct.unpack("<f" + "I" * 8, raw[4:])

    # Validación de coherencia.
    if version != 1.0:
        print(f"AVISO: versión {version} no es 1.0 (¿futuro formato?)")

    num_entries = size_of_file_entries // ENTRY_SIZE
    if num_entries * ENTRY_SIZE != size_of_file_entries:
        print(f"AVISO: sizeOfFileEntries ({size_of_file_entries}) no es múltiplo de {ENTRY_SIZE}")

    return {
        "magic": magic_on_disk.decode("ascii"),
        "endianness": endianness,
        "version": version,
        "startOfIndex": start_of_index,
        "startOfFileEntries": start_of_file_entries,
        "startOfFileNames": start_of_file_names,
        "startOfData": start_of_data,
        "sizeOfIndex": size_of_index,
        "sizeOfFileEntries": size_of_file_entries,
        "sizeOfFileNames": size_of_file_names,
        "sizeOfData": size_of_data,
        "numEntries": num_entries,
    }


def read_entries(f, header):
    """Lee el array de entries (numEntries × 20 bytes)."""
    f.seek(header["startOfFileEntries"])
    raw = f.read(header["sizeOfFileEntries"])
    n = header["numEntries"]
    entries = []
    for i in range(n):
        off_data, off_name, size, size2, compressed = \
            struct.unpack(ENTRY_FMT, raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
        entries.append({
            "idx": i,
            "fileDataPos": off_data,
            "fileNamePos": off_name,
            "dataSize": size,
            "dataSize2": size2,
            "compressed": compressed,
            # Offset absoluto en disco (sumamos startOfData).
            "abs_offset": off_data + header["startOfData"],
        })
    return entries


def read_names(f, header, entries):
    """Lee los nombres (strings null-terminated).

    OJO: fileNamePos es un OFFSET EN BYTES dentro del bloque de nombres,
    NO un índice en la lista. Esto es importante porque las rutas tienen
    longitudes variables, así que los offsets son únicos por entry.
    """
    f.seek(header["startOfFileNames"])
    name_block = f.read(header["sizeOfFileNames"])

    # Para cada entry, lee el nombre en el offset exacto.
    paired = []
    for e in entries:
        off = e["fileNamePos"]
        if off >= len(name_block):
            paired.append(f"<offset {off} fuera de rango>")
            continue
        end = name_block.find(b"\x00", off)
        if end == -1:
            end = len(name_block)
        try:
            name = name_block[off:end].decode("ascii")
        except UnicodeDecodeError:
            name = name_block[off:end].decode("utf-8", errors="replace")
        paired.append(name)
    return paired


def format_size(n):
    """Tamaño humano: KB, MB, GB."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Inspector de archivos LPAK MISE.")
    parser.add_argument("pak", type=Path, help="Ruta al archivo .pak")
    parser.add_argument("--filter", default=None,
                        help="Muestra solo entries cuyo nombre contenga este texto")
    parser.add_argument("--limit", type=int, default=20,
                        help="Número máximo de entries a listar (default 20)")
    parser.add_argument("--show-all", action="store_true",
                        help="Lista TODAS las entries (sin limit ni filter)")
    args = parser.parse_args()

    if not args.pak.is_file():
        print(f"ERROR: no existe {args.pak}", file=sys.stderr)
        return 1

    print(f"=== {args.pak.name} ===")
    print(f"Tamaño en disco: {format_size(args.pak.stat().st_size)}")
    print()

    with args.pak.open("rb") as f:
        header = read_header(f)
        entries = read_entries(f, header)
        names = read_names(f, header, entries)

        # Cabecera.
        print("HEADER")
        print(f"  magic        : '{header['magic']}' (en disco = '{header['magic']}', invertido = 'LPAK' → {header['endianness']}-endian)")
        print(f"  version      : {header['version']}")
        print(f"  startOfIndex : {header['startOfIndex']}")
        print(f"  startOfFileEntries : {header['startOfFileEntries']}")
        print(f"  startOfFileNames   : {header['startOfFileNames']}")
        print(f"  startOfData  : {header['startOfData']}")
        print(f"  sizeOfIndex  : {header['sizeOfIndex']}")
        print(f"  sizeOfFileEntries  : {header['sizeOfFileEntries']}")
        print(f"  sizeOfFileNames    : {header['sizeOfFileNames']}")
        print(f"  sizeOfData   : {header['sizeOfData']} ({format_size(header['sizeOfData'])})")
        print(f"  numEntries   : {header['numEntries']}")
        print()

        # Validación de totales.
        total_size = (header["startOfIndex"]
                      + header["sizeOfIndex"]
                      + header["sizeOfFileEntries"]
                      + header["sizeOfFileNames"]
                      + header["sizeOfData"])
        print(f"Suma secciones = {total_size} ({format_size(total_size)})")
        print(f"Tamaño archivo = {args.pak.stat().st_size} ({format_size(args.pak.stat().st_size)})")
        diff = args.pak.stat().st_size - total_size
        if diff == 0:
            print("OK: cuadra exacto.")
        else:
            print(f"AVISO: diferencia de {diff} bytes.")
        print()

        # Empareja entries con nombres (read_names ya devuelve uno por entry).
        paired = list(zip(names, entries))

        # Filtra si procede.
        if args.filter:
            paired = [p for p in paired if args.filter.lower() in p[0].lower()]
            print(f"=== Filtrado por '{args.filter}': {len(paired)} coincidencias ===")
        else:
            print(f"=== Listado de archivos ({len(paired)} total) ===")

        if not args.show_all:
            paired = paired[:args.limit]
            if len(paired) == args.limit:
                print(f"(mostrando primeros {args.limit}, usa --show-all o --limit N)")
        print()

        # Tabla.
        print(f"{'idx':>5}  {'abs_offset':>12}  {'size':>10}  {'compressed':>10}  name")
        print("-" * 80)
        for name, e in paired:
            print(f"{e['idx']:>5}  {e['abs_offset']:>12}  {format_size(e['dataSize']):>10}  "
                  f"{e['compressed']:>10}  {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

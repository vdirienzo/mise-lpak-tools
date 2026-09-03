#!/usr/bin/env python3
"""
lpak_unpack.py — Desempaqueta archivos de un .pak LPAK (MISE).

Mantiene la estructura de carpetas interna del pak. Por defecto extrae
todo; se puede filtrar por substring en el nombre o por extensión.

Formato: ver tools/lpak_inspect.py o LPak_notes.md.

Uso:
  ./lpak_unpack.py Monkey1.pak                        # extrae todo
  ./lpak_unpack.py Monkey1.pak --filter 85_melee       # solo Mêlée
  ./lpak_unpack.py Monkey1.pak --ext dxt              # solo texturas
  ./lpak_unpack.py Monkey1.pak --out unpacked/
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
    fields = struct.unpack("<f" + "I" * 8, raw[4:])
    return {
        "magic": magic.decode("ascii"),
        "endian": endian,
        "version": fields[0],
        "startOfFileEntries": fields[2],
        "startOfFileNames": fields[3],
        "startOfData": fields[4],
        "sizeOfFileEntries": fields[6],
        "sizeOfFileNames": fields[7],
        "numEntries": fields[6] // ENTRY_SIZE,
    }


def read_entries(pak_file, header):
    pak_file.seek(header["startOfFileEntries"])
    raw = pak_file.read(header["sizeOfFileEntries"])
    entries = []
    for i in range(header["numEntries"]):
        e = struct.unpack(ENTRY_FMT, raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE])
        entries.append({
            "idx": i,
            "fileDataPos": e[0],
            "fileNamePos": e[1],
            "dataSize": e[2],
            "dataSize2": e[3],
            "compressed": e[4],
            "abs_offset": e[0] + header["startOfData"],
        })
    return entries


def read_names(pak_file, header, entries):
    pak_file.seek(header["startOfFileNames"])
    name_block = pak_file.read(header["sizeOfFileNames"])
    out = []
    for e in entries:
        off = e["fileNamePos"]
        if off >= len(name_block):
            out.append(None)
            continue
        end = name_block.find(b"\x00", off)
        if end == -1:
            end = len(name_block)
        out.append(name_block[off:end].decode("utf-8", errors="replace"))
    return out


def main():
    p = argparse.ArgumentParser(description="Unpacker de archivos LPAK MISE.")
    p.add_argument("pak", type=Path)
    p.add_argument("--out", "-o", type=Path, default=Path("unpacked"),
                   help="Directorio de salida (default: ./unpacked)")
    p.add_argument("--filter", default=None,
                   help="Solo extrae entries cuyo nombre contenga este substring")
    p.add_argument("--ext", default=None,
                   help="Solo extrae entries con esta extensión (sin punto)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="No escribe archivos, solo lista lo que haría")
    p.add_argument("--manifest", type=Path, default=None,
                   help="Escribe un TSV con idx,nombre,offset,tamaño,sha256")
    args = p.parse_args()

    if not args.pak.is_file():
        print(f"ERROR: no existe {args.pak}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    manifest_fp = None
    if args.manifest:
        manifest_fp = args.manifest.open("w", encoding="utf-8")
        manifest_fp.write("idx\tname\tabs_offset\tsize\tdataSize2\tcompressed\n")

    import hashlib

    with args.pak.open("rb") as f:
        header = read_header(f)
        entries = read_entries(f, header)
        names = read_names(f, header, entries)

        # Filtrado.
        indices = list(range(header["numEntries"]))
        if args.filter:
            indices = [i for i in indices
                       if names[i] and args.filter.lower() in names[i].lower()]
            print(f"Filtrado por '{args.filter}': {len(indices)} coincidencias")
        if args.ext:
            ext = args.ext.lower().lstrip(".")
            indices = [i for i in indices
                       if names[i] and names[i].lower().endswith(f".{ext}")]
            print(f"Filtrado por extensión '.{ext}': {len(indices)} coincidencias")
        if args.limit:
            indices = indices[:args.limit]

        print(f"Total a extraer: {len(indices)}")
        if args.dry_run:
            for i in indices[:30]:
                print(f"  [{i}] {names[i]} ({entries[i]['dataSize']} bytes @ {entries[i]['abs_offset']})")
            if len(indices) > 30:
                print(f"  ... y {len(indices) - 30} más")
            return 0

        # Extracción.
        for n, i in enumerate(indices, 1):
            name = names[i]
            e = entries[i]
            out_path = args.out / name
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Seguridad: que no se escape del directorio de salida.
            try:
                out_path.resolve().relative_to(args.out.resolve())
            except ValueError:
                print(f"  AVISO: path peligroso {name}, saltando")
                continue

            f.seek(e["abs_offset"])
            blob = f.read(e["dataSize"])

            sha = hashlib.sha256(blob).hexdigest()

            out_path.write_bytes(blob)

            if manifest_fp:
                manifest_fp.write(f"{i}\t{name}\t{e['abs_offset']}\t{e['dataSize']}\t{e['dataSize2']}\t{e['compressed']}\n")

            if n % 100 == 0 or n == len(indices):
                print(f"  [{n}/{len(indices)}] {name}")

    if manifest_fp:
        manifest_fp.close()
        print(f"Manifest escrito en {args.manifest}")

    print(f"Listo: {len(indices)} archivos en {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

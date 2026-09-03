#!/usr/bin/env python3
"""
lpak_rebuild.py — Reconstruye un .pak LPAK a partir de una carpeta extraída.

Lee el manifest.tsv generado por lpak_unpack.py y reconstruye el pak
manteniendo los offsets originales (porque no estamos reordenando nada).

Uso:
  ./lpak_rebuild.py manifest.tsv output.pak
"""

import argparse
import struct
import sys
from pathlib import Path


HEADER_FMT_OUT = "<" + "I" + "f" + "I" * 8
HEADER_SIZE = struct.calcsize(HEADER_FMT_OUT)
ENTRY_FMT = "<" + "I" * 5
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path,
                   help="manifest.tsv de lpak_unpack.py")
    p.add_argument("source_pak", type=Path,
                   help="Pak original (para copiar header, entries, names)")
    p.add_argument("output", type=Path,
                   help="Pak reconstruido")
    p.add_argument("--extracted-root", type=Path, default=None,
                   help="Carpeta donde se extrajo (default: padre del manifest)")
    args = p.parse_args()

    if not args.manifest.is_file():
        print(f"ERROR: manifest no existe: {args.manifest}", file=sys.stderr)
        return 1
    if not args.source_pak.is_file():
        print(f"ERROR: pak original no existe", file=sys.stderr)
        return 1

    extracted_root = args.extracted_root or args.manifest.parent

    # Lee manifest.
    rows = []
    with args.manifest.open() as fp:
        header = fp.readline().rstrip("\n").split("\t")
        idx_i = header.index("idx")
        name_i = header.index("name")
        offset_i = header.index("abs_offset")
        size_i = header.index("size")
        for line in fp:
            fields = line.rstrip("\n").split("\t")
            rows.append({
                "idx": int(fields[idx_i]),
                "name": fields[name_i],
                "abs_offset": int(fields[offset_i]),
                "size": int(fields[size_i]),
            })
    rows.sort(key=lambda r: r["idx"])
    print(f"Leídas {len(rows)} entries del manifest")

    # Lee header del pak original para reutilizarlo.
    with args.source_pak.open("rb") as f:
        header_bytes = f.read(HEADER_SIZE)
        f.seek(HEADER_SIZE)  # después del header empieza el index, luego entries, etc.
        index_and_rest = f.read()

    # Reconstruye el pak.
    with args.output.open("wb") as out:
        out.write(header_bytes)
        out.write(index_and_rest)  # index + entries + names

        # Ahora escribe los datos en cada offset.
        # Como el pak original ya tiene los datos en los offsets correctos,
        # basta con sobrescribir desde cada abs_offset.
        for r in rows:
            src_path = extracted_root / r["name"]
            if not src_path.is_file():
                print(f"ERROR: falta {src_path}", file=sys.stderr)
                return 1
            data = src_path.read_bytes()
            if len(data) != r["size"]:
                print(f"ERROR: tamaño incorrecto para {r['name']}: "
                      f"esperado {r['size']}, leído {len(data)}", file=sys.stderr)
                return 1
            out.seek(r["abs_offset"])
            out.write(data)

    print(f"Pak reconstruido: {args.output}")
    print(f"Para verificar: sha256sum {args.source_pak} {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

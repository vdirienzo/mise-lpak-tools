# mise-lpak-tools

Reverse-engineering tooling and modding pipeline for the **LPAK** archive format
used by *The Secret of Monkey Island: Special Edition* (MISE engine, LucasArts).

## What this is

`Monkey1.pak` is a 1.2 GB LPAK archive containing 2,599 uncompressed assets
(textures, sounds, scripts, room layouts, costumes, …). The format was already
publicly documented by [bgbennyboy](https://github.com/bgbennyboy/Monkey-Island-Explorer)
and [timfel](https://github.com/timfel/monkey) — this repo packages the Python
tooling developed while building the **HiColor reim** pipeline (swap the
8-color EGA backgrounds for HD reim paintings while keeping game coordinates).

## Layout

```
tools/                            ← Python scripts (all work standalone)
  lpak_inspect.py                 ← header/entries inspector (filter by name)
  lpak_unpack.py                  ← full unpack to a folder (with manifest)
  lpak_repack.py                  ← in-place replacement (smaller file only)
  lpak_rebuild.py                 ← full rebuild from a manifest (round-trip)
  lpak_rebuild_with_mods.py       ← rebuild with one folder of .dxt overrides
  lpak_room_override.py           ← mass-recolor a whole room; --restore to undo
  lpak_sprite_convert.py          ← extract / inject / batch a room's sprites
  png_to_dxt.py                   ← PNG → .dxt (DXT1/DXT5); uses etcpak if avail
  dxt_to_png.py                   ← .dxt → PNG (for editing in GIMP/AI tools)
  dxt5_compress.py                ← fallback range-fit compressor (numpy only)
  compare_images.py               ← diff metric between original and modded PNG

scripts/                          ← shell launchers / helpers
  swap_pak.sh                     ← toggle original / modded pak in extracted/
  capture_screenshot.sh           ← Wine screenshot helper
  mise-wine.sh                    ← fullscreen Wine launcher
  mise-wine-windowed.sh           ← windowed Wine launcher

LPak_notes.md                     ← RE bitácora (Spanish): every finding session-by-session
PLAN.md                           ← project plan with phase log (Spanish)
```

## Pipeline (the mod workflow)

```
┌──────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌────────────┐
│  PAK     │ →  │ UNPACK  │ →  │  EDIT   │ →  │ CONVERT  │ →  │  INJECT    │
│ Monkey1  │    │  tool   │    │  PNGs   │    │ PNG→DXT  │    │  in-place  │
│   .pak   │    │         │    │  (AI)   │    │  (etcpak)│    │   or pak   │
└──────────┘    └─────────┘    └─────────┘    └──────────┘    └────────────┘
```

Two ways to inject a mod without rebuilding the whole pak:

1. **In-place replacement** (`lpak_repack.py`) — overwrites a single entry's
   bytes in the pak. Requires the new asset to be **≤** the original size;
   pads with zeros if smaller. Fast, surgical, no round-trip risk.

2. **Override folder** — the MISE engine accepts `.dxt` files at
   `extracted/<asset_path>` that take precedence over the pak. Place the
   modified `.dxt` files there and the pak stays untouched (best for
   iterative modding). Use `lpak_room_override.py --restore` to clean up.

## LPAK format (TL;DR)

```c
struct PakHeader {              // 40 bytes
    uint32_t magic;             // "KAPL" (LE) / "LPAK" (BE on XBOX 360)
    float    version;           // 1.0
    uint32_t startOfIndex;      // offset
    uint32_t startOfFileEntries;// offset
    uint32_t startOfFileNames;  // offset
    uint32_t startOfData;       // offset
    uint32_t sizeOfIndex;
    uint32_t sizeOfFileEntries;
    uint32_t sizeOfFileNames;
    uint32_t sizeOfData;
};

struct PakFileEntry {           // 20 bytes per file
    uint32_t fileDataPos;       // + startOfData = real offset
    uint32_t fileNamePos;       // + startOfFileNames
    uint32_t dataSize;
    uint32_t dataSize2;         // always == dataSize
    uint32_t compressed;        // always 0 (uncompressed)
};
```

2,599 entries in the retail `Monkey1.pak`. Round-trip test (`unpack` →
`rebuild`) is bit-exact (`sha256(original) == sha256(rebuild)`), so the
format is fully understood.

## DXT textures

MISE uses **DXT1** (no-alpha backgrounds) and **DXT5** (with-alpha costumes)
in a custom 12-byte container: 4-byte magic (`DXT1`/`DXT5`) + 4-byte width
+ 4-byte height + raw DXT data. No DDS wrapper.

Compression via [etcpak](https://pypi.org/project/etcpak/) when available
(~2-4% avg error); falls back to a numpy range-fit implementation otherwise
(~5-7% avg error).

## Requirements

- Python 3.10+
- `Pillow`, `numpy`
- `etcpak` (recommended, ~10× faster and ~2× better quality than the
  numpy range-fit fallback):

  ```bash
  pip install etcpak
  ```

- For running the actual game on Linux: Wine (the `scripts/mise-wine*.sh`
  launchers are tested with the `org.winehq.Wine` flatpak).

## Quickstart

```bash
# Inspect a pak
./tools/lpak_inspect.py /path/to/Monkey1.pak --filter melee

# Unpack everything (1.2 GB on disk)
./tools/lpak_unpack.py /path/to/Monkey1.pak ./unpacked

# Round-trip test
./tools/lpak_rebuild.py ./unpacked ./Monkey1_rebuild.pak
sha256sum /path/to/Monkey1.pak ./Monkey1_rebuild.pak   # must match

# Replace one asset in-place (must be ≤ original size)
./tools/lpak_repack.py ./Monkey1.pak \
                       ./mod.dxt \
                       art/rooms/images/85_melee/layer0_chunk_0_0.dxt

# Mass-override a whole room with a single color (testing)
./tools/lpak_room_override.py 28 --color ff0000

# Revert the override
./tools/lpak_room_override.py 28 --restore
./tools/lpak_room_override.py all --restore

# PNG → DXT (DXT1 if no alpha, DXT5 if RGBA)
./tools/png_to_dxt.py input.png output.dxt

# DXT → PNG (for editing)
./tools/dxt_to_png.py input.dxt output.png
```

## Tested with

- `Monkey1.pak` from the GOG release of *The Secret of Monkey Island: Special Edition*
- Wine 10.x (flatpak `org.winehq.Wine`)
- Python 3.11 / 3.14

## License

MIT — see `LICENSE` (the format itself was RE'd by the community, see
`LPak_notes.md` for citations).

## Acknowledgements

Format reverse-engineering references:

- [bgbennyboy/Monkey-Island-Explorer](https://github.com/bgbennyboy/Monkey-Island-Explorer)
  — Pascal spec + PAK manager
- [timfel/monkey](https://github.com/timfel/monkey) — portable C
  `extractpak.c` + in-place `packpak.c`
- [jmnunezizu/scummkit](https://github.com/jmnunezizu/scummkit) — modern
  Python+C tool

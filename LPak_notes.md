# LPak — Bitácora del reversing

> Documento vivo. Cada sesión añade hallazgos al final.
> La versión final, consolidada, irá en `LPak_format.md` (Fase 6).

## Conceptos base (Fase 1 — setup)

### Magic number
Primeros bytes que identifican el formato. En `Monkey1.pak`: `4b 41 50 4c`
que en little-endian se lee **"LPAK"** (LucasArts PAK).

### Little-endian
Los PCs con Windows/x86 guardan los números multi-byte con el byte menos
significativo primero. Por eso vemos `4b 41 50 4c` en disco y se lee "LPAK"
al invertir mentalmente.

### Tabla de contenidos (TOC)
Lista interna de `(offset, tamaño, [nombre])` que apunta a cada asset del pak.
Vive en una posición fija del archivo (a menudo al inicio o al final).

### Float IEEE-754
`00 00 80 3f` en little-endian = `1.0`. Aparece justo tras el magic → probable
campo "versión".

### Magic bytes conocidos (referencia para Fase 2)
| Tipo | Magic (hex) | ASCII |
|---|---|---|
| PNG | `89 50 4E 47 0D 0A 1A 0A` | `.PNG....` |
| DDS | `44 44 53 20` | `DDS ` |
| OGG | `4F 67 67 53` | `OggS` |
| WAV | `52 49 46 46` | `RIFF` |
| XML | `3C 3F 78 6D 6C` o `3C 00 3F 00` | `<?xml` o UTF-16 |
| Lua bytecode | `1B 4C 75 61` | `.Lua` |
| ZIP/PK | `50 4B 03 04` | `PK..` |
| BMP | `42 4D` | `BM` |

---

## Sesión 1 — 2026-09-03 (Fase 1)

### Hex dump de los primeros 80 bytes

```
000000 4b 41 50 4c 00 00 80 3f 28 00 00 00 c4 28 00 00  >KAPL...?(....(..<
000010 d0 f3 00 00 5c f1 02 00 9c 28 00 00 0c cb 00 00  >....\....(......<
000020 8c fd 01 00 cc e0 10 4a d6 b3 27 00 6f 76 28 00  >.......J..'.ov(.<
000030 c6 f6 3c 00 a6 c2 b7 00 18 04 c8 00 20 92 c8 00  >..<......... ...<
000040 34 20 ee 00 74 a3 f5 00 58 16 1a 01 83 46 2e 01  >4 ..t...X....F..<
```

### Hallazgo MAYOR — formato ya documentado

**El formato LPAK de MISE ya fue RE por la comunidad**. Tenemos:

- **Espec completa**: `bgbennyboy/Monkey-Island-Explorer/blob/master/uMIExplorer_PAKManager.pas`
- **Extractor C portable**: `timfel/monkey` (`extractpak.c`)
- **Packer C con reemplazo in-place**: `timfel/monkey` (`packpak.c`)
- **Herramienta moderna Python+C**: `jmnunezizu/scummkit`
- **Patcher para LPAK de DoubleFine** (mismo formato base): `fleger/untangle`

### Estructura confirmada (de timfel/extractpak.c)

```c
typedef struct PakHeader {
    uint32_t magic;              // "KAPL" (LE) o "LPAK" (BE, XBOX 360)
    float    version;            // 1.0
    uint32_t startOfIndex;       // 1 DWORD por archivo
    uint32_t startOfFileEntries; // 5 DWORD por archivo (20 bytes/entry)
    uint32_t startOfFileNames;   // strings null-terminated
    uint32_t startOfData;
    uint32_t sizeOfIndex;
    uint32_t sizeOfFileEntries;
    uint32_t sizeOfFileNames;
    uint32_t sizeOfData;
} PakHeader;   // total: 40 bytes

typedef struct PakFileEntry {
    uint32_t fileDataPos;        // + startOfData = offset real
    uint32_t fileNamePos;        // + startOfFileNames
    uint32_t dataSize;
    uint32_t dataSize2;          // siempre = dataSize
    uint32_t compressed;         // siempre 0 (datos sin comprimir!)
} PakFileEntry; // total: 20 bytes
```

**Implicaciones críticas**:
- Sin compresión → reemplazo de bytes directo en offset conocido.
- 2599 archivos en el pak (51980 bytes / 20 = 2599).
- El repack es **idéntico** a `sed -i` sobre un rango de bytes: lees header → ubicas entry → reescribes bytes → actualizas `dataSize` en la entry.

### Validación contra el hex dump

| Offset | Bytes | Campo | Valor decimal |
|---|---|---|---|
| 0x00 | `4b 41 50 4c` | magic | "KAPL" |
| 0x04 | `00 00 80 3f` | version | 1.0 |
| 0x08 | `28 00 00 00` | startOfIndex | 40 |
| 0x0C | `c4 28 00 00` | startOfFileEntries | 10436 |
| 0x10 | `d0 f3 00 00` | startOfFileNames | 62416 |
| 0x14 | `5c f1 02 00` | startOfData | 192860 |
| 0x18 | `9c 28 00 00` | sizeOfIndex | 10396 (= 2599×4) |
| 0x1C | `0c cb 00 00` | sizeOfFileEntries | 51980 (= 2599×20) ✓ |
| 0x20 | `8c fd 01 00` | sizeOfFileNames | 130444 |
| 0x24 | `cc e0 10 4a` | sizeOfData | 1242620108 = file_size - startOfData ✓ |

**Todo cuadra perfecto**. El formato está 100% entendido.

### Sesión 2 — 2026-09-03 (Fases 1-5 completas en formato técnico)

#### Scripts creados
- `tools/lpak_inspect.py` — inspector / listador con magic + filter
- `tools/lpak_unpack.py` — extractor con filtro / extensión / manifest
- `tools/lpak_repack.py` — reemplazo in-place (necesita archivo ≤ original)
- `tools/lpak_rebuild.py` — reconstrucción completa desde manifest (round-trip)

#### Hallazgos Mêlée Town (room 85)
- Asset: `art/rooms/85_melee.room.xml` (binario, NO es XML real — la extensión
  es solo routing del motor). Contiene:
  - uint32 magic `55 00 00 00` (= room 85)
  - string interno `melee`
  - texto `Water`
  - lista de 12 rutas a assets (4× layer0, 4× layer1, 4× extra_water_f0)
- Capas:
  - `layer0` = fondo principal (background)
  - `layer1` = foreground (personajes / objetos cercanos)
  - `extra_water_f0` = capa de agua animada
- Cada capa está dividida en **4 tiles de 1024×1024 px**:
  - `chunk_0_0`, `chunk_0_1024`, `chunk_1024_0`, `chunk_1024_1024`
  - Tamaño: 1.048.588 bytes = exactamente 1024×1024 DXT5 (16 bytes/bloque 4×4)
- Room XML ocupa 1757 bytes.

#### Round-trip test (Fase 4)
- Extraídos los **2599 archivos** del pak (1.2 GB en disco).
- Reconstruido `Monkey1_rebuild.pak` desde el manifest.
- `sha256(original) = sha256(rebuild)` → **idéntico bit-a-bit**.
- Esto prueba que el formato se entiende al 100%.

#### Primer mod inyectado (Fase 5 — técnico, pendiente validación visual)
- Archivo: `test_mod/Monkey1_mod.pak`
- Cambio: 3 bytes en offset 1000 dentro de `layer0_chunk_0_0.dxt`:
  - Original: `FF FF FF`
  - Modificado: `DE AD BE`
- Comparación binaria: **exactamente 3 bytes de diferencia**, todos en la zona
  esperada (offset 775964691-3 del pak). Header, tabla de entries y nombres
  intactos.
- Validación pendiente: cuando Wine esté listo, lanzar el juego y comparar
  visualmente con baseline.

#### Bug encontrado y corregido
- Primera versión del repacker escribía dataSize sobreescribiendo
  `fileDataPos` y `fileNamePos` (las direcciones del archivo). Detectado con
  `cmp -l`: 7 bytes corruptos en la zona de entries en lugar de 3.
- Fix: avanzar 8 bytes (tamaño de fileDataPos + fileNamePos) antes de escribir
  dataSize / dataSize2.

#### Pipeline para mods reales (cuando Wine esté listo)
1. Convertir el `.dxt` a `.dds` (añadir header DDS de 124 bytes — ver
   `write_dds()` en `extractpak.c` de timfel).
2. Abrir el DDS en GIMP/Photoshop y editar.
3. Exportar como `.dds` con la misma compresión (DXT5 si tiene alpha, DXT1 si
   no) y mismas dimensiones.
4. Strip el header DDS de 124 bytes → volver a `.dxt`.
5. `lpak_repack.py pak.dxt.dxt ruta/en/pak` con `-y`.
6. Probar en Wine.

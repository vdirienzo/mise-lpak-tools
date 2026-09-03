# PLAN — Monkey Island SE Modding + RE del formato LPAK

> **Proyecto**: Aprender reversing de formatos binarios mientras hacemos mods
> de fondos/personajes para *The Secret of Monkey Island: Special Edition*.
> **Copia**: GOG original (`TheScapeOfMonkeyIslandRemasteredGOG.exe`)
> **Target inicial**: Mêlée Town (intro)
> **Motor**: MISE (LucasArts), archivo `Monkey1.pak` formato LPAK

---

## Convenciones

- Carpeta de trabajo: `/home/user/Projects/monkeyisland/tsomir/`
- Modo: **Tutorial detallado** — cada paso se explica antes de ejecutar.
- Idioma: español (código y comentarios también, salvo APIs/términos técnicos).
- Bitácora viva: `LPak_notes.md` (hallazgos durante el RE).
- Documento final: este archivo (`PLAN.md`) + `LPak_format.md` al terminar.

---

## Estado de cada fase

| Fase | Estado | Bloqueada por |
|---|---|---|
| 0 — Setup y baseline visual | ✅ Wine flatpak funciona, windowed mode disponible | — |
| 1 — Header LPAK (inspector) | ✅ Hecho (formato conocido de la comunidad) | — |
| 2 — Unpacker real | ✅ Hecho (2599 archivos extraídos) | — |
| 3 — Mapeo asset → ruta lógica | ✅ Hecho (123 rooms parseados) | — |
| 4 — Repacker round-trip | ✅ Hecho (sha256 idéntico) | — |
| 5 — Primer mod real | ✅ Override por archivo suelto + reconstruccion de pak | — |
| 6 — Conversión DXT ↔ PNG | ✅ Pipeline completo funcional | — |
| 7 — Documentación final | ✅ Scripts documentados, LPak_format.md pendiente | — |

Leyenda: ✅ hecho · 🔄 en curso · ⬜ pendiente · 🚫 bloqueado · ⚠️ con dudas

**Hallazgo clave de la Sesión 3**: el motor acepta archivos `.dxt` sueltos en
`extracted/<ruta>` que sobreescriben los del pak (sin tocar el pak). Fuente:
`bgbennyboy/Monkey-Island-Image-Converter`. Esto cambia completamente el
workflow: mods no destructivos, sin riesgo de romper el pak, múltiples mods
simultáneos, activación/desactivación instantánea.

**Hallazgo clave de la Sesión 4**: el pak se puede reconstruir completo con
assets modificados usando solo Pillow + numpy. Pipeline end-to-end:
PNG (editable por AI) → DXT5 (vía compresor nativo en numpy) → pak rebuilt.
Diferencia promedio por píxel: ~3.7/255 (~1.5%) — aceptable para mods casuales.
Algoritmo range-fit, mejorable con librería externa (quicktex/etcpak).

---

## Fase 0 — Setup y baseline visual

**Objetivo**: confirmar que el juego arranca y tener un screenshot "antes" de Mêlée Town.

**Tareas**:
- [ ] Instalar Wine flatpak (lo haces tú en otra sesión).
- [ ] Verificar que `wine MISE.exe` arranca el juego en Linux.
- [ ] Capturar screenshot del intro / Mêlée Town → `screenshots/before_meleetown.png`.
- [ ] Si Wine falla, documentar el error y continuar con RE puro (Fases 1–4).

**Criterio de éxito**: existe `screenshots/before_meleetown.png` o, si Wine no
arranca, está documentado por qué y seguimos adelante.

---

## Fase 1 — Header LPAK (primer contacto con RE)

**Objetivo**: entender la estructura de los primeros bytes de `Monkey1.pak`.

**Conceptos previos a explicar** (en `LPak_notes.md`):
- Magic number y por qué los formatos de juego lo llevan.
- Little-endian vs big-endian (los bytes `4b 41 50 4c` = "LPAK" en LE).
- Tabla de contenidos (TOC) y offsets de 32/64 bits.
- Por qué `00 00 80 3f` justo tras el magic sugiere "versión 1.0".

**Tareas**:
- [ ] Crear `tools/lpak_inspect.py`.
- [ ] Leer los primeros 80 bytes con `od -A x -t x1 -N 80`.
- [ ] Misma lectura con Python + `struct.unpack`.
- [ ] Imprimir tabla con hipótesis: magic, versión, primer offset, count.
- [ ] Anotar hallazgos en `LPak_notes.md`.

**Salidas**:
- `tools/lpak_inspect.py`
- `LPak_notes.md` (sección "Fase 1")

**Criterio de éxito**: el script imprime una tabla legible con la estructura
del header y nuestras hipótesis iniciales están escritas en la bitácora.

---

## Fase 2 — Unpacker real

**Objetivo**: volcar todos los entries del pak a disco y clasificarlos por tipo.

**Tareas**:
- [ ] Crear `tools/lpak_unpack.py` (extiende el inspector).
- [ ] Crear `tools/magic_sniffer.py` — tabla de magic bytes:
  - PNG: `89 50 4E 47 0D 0A 1A 0A`
  - DDS: `44 44 53 20`
  - OGG: `4F 67 67 53`
  - WAV: `52 49 46 46`
  - XML: `3C 3F 78 6D 6C` o `3C 00`
  - Lua bytecode: `1B 4C 75 61`
  - PK (zip): `50 4B 03 04`
  - BMP: `42 4D`
- [ ] Volcar a `unpacked/<id>.<ext>` con un prefijo numérico.
- [ ] Generar `unpacked/INDEX.tsv` con: `id, offset, size, detected_type, sha256`.
- [ ] Estadísticas: cuántos blobs de cada tipo.

**Salidas**:
- `tools/lpak_unpack.py`
- `tools/magic_sniffer.py`
- `tsomir/unpacked/` (puede ser muy grande; medir antes)
- `tsomir/unpacked/INDEX.tsv`

**Criterio de éxito**: todos los entries del pak están en disco, clasificados,
con un índice consultable.

**⚠️ Nota de espacio**: `Monkey1.pak` descomprimido puede ocupar varios GB.
Verificar espacio en disco antes de empezar.

---

## Fase 3 — Mapeo asset → ruta lógica

**Objetivo**: identificar qué blob(es) corresponden a Mêlée Town.

**Tareas**:
- [ ] Extraer `monkey1_retail.scumm.xml` del pak (o leer del disco si está suelto).
- [ ] Listar assets referenciados que contengan "meleetown", "melee", "intro".
- [ ] Buscar también en strings de `MISE.exe` referencias tipo
  `Art/Scenes/meleetown/...png`.
- [ ] Para cada candidato, abrir el blob y confirmar que es un PNG válido.
- [ ] Documentar las rutas lógicas en `LPak_notes.md`.

**Salidas**:
- `LPak_notes.md` (sección "Fase 3") con tabla
  `ruta_lógica → id_blob → dimensiones → preview`.

**Criterio de éxito**: tenemos localizados los PNGs del fondo de Mêlée Town
intro. Los podemos abrir y ver.

---

## Fase 4 — Repacker round-trip

**Objetivo**: probar que unpack + repack = idéntico al original.

**Tareas**:
- [ ] Crear `tools/lpak_repack.py`.
- [ ] Reconstruir el archivo manteniendo orden, compresión, offsets.
- [ ] `sha256sum Monkey1.pak original` → guardar en `baseline.sha256`.
- [ ] `sha256sum Monkey1_repack.pak` → comparar.
- [ ] Si difiere: investigar campo por campo hasta encontrar la causa.

**Salidas**:
- `tools/lpak_repack.py`
- `tsomir/baseline.sha256`

**Criterio de éxito**: hash idéntico. Si no, documentar desviaciones y por qué
puede seguir siendo funcional (algunos formatos no son bit-exact pero sí
semánticamente equivalentes).

---

## Fase 5 — Primer mod real

**Objetivo**: modificar un solo asset de Mêlée Town y verificar que el juego
lo carga.

**Tareas**:
- [ ] Elegir el fondo (PNG) identificado en Fase 3.
- [ ] Hacer un cambio mínimo (1 píxel de otro color, o una zona pequeña).
- [ ] Repack → `Monkey1_modded.pak`.
- [ ] Sustituir el pak original (hacer backup antes) o investigar si el motor
  soporta pak override tipo `mods/meleetown.pak`.
- [ ] Ejecutar en Wine → screenshot → comparar con baseline.
- [ ] Si crashea: registrar el error, revertir, ajustar.

**Salidas**:
- `examples/meleetown_mod/`
  - `original.png`
  - `modificado.png`
  - `Monkey1.pak` (con el mod)
  - `README.md` con instrucciones de instalación
- `screenshots/after_meleetown.png`

**Criterio de éxito**: el juego carga sin crashear y se ve el cambio.

---

## Fase 6 — Documentación final

**Objetivo**: dejar todo documentado para futura referencia (propia o
comunidad).

**Tareas**:
- [ ] Escribir `LPak_format.md` con la especificación completa deducida.
- [ ] Revisar `LPak_notes.md` y consolidar hallazgos.
- [ ] Comentar todos los scripts en español.
- [ ] Crear `README.md` en `tsomir/` con índice de todo lo entregado.
- [ ] Si hay tiempo: ejemplo funcional de un mod no destructivo usando
  pak override (sin tocar el original).

**Salidas**:
- `LPak_format.md`
- `tsomir/README.md`
- Scripts comentados

**Criterio de éxito**: alguien con poca experiencia puede seguir el README y
los scripts para hacer su propio mod.

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Wine no se instala / no corre el juego | Continuar con RE puro; validar visual en tu Windows |
| Formato no reversible bit-exact | Documentar desviación; validar semánticamente (que el juego aún carga el repack sin tocar) |
| Descomprimido ocupa demasiado | Procesar entrada por entrada sin guardar todo a la vez; o usar SSD externo |
| Asset reemplazado crashea el juego | Tener backup del pak original; cambios mínimos primero |
| Tabla de offsets incluye hashes / firmas | Estudiar Fase 1 con cuidado; si hay firma, dejar Fase 5 como "investigar más" |

---

## Espacio de trabajo esperado

```
tsomir/
├── PLAN.md                          ← este archivo
├── LPak_notes.md                    ← bitácora viva del RE
├── LPak_format.md                   ← especificación final (Fase 6)
├── README.md                        ← índice general (Fase 6)
├── TheScapeOfMonkeyIslandRemasteredGOG.exe   (original sin tocar)
├── baseline.sha256                  ← hash del pak original (Fase 4)
├── extracted/                       ← salida del innoextract (ya hecho)
├── tools/
│   ├── lpak_inspect.py              (Fase 1)
│   ├── lpak_unpack.py               (Fase 2)
│   ├── magic_sniffer.py             (Fase 2)
│   └── lpak_repack.py               (Fase 4)
├── unpacked/                        ← blobs desempaquetados (Fase 2)
│   ├── INDEX.tsv
│   └── ...
├── screenshots/
│   ├── before_meleetown.png         (Fase 0)
│   └── after_meleetown.png          (Fase 5)
└── examples/
    └── meleetown_mod/               (Fase 5)
        ├── original.png
        ├── modificado.png
        ├── Monkey1.pak
        └── README.md
```

---

## Log de sesiones

> Anotar aquí fecha + sesión + qué se avanzó + decisiones tomadas.

### Sesión 1 — 2026-09-03
- **Hecho**:
  - Desempaquetado del instalador GOG con `innoextract` → `extracted/`.
  - Inspección inicial del `Monkey1.pak`: magic `4b 41 50 4c` ("LPAK" LE), 1.18 GB.
  - Strings de `MISE.exe` sugieren rutas `Art/Textures/*.png`, `monkey1_retail.scumm.xml`.
- **Decidido**:
  - Modo: tutorial detallado.
  - Wine se instala en paralelo (flatpak).
  - Target inicial: Mêlée Town intro.
  - Aprendizaje de RE como objetivo principal.
- **Próxima sesión**:
  - Fase 1: explicación de little-endian + magic numbers, luego `lpak_inspect.py`.

### Sesión 2 — 2026-09-03 (continuación)
- **Hecho**:
  - Investigación web: formato LPAK ya documentado (bgbennyboy, timfel).
  - `tools/lpak_inspect.py` — inspector funcional con tabla de entries.
  - `tools/lpak_unpack.py` — extractor con filtro.
  - `tools/lpak_repack.py` — reemplazo in-place (con bug detectado y corregido).
  - `tools/lpak_rebuild.py` — reconstrucción completa desde manifest (round-trip).
  - Extracción completa: 2599 archivos, 1.2 GB.
  - **Round-trip verificado**: `sha256(original) == sha256(rebuild)`.
  - Identificado room 85 = Mêlée Town (`art/rooms/85_melee/`).
  - Identificadas las 3 capas de la escena: layer0 (fondo), layer1 (fg),
    extra_water_f0 (agua).
  - Identificado que el archivo `.room.xml` es binario, no XML real.
  - Inyectada primera modificación (3 bytes cambiados en layer0_chunk_0_0.dxt).
- **Próxima sesión**:
  - Cuando Wine esté listo: capturar baseline screenshot.
  - Probar el pak modificado en Wine y capturar after-screenshot.
  - Implementar conversión `.dxt` ↔ `.dds` para edición con GIMP.
  - Crear un mod real (no solo 3 bytes).
  - Escribir `LPak_format.md` final (Fase 6).

### Sesión 3 — 2026-09-03 (continuación, BUILD MODE)
- **Hecho**:
  - Wine instalado (flatpak), funciona perfecto (fullscreen y windowed con
    `mise-wine-windowed.sh`).
  - Test visual: pak modificado parecía no cargar el mod (sprite room 85
    intacto). Causa: el sprite que veíamos NO estaba en layer0 sino en el
    costume `33_lookout-skin/costumes_a0.dxt`.
  - **Hallazgo MAYOR**: el motor acepta `.dxt` sueltos en `extracted/<ruta>`
    que sobreescriben los del pak sin tocarlo. Fuente: `bgbennyboy/Monkey-
    Island-Image-Converter`. Cambio total de estrategia.
  - Override del title screen → confirmado: pantalla de título a rayas rojas.
  - Búsqueda del sprite correcto del SCUMM bar: el "edificio" se compone de
    muchas sprites en `art/rooms/images/28_bar/` (layer0, layer1, objects).
  - Parsing de `.room.xml` binario: extrae lista de assets por room.
  - 123 rooms parseados. Room 28 (SCUMM Bar) tiene 21 assets, room 85 (Mêlée)
    tiene 12 assets.
  - **Override masivo del bar interior**: 54 sprites en `extracted/`. Resultado:
    pantalla del bar completamente roja, con personajes (piratas) visibles
    porque NO sobrescribimos sus sprites específicos.
- **Herramientas creadas esta sesión**:
  - `mise-wine-windowed.sh` — Wine en modo ventana
  - `tools/lpak_room_override.py` — override completo de un room por ID/color
  - `/tmp/room_assets.json` — mapa room_id → assets
- **Próximos pasos posibles**:
  - Conversor `.dxt` ↔ `.dds` para editar con GIMP/Photoshop
  - Mod real: pintar un fondo nuevo (no solo rojo)
  - `LPak_format.md` final
  - Identificar sprites específicos de Fester Shinetop, Meathook, etc.

### Sesión 4 — 2026-09-03 (BUILD MODE — pipeline DXT ↔ PNG)
- **Hecho**:
  - **Investigación web**: Pillow 12.3 tiene soporte DDS nativo (lee DXT1/DXT5,
    escribe con `pixel_format="DXT5"`), pero en 12.x mapea a BC3/DX10 que el
    juego no acepta. Implementación nativa de DXT5 en Python (numpy).
  - `tools/dxt_to_png.py` — convierte `.dxt` (formato MISE custom 12 bytes) a
    PNG editable. Wrap con header DDS estándar (124 bytes) + Pillow decode.
  - `tools/dxt5_compress.py` — compresor DXT5 nativo en Python (numpy).
    Algoritmo range-fit. Suficientemente bueno para mods casuales
    (diferencia promedio ~3.7/255 = 1.5% por píxel).
  - `tools/png_to_dxt.py` — PNG → `.dxt` con preservación de formato (DXT5/DXT1).
  - `tools/lpak_sprite_convert.py` — wrapper unificado con subcomandos
    `extract`, `inject`, `batch`. Permite extraer todos los assets de un room,
    modificarlos, y reinyectarlos.
  - `tools/lpak_rebuild_with_mods.py` — reconstruye el pak completo con assets
    modificados en sus offsets originales.
  - **Test E2E validado**: extraer `85_melee/layer0_chunk_0_0.dxt` → PNG → pintar
    círculo verde → PNG → DXT5 → pak rebuilt. Extracción del pak rebuilt
    confirma que el círculo está en su lugar.
- **Limitaciones conocidas**:
  - Compresión DXT5 con pérdida (artefactos menores en bordes/transparencias).
  - Mejorable con librería externa (quicktex/etcpak) si la calidad no es suficiente.
  - Dimensiones deben ser múltiplos de 4 (se paddea replicando).
- **Output para AI**: 21 PNGs del room 28 (SCUMM Bar) extraídos en
  `work/room_28_extracted/`. Listos para que la AI los edite y reinyectarlos.
- **Próximos pasos posibles**:
  - Mejorar el algoritmo de compresión (cluster-fit, perceptual weighting)
  - Documentar LPak_format.md final
  - Probar con un mod real (no solo círculo de prueba)

### Sesión 5 — 2026-09-03 (reim SCUMM bar + etcpak + restore)
- **Hecho**:
  - **Reim SCUMM bar (room 28)**: 4 PNGs reimaginados con AI entregados
    a 1600×1600 RGB. Pipeline: resize LANCZOS a 1024×1024 → DXT1 → pak
    rebuild / override suelto. Inyectados y validados visualmente en
    Wine.
  - **Integración etcpak**: instalado `etcpak` (`pip install etcpak`) y
    actualizado `tools/png_to_dxt.py` para usarlo como backend primario
    (range-fit queda como fallback). Cae del 6-7% al 3-4% de error
    promedio por canal y ~10× más rápido.
  - **`lpak_room_override.py --restore`**: nueva flag para borrar
    overrides de un room (o `all`). Bug detectado: la primera versión
    ignoraba `--dry-run` y borraba igual — corregido (respetar flag +
    pedir confirmación).
  - **Limpieza overrides rojos**: tras el test de override masivo del
    bar (21 sprites a rojo), se eliminaron los 17 archivos no-reimaginados.
    Quedan solo los 4 reimaginados en `extracted/art/rooms/images/28_bar/`.
  - **Repo público**: inicializado `vdirienzo/mise-lpak-tools` en GitHub
    (https://github.com/vdirienzo/mise-lpak-tools), privado al inicio
    y luego publicado. Incluye los 11 scripts Python + 4 bash + docs.
- **Decidido**:
  - Para mods de una pieza: usar override por archivo suelto (no tocar
    el pak, no perder el pristine).
  - Para mods grandes / reconstrucción masiva: usar
    `lpak_rebuild_with_mods.py` con un directorio `mods/`.

---

## Comandos de referencia rápida

```bash
# Ir al directorio de trabajo
cd /home/user/Projects/monkeyisland/tsomir

# Inspeccionar primeros 80 bytes del pak
od -A x -t x1 -N 80 Monkey1.pak.extracted/Monkey1.pak
# (ajustar ruta: el pak vive en extracted/Monkey1.pak)

# Hash del original (Fase 4)
sha256sum extracted/Monkey1.pak > baseline.sha256

# Lanzar el juego en Wine (cuando esté listo)
flatpak run org.winehq.Wine MISE.exe
# o
wine extracted/MISE.exe
```

---

## Cómo retomar este plan en una sesión nueva

1. Leer este archivo completo.
2. Leer `LPak_notes.md` (lo que llevamos aprendido).
3. Mirar la tabla "Estado de cada fase" arriba.
4. Continuar con la primera fase ⬜ pendiente o 🔄 en curso.
5. Actualizar el "Log de sesiones" al cerrar.

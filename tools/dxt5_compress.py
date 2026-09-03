#!/usr/bin/env python3
"""
dxt5_compress.py — Compresión DXT5 nativa en Python (con numpy).

Implementa el algoritmo "range fit" para comprimir imágenes RGBA a DXT5/BC3.
Cada bloque 4×4 se codifica como:
  - 8 bytes de alpha (alpha0, alpha1 + 16 índices de 3 bits)
  - 4 bytes de color (RGB565 c0, RGB565 c1 + 16 índices de 2 bits)
  - Total: 16 bytes por bloque 4×4 px

Suficientemente bueno para mods casuales (no es óptimo como RGBCX, pero
preserva el formato exacto que espera el motor MISE).

El algoritmo:
  Alpha:
    1. min/max del bloque
    2. Si min > max: swap
    3. Generar 8 valores (min, max, y 6 interpolados)
    4. Para cada pixel: índice del más cercano (3 bits)
  Color:
    1. Encontrar c0, c1 extremos (max distancia RGB)
    2. Si c0 <= c1 (en RGB565), swap
    3. Generar 4 colores: c0, c1, 2/3*c0+1/3*c1, 1/3*c0+2/3*c1
    4. Para cada pixel: índice del más cercano (2 bits)
"""

import numpy as np


def _alpha_block(alphas_u8):
    """Codifica un bloque 4×4 de alphas (uint8) en 8 bytes."""
    block = alphas_u8.flatten()  # 16 valores
    a_min, a_max = int(block.min()), int(block.max())

    if a_min == a_max:
        return bytes([a_min, a_max, 0, 0, 0, 0, 0, 0])

    if a_min > a_max:
        a_min, a_max = a_max, a_min

    # Tabla de 8 alphas: a0, a1, y 6 interpolados
    # Si a0 > a1: 6 interp; si a0 <= a1: 4 interp + 0 + 255
    if a_min > a_max:
        # a0 > a1: tabla completa de 8 valores
        alphas_tab = np.array([
            a_min,
            a_max,
            (6 * a_min + 1 * a_max) // 7,
            (5 * a_min + 2 * a_max) // 7,
            (4 * a_min + 3 * a_max) // 7,
            (3 * a_min + 4 * a_max) // 7,
            (2 * a_min + 5 * a_max) // 7,
            (1 * a_min + 6 * a_max) // 7,
        ], dtype=np.int32)
    else:
        # a0 <= a1: solo 4 interpolados
        alphas_tab = np.array([
            a_min,
            a_max,
            (4 * a_min + 1 * a_max) // 5,
            (3 * a_min + 2 * a_max) // 5,
            (2 * a_min + 3 * a_max) // 5,
            (1 * a_min + 4 * a_max) // 5,
            0,
            255,
        ], dtype=np.int32)

    # Distancia y argmin por pixel
    diffs = np.abs(block.astype(np.int32)[:, None] - alphas_tab[None, :])
    indices = np.argmin(diffs, axis=1).astype(np.uint8)

    # Empaquetar 16 índices de 3 bits = 48 bits = 6 bytes
    # Píxel 0 -> bits [0..2], píxel 1 -> bits [3..5], etc.
    bits = np.zeros(48, dtype=np.uint8)
    for i in range(16):
        bits[i * 3:(i + 1) * 3] = (indices[i] >> np.array([0, 1, 2])) & 1

    packed = 0
    for b in bits:
        packed = (packed << 1) | int(b)
    idx_bytes = packed.to_bytes(6, "big")

    return bytes([a_min, a_max]) + idx_bytes


def _color_block(rgb_u8):
    """Codifica un bloque 4×4 RGB (uint8) en 4 bytes."""
    block = rgb_u8.reshape(16, 3).astype(np.int32)

    # Encontrar los dos colores extremos (max distancia RGB)
    r_min, g_min, b_min = block.min(axis=0)
    r_max, g_max, b_max = block.max(axis=0)

    # Convertir a RGB565
    def to_rgb565(r, g, b):
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    def from_rgb565(v):
        r = ((v >> 11) & 0x1F) << 3
        g = ((v >> 5) & 0x3F) << 2
        b = (v & 0x1F) << 3
        return (r, g, b)

    c0_int = to_rgb565(int(r_max), int(g_max), int(b_max))
    c1_int = to_rgb565(int(r_min), int(g_min), int(b_min))

    # En DXT5, si c0 <= c1 en RGB565, swap (para indicar "tabla de 4 colores")
    if c0_int <= c1_int:
        c0_int, c1_int = c1_int, c0_int
        r_max, g_max, b_max = r_min, g_min, b_min
        r_min, g_min, b_min = (from_rgb565(c0_int))

    c0 = np.array(from_rgb565(c0_int))
    c1 = np.array(from_rgb565(c1_int))

    # Tabla de 4 colores: c0, c1, y 2 interp
    c2 = (2 * c0 + c1) // 3
    c3 = (c0 + 2 * c1) // 3
    color_tab = np.stack([c0, c1, c2, c3])  # (4, 3)

    # Encontrar índice más cercano
    diffs = np.abs(block[:, None, :] - color_tab[None, :, :]).sum(axis=2)
    indices = np.argmin(diffs, axis=1).astype(np.uint8)

    # Empaquetar 16 índices de 2 bits = 32 bits = 4 bytes
    bits = np.zeros(32, dtype=np.uint8)
    for i in range(16):
        bits[i * 2:(i + 1) * 2] = (indices[i] >> np.array([0, 1])) & 1

    packed = 0
    for b in bits:
        packed = (packed << 1) | int(b)
    idx_bytes = packed.to_bytes(4, "big")

    # c0 y c1 en little-endian (16 bits cada uno)
    c0_bytes = c0_int.to_bytes(2, "little")
    c1_bytes = c1_int.to_bytes(2, "little")

    return c0_bytes + c1_bytes + idx_bytes


def compress_dxt5(rgba_array):
    """Comprime una imagen RGBA (H, W, 4) uint8 a bytes DXT5.

    Asume que H y W son múltiplos de 4 (los añade si no).
    """
    if rgba_array.ndim != 3 or rgba_array.shape[2] != 4:
        raise ValueError(f"Esperado (H, W, 4), got {rgba_array.shape}")
    if rgba_array.dtype != np.uint8:
        rgba_array = rgba_array.astype(np.uint8)

    h, w = rgba_array.shape[:2]
    # Pad a múltiplos de 4 replicando el último píxel
    pad_h = (4 - h % 4) % 4
    pad_w = (4 - w % 4) % 4
    if pad_h or pad_w:
        padded = np.pad(
            rgba_array,
            ((0, pad_h), (0, pad_w), (0, 0)),
            mode="edge",
        )
    else:
        padded = rgba_array

    ph, pw = padded.shape[:2]

    # Procesar bloque por bloque
    n_blocks_y = ph // 4
    n_blocks_x = pw // 4
    blocks = []
    for by in range(n_blocks_y):
        for bx in range(n_blocks_x):
            block = padded[by * 4:(by + 1) * 4, bx * 4:(bx + 1) * 4]
            alpha_block = _alpha_block(block[:, :, 3])
            color_block = _color_block(block[:, :, :3])
            blocks.append(alpha_block + color_block)

    return b"".join(blocks)


def compress_dxt1(rgb_array):
    """Comprime RGB (sin alpha) a DXT1.

    DXT1: bloques de 8 bytes (4 bytes color + 4 bytes índices).
    Si c0 <= c1 en RGB565, hay un modo "1-bit alpha" (índice 3 = transparente).
    Aquí usamos siempre el modo 4-colores.
    """
    if rgb_array.ndim != 3 or rgb_array.shape[2] != 3:
        raise ValueError(f"Esperado (H, W, 3), got {rgb_array.shape}")
    if rgb_array.dtype != np.uint8:
        rgb_array = rgb_array.astype(np.uint8)

    h, w = rgb_array.shape[:2]
    pad_h = (4 - h % 4) % 4
    pad_w = (4 - w % 4) % 4
    if pad_h or pad_w:
        padded = np.pad(rgb_array, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
    else:
        padded = rgb_array

    ph, pw = padded.shape[:2]
    n_blocks_y = ph // 4
    n_blocks_x = pw // 4
    blocks = []
    for by in range(n_blocks_y):
        for bx in range(n_blocks_x):
            block = padded[by * 4:(by + 1) * 4, bx * 4:(bx + 1) * 4]
            color_block = _color_block(block[:, :, :3])
            blocks.append(color_block)

    return b"".join(blocks)

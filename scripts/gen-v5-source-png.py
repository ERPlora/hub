#!/usr/bin/env python3
"""
ERPlora · render PROVISIONAL del asset fuente para el icono de app Tauri.

Genera `apps/tauri/branding/app-icon-source.png` (1024×1024, marca V5 sobre
transparente, centrada con margen) reutilizando el layout de la marca V5
(hub central azul + 8 módulos rojo/verde/amarillo), idéntico al de
`media/generate-v5-icons.py` del monorepo.

Esto es SOLO un asset provisional para que el pipeline de iconos de app
(`scripts/gen-tauri-icon.py`) tenga una fuente válida y la app Tauri compile/arranque
con iconos correctos. El ARTE DE MARCA DEFINITIVO lo aporta el humano: sustituye
`app-icon-source.png` por el suyo y vuelve a correr el pipeline.

Dependencia única: Pillow.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    sys.exit("Falta Pillow: pip install Pillow")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps/tauri/branding/app-icon-source.png"

# ── Paleta V5 (idéntica a media/generate-v5-icons.py) ───────────────────────
BLUE = (0, 145, 206)
RED = (239, 68, 68)
GREEN = (16, 185, 129)
YELLOW = (245, 158, 11)

# Layout en espacio de 72 unidades
MODULES = [
    (6, 6, 12, 12, 2, RED),
    (30, 6, 12, 12, 2, GREEN),
    (54, 6, 12, 12, 2, YELLOW),
    (6, 30, 12, 12, 2, GREEN),
    (54, 30, 12, 12, 2, RED),
    (6, 54, 12, 12, 2, YELLOW),
    (30, 54, 12, 12, 2, RED),
    (54, 54, 12, 12, 2, GREEN),
    (24, 24, 24, 24, 4, BLUE),  # hub central
]
VIEW = 72
SIZE = 1024
SS = 4
# La marca ocupa ~78% del lienzo; el resto es margen (la safe-area fina la añade
# el pipeline de icono de app al componer).
MARK_SCALE = 0.78


def draw_mark() -> Image.Image:
    S = SIZE * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    span = S * MARK_SCALE
    k = span / VIEW
    off = (S - span) / 2
    for x, y, w, h, r, col in MODULES:
        d.rounded_rectangle(
            [off + x * k, off + y * k, off + (x + w) * k, off + (y + h) * k],
            radius=r * k,
            fill=col + (255,),
        )
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    draw_mark().save(OUT)
    print(f"OK — asset fuente provisional: {OUT.relative_to(ROOT)} ({SIZE}×{SIZE})")


if __name__ == "__main__":
    main()

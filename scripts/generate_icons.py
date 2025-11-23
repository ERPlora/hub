#!/usr/bin/env python3
"""
Script para generar iconos de aplicación desde SVG.
Genera: PNG (varios tamaños), ICO (Windows), ICNS (macOS)
"""

import subprocess
import sys
from pathlib import Path

# Rutas
SCRIPT_DIR = Path(__file__).parent
HUB_ROOT = SCRIPT_DIR.parent
SVG_LOGO = HUB_ROOT / "static" / "img" / "logo-blue.svg"
ASSETS_DIR = HUB_ROOT / "assets"

def check_dependencies():
    """Verifica que las herramientas necesarias estén instaladas."""
    tools = {
        'rsvg-convert': 'librsvg (brew install librsvg)',
        'convert': 'ImageMagick (brew install imagemagick)',
        'iconutil': 'Xcode Command Line Tools (xcode-select --install)'
    }

    missing = []
    for tool, install_cmd in tools.items():
        try:
            subprocess.run([tool, '--version'], capture_output=True, check=True)
            print(f"✓ {tool} found")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"✗ {tool} not found - Install with: {install_cmd}")
            missing.append(tool)

    return len(missing) == 0

def svg_to_png(svg_path, output_path, size):
    """Convierte SVG a PNG con el tamaño especificado."""
    print(f"Generating PNG {size}x{size}...")
    subprocess.run([
        'rsvg-convert',
        '-w', str(size),
        '-h', str(size),
        str(svg_path),
        '-o', str(output_path)
    ], check=True)
    print(f"✓ Created {output_path}")

def create_ico(png_files, output_path):
    """Crea archivo ICO para Windows desde varios PNG."""
    print(f"Generating ICO...")
    subprocess.run([
        'convert',
        *[str(p) for p in png_files],
        str(output_path)
    ], check=True)
    print(f"✓ Created {output_path}")

def create_icns(png_dir, output_path):
    """Crea archivo ICNS para macOS."""
    print(f"Generating ICNS...")

    # Crear iconset directory
    iconset_dir = png_dir / "AppIcon.iconset"
    iconset_dir.mkdir(exist_ok=True)

    # Tamaños requeridos para ICNS
    sizes = {
        16: ['icon_16x16.png'],
        32: ['icon_16x16@2x.png', 'icon_32x32.png'],
        64: ['icon_32x32@2x.png'],
        128: ['icon_128x128.png'],
        256: ['icon_128x128@2x.png', 'icon_256x256.png'],
        512: ['icon_256x256@2x.png', 'icon_512x512.png'],
        1024: ['icon_512x512@2x.png']
    }

    # Generar PNGs en tamaños específicos
    for size, filenames in sizes.items():
        png_path = png_dir / f"icon_{size}x{size}.png"
        if not png_path.exists():
            svg_to_png(SVG_LOGO, png_path, size)

        for filename in filenames:
            target = iconset_dir / filename
            if not target.exists():
                subprocess.run(['cp', str(png_path), str(target)], check=True)

    # Crear ICNS desde iconset
    subprocess.run([
        'iconutil',
        '-c', 'icns',
        str(iconset_dir),
        '-o', str(output_path)
    ], check=True)

    print(f"✓ Created {output_path}")

def main():
    print("=== ERPlora Icon Generator ===\n")

    # Verificar dependencias
    if not check_dependencies():
        print("\n❌ Please install missing dependencies and try again.")
        sys.exit(1)

    if not SVG_LOGO.exists():
        print(f"\n❌ SVG logo not found: {SVG_LOGO}")
        sys.exit(1)

    print(f"\nUsing logo: {SVG_LOGO}\n")

    # Crear directorio de assets si no existe
    ASSETS_DIR.mkdir(exist_ok=True)
    temp_dir = ASSETS_DIR / "temp"
    temp_dir.mkdir(exist_ok=True)

    try:
        # Generar PNGs para ICO (Windows)
        ico_sizes = [16, 32, 48, 64, 128, 256]
        png_files = []

        print("1. Generating PNGs for ICO...")
        for size in ico_sizes:
            png_path = temp_dir / f"icon_{size}.png"
            svg_to_png(SVG_LOGO, png_path, size)
            png_files.append(png_path)

        # Crear ICO
        print("\n2. Creating Windows ICO...")
        ico_path = ASSETS_DIR / "app_icon.ico"
        create_ico(png_files, ico_path)

        # Crear ICNS (macOS)
        print("\n3. Creating macOS ICNS...")
        icns_path = ASSETS_DIR / "app_icon.icns"
        create_icns(temp_dir, icns_path)

        # Crear PNG principal (logo.png)
        print("\n4. Creating main logo.png...")
        logo_png = HUB_ROOT / "static" / "img" / "logo.png"
        svg_to_png(SVG_LOGO, logo_png, 512)

        # Limpiar archivos temporales
        print("\n5. Cleaning up...")
        subprocess.run(['rm', '-rf', str(temp_dir)], check=True)

        print("\n✅ All icons generated successfully!")
        print(f"\nGenerated files:")
        print(f"  - {ico_path}")
        print(f"  - {icns_path}")
        print(f"  - {logo_png}")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

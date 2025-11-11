#!/usr/bin/env python3
"""
Script para generar iconos de aplicación desde SVG con tamaños más grandes.
Genera: PNG (varios tamaños), ICO grande (Windows), Favicon (Web)
"""

import sys
from pathlib import Path
from io import BytesIO

try:
    from PIL import Image
    import cairosvg
except ImportError:
    print("❌ Missing dependencies. Install with:")
    print("   pip install Pillow cairosvg")
    sys.exit(1)

# Rutas
SCRIPT_DIR = Path(__file__).parent
HUB_ROOT = SCRIPT_DIR.parent
SVG_LOGO = HUB_ROOT / "static" / "img" / "logo-blue.svg"
ASSETS_DIR = HUB_ROOT / "assets"
CLOUD_ROOT = HUB_ROOT.parent / "cloud"

def svg_to_pil_image(svg_path, size):
    """Convierte SVG a PIL Image con el tamaño especificado."""
    png_data = cairosvg.svg2png(
        url=str(svg_path),
        output_width=size,
        output_height=size
    )
    return Image.open(BytesIO(png_data))

def create_large_ico(svg_path, output_path):
    """Crea archivo ICO grande para Windows desde SVG."""
    print(f"Generating large ICO for Windows app icon...")

    # Tamaños más grandes para ICO de aplicación
    sizes = [16, 24, 32, 48, 64, 96, 128, 256]
    images = []

    for size in sizes:
        print(f"  - Generating {size}x{size}...")
        img = svg_to_pil_image(svg_path, size)
        images.append(img)

    # Guardar como ICO con múltiples tamaños
    images[0].save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    print(f"✓ Created {output_path}")

def create_favicon(svg_path, output_path):
    """Crea favicon.ico para web (tamaños estándar)."""
    print(f"Generating favicon.ico for web...")

    # Tamaños estándar para favicon
    sizes = [16, 32, 48]
    images = []

    for size in sizes:
        print(f"  - Generating {size}x{size}...")
        img = svg_to_pil_image(svg_path, size)
        images.append(img)

    # Guardar como ICO
    images[0].save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    print(f"✓ Created {output_path}")

def create_icns_pngs(svg_path, output_dir):
    """
    Crea los PNGs necesarios para ICNS.
    """
    print(f"Generating PNGs for ICNS...")

    iconset_dir = output_dir / "AppIcon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # Tamaños y nombres para ICNS
    icns_mapping = {
        16: ['icon_16x16.png'],
        32: ['icon_16x16@2x.png', 'icon_32x32.png'],
        64: ['icon_32x32@2x.png'],
        128: ['icon_128x128.png'],
        256: ['icon_128x128@2x.png', 'icon_256x256.png'],
        512: ['icon_256x256@2x.png', 'icon_512x512.png'],
        1024: ['icon_512x512@2x.png']
    }

    for size, filenames in icns_mapping.items():
        img = svg_to_pil_image(svg_path, size)

        for filename in filenames:
            output_path = iconset_dir / filename
            img.save(output_path, "PNG")

    print(f"✓ Created ICNS PNGs in {iconset_dir}")
    return iconset_dir

def main():
    print("=== ERPlora Large Icon Generator ===\n")

    if not SVG_LOGO.exists():
        print(f"❌ SVG logo not found: {SVG_LOGO}")
        sys.exit(1)

    print(f"Using logo: {SVG_LOGO}\n")

    # Crear directorios si no existen
    ASSETS_DIR.mkdir(exist_ok=True)
    (CLOUD_ROOT / "static" / "img").mkdir(parents=True, exist_ok=True)
    (HUB_ROOT / "static" / "img").mkdir(parents=True, exist_ok=True)

    try:
        # 1. Crear ICO grande para aplicación Windows
        print("1. Creating large Windows ICO (app icon)...")
        ico_path = ASSETS_DIR / "app_icon.ico"
        create_large_ico(SVG_LOGO, ico_path)

        # 2. Crear Favicon para web
        print("\n2. Creating favicon.ico for web...")
        favicon_hub = HUB_ROOT / "static" / "img" / "favicon.ico"
        favicon_cloud = CLOUD_ROOT / "static" / "img" / "favicon.ico"

        create_favicon(SVG_LOGO, favicon_hub)

        # Copiar favicon a Cloud
        import shutil
        shutil.copy(favicon_hub, favicon_cloud)
        print(f"✓ Copied to {favicon_cloud}")

        # 3. Crear PNGs para ICNS (macOS)
        print("\n3. Creating PNGs for macOS ICNS...")
        iconset_dir = create_icns_pngs(SVG_LOGO, ASSETS_DIR)

        print("\n✅ Icons generated successfully!")
        print(f"\nGenerated files:")
        print(f"  - {ico_path} (Large, for app)")
        print(f"  - {favicon_hub}")
        print(f"  - {favicon_cloud}")
        print(f"  - {iconset_dir}/ (for ICNS)")

        # 4. Intentar crear ICNS automáticamente si iconutil está disponible
        print("\n4. Attempting to create ICNS...")
        import subprocess
        try:
            icns_path = ASSETS_DIR / "app_icon.icns"
            subprocess.run([
                'iconutil',
                '-c', 'icns',
                str(iconset_dir),
                '-o', str(icns_path)
            ], check=True, capture_output=True)
            print(f"✓ Created {icns_path}")

            # Limpiar iconset
            subprocess.run(['rm', '-rf', str(iconset_dir)], check=True)
            print(f"✓ Cleaned up temporary files")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"⚠ iconutil not available. ICNS not created.")
            print(f"  Run manually: iconutil -c icns {iconset_dir} -o {ASSETS_DIR}/app_icon.icns")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script para generar iconos de aplicación desde SVG usando Pillow.
Genera: PNG (varios tamaños), ICO (Windows)
Nota: ICNS requiere herramientas de macOS (iconutil)
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

def svg_to_pil_image(svg_path, size):
    """Convierte SVG a PIL Image con el tamaño especificado."""
    png_data = cairosvg.svg2png(
        url=str(svg_path),
        output_width=size,
        output_height=size
    )
    return Image.open(BytesIO(png_data))

def create_png_logo(svg_path, output_path, size=512):
    """Crea PNG desde SVG."""
    print(f"Generating PNG {size}x{size}...")
    img = svg_to_pil_image(svg_path, size)
    img.save(output_path, "PNG")
    print(f"✓ Created {output_path}")
    return img

def create_ico(svg_path, output_path):
    """Crea archivo ICO para Windows desde SVG."""
    print(f"Generating ICO with multiple sizes...")

    # Tamaños para ICO
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = svg_to_pil_image(svg_path, size)
        images.append(img)

    # Guardar como ICO con múltiples tamaños
    images[0].save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    print(f"✓ Created {output_path}")

def create_icns_pngs(svg_path, output_dir):
    """
    Crea los PNGs necesarios para ICNS.
    El usuario debe ejecutar iconutil manualmente después.
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
    print(f"\n  To create ICNS, run:")
    print(f"  iconutil -c icns {iconset_dir} -o {output_dir}/app_icon.icns")

    return iconset_dir

def main():
    print("=== ERPlora Icon Generator (Pillow) ===\n")

    if not SVG_LOGO.exists():
        print(f"❌ SVG logo not found: {SVG_LOGO}")
        sys.exit(1)

    print(f"Using logo: {SVG_LOGO}\n")

    # Crear directorio de assets si no existe
    ASSETS_DIR.mkdir(exist_ok=True)

    try:
        # 1. Crear PNG principal (logo.png)
        print("1. Creating main logo.png...")
        logo_png = HUB_ROOT / "static" / "img" / "logo.png"
        create_png_logo(SVG_LOGO, logo_png, 512)

        # 2. Crear ICO para Windows
        print("\n2. Creating Windows ICO...")
        ico_path = ASSETS_DIR / "app_icon.ico"
        create_ico(SVG_LOGO, ico_path)

        # 3. Crear PNGs para ICNS (macOS)
        print("\n3. Creating PNGs for macOS ICNS...")
        iconset_dir = create_icns_pngs(SVG_LOGO, ASSETS_DIR)

        print("\n✅ Icons generated successfully!")
        print(f"\nGenerated files:")
        print(f"  - {logo_png}")
        print(f"  - {ico_path}")
        print(f"  - {iconset_dir}/ (for ICNS)")

        # Intentar crear ICNS automáticamente si iconutil está disponible
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

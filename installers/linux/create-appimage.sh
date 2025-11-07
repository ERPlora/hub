#!/bin/bash
set -e

# Script para crear AppImage de CPOS Hub con autostart
# Requiere: appimagetool

VERSION="${1:-0.8.0}"
ARCH=$(uname -m)

echo "[INFO] Creando AppImage para CPOS Hub v${VERSION} (${ARCH})"

# Directorios
BUILD_DIR="dist/main"
APPDIR="CPOS-Hub.AppDir"

# Limpiar AppDir anterior
rm -rf "$APPDIR"

# Crear estructura AppDir
echo "[INFO] Creando estructura AppDir..."
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$APPDIR/usr/share/metainfo"

# Copiar aplicación
echo "[INFO] Copiando aplicación..."
cp -r "$BUILD_DIR"/* "$APPDIR/usr/bin/"

# Crear wrapper script que maneja autostart
cat > "$APPDIR/usr/bin/cpos-hub-wrapper.sh" << 'EOF'
#!/bin/bash

# CPOS Hub Wrapper Script
# Maneja instalación de autostart y ejecución

AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/cpos-hub.desktop"
APPIMAGE_PATH="$(readlink -f "$APPIMAGE")"

# Función para instalar autostart
install_autostart() {
    if [ ! -z "$APPIMAGE" ]; then
        echo "[INFO] Configurando autostart de CPOS Hub..."
        mkdir -p "$AUTOSTART_DIR"

        cat > "$AUTOSTART_FILE" << AUTOSTART
[Desktop Entry]
Type=Application
Name=CPOS Hub
Comment=CPOS Point of Sale System
Exec="$APPIMAGE_PATH"
Icon=cpos-hub
Terminal=false
Categories=Office;Finance;
StartupNotify=false
X-GNOME-Autostart-enabled=true
AUTOSTART

        chmod +x "$AUTOSTART_FILE"
        echo "[OK] Autostart configurado en: $AUTOSTART_FILE"
    fi
}

# Instalar autostart en primer arranque
if [ ! -f "$AUTOSTART_FILE" ]; then
    install_autostart
fi

# Ejecutar aplicación
cd "$(dirname "$0")"
exec ./main "$@"
EOF

chmod +x "$APPDIR/usr/bin/cpos-hub-wrapper.sh"

# Crear AppRun (entry point)
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
export PATH="${HERE}/usr/bin:${PATH}"
cd "${HERE}/usr/bin"
exec ./cpos-hub-wrapper.sh "$@"
EOF

chmod +x "$APPDIR/AppRun"

# Copiar icono
if [ -f "assets/app_icon.png" ]; then
    cp assets/app_icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/cpos-hub.png"
    cp assets/app_icon.png "$APPDIR/cpos-hub.png"
elif [ -f "assets/icon.png" ]; then
    cp assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/cpos-hub.png"
    cp assets/icon.png "$APPDIR/cpos-hub.png"
else
    echo "[WARNING] Icono no encontrado, usando icono por defecto"
fi

# Crear .desktop file
cat > "$APPDIR/cpos-hub.desktop" << EOF
[Desktop Entry]
Type=Application
Name=CPOS Hub
Comment=CPOS Point of Sale System
Exec=cpos-hub-wrapper.sh
Icon=cpos-hub
Categories=Office;Finance;
Terminal=false
StartupNotify=false
EOF

# Copiar también a /usr/share/applications
cp "$APPDIR/cpos-hub.desktop" "$APPDIR/usr/share/applications/"

# Crear AppStream metadata
cat > "$APPDIR/usr/share/metainfo/cpos-hub.appdata.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.cpos.hub</id>
  <name>CPOS Hub</name>
  <summary>Point of Sale System</summary>
  <description>
    <p>CPOS Hub es un sistema POS completo con gestión de inventario, ventas, y sincronización en la nube.</p>
  </description>
  <launchable type="desktop-id">cpos-hub.desktop</launchable>
  <url type="homepage">https://cpos.app</url>
  <provides>
    <binary>cpos-hub-wrapper.sh</binary>
  </provides>
  <releases>
    <release version="${VERSION}" date="$(date +%Y-%m-%d)"/>
  </releases>
  <content_rating type="oars-1.1"/>
</component>
EOF

# Descargar appimagetool si no existe
if [ ! -f "appimagetool-${ARCH}.AppImage" ]; then
    echo "[INFO] Descargando appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "appimagetool-${ARCH}.AppImage"
fi

# Crear AppImage
echo "[INFO] Creando AppImage..."
ARCH="${ARCH}" "./appimagetool-${ARCH}.AppImage" "$APPDIR" "CPOS-Hub-${VERSION}-${ARCH}.AppImage"

# Hacer ejecutable
chmod +x "CPOS-Hub-${VERSION}-${ARCH}.AppImage"

echo "[OK] AppImage creado: CPOS-Hub-${VERSION}-${ARCH}.AppImage"
echo ""
echo "Características:"
echo "  - Autostart: Se añade automáticamente al inicio del sistema"
echo "  - Ubicación autostart: ~/.config/autostart/cpos-hub.desktop"
echo "  - Portable: No requiere instalación"
echo ""
echo "Para ejecutar:"
echo "  ./CPOS-Hub-${VERSION}-${ARCH}.AppImage"

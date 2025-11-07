#!/bin/bash
set -e

# Script para firmar y empaquetar CPOS Hub para macOS
# Requiere: Apple Developer ID certificate

VERSION="${1:-0.8.0}"
APP_NAME="CPOS Hub.app"
DMG_NAME="CPOS-Hub-${VERSION}-macos.dmg"
BUILD_PATH="dist/${APP_NAME}"

echo "[INFO] Firmando y empaquetando CPOS Hub v${VERSION} para macOS"

# Verificar que existe el build
if [ ! -d "$BUILD_PATH" ]; then
    echo "[ERROR] Build no encontrado en: $BUILD_PATH"
    echo "[INFO] Ejecuta primero: pyinstaller main.spec"
    exit 1
fi

# Función para verificar si hay certificado de Developer ID
check_certificate() {
    if security find-identity -v -p codesigning | grep -q "Developer ID Application"; then
        CERT_NAME=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.*)"/\1/')
        echo "[OK] Certificado encontrado: $CERT_NAME"
        return 0
    else
        echo "[WARNING] No se encontró certificado de Developer ID"
        echo "[INFO] La aplicación NO será firmada"
        echo "[INFO] Para firmar, necesitas un Apple Developer ID"
        return 1
    fi
}

# Función para firmar la aplicación
sign_app() {
    local cert_name="$1"
    echo "[INFO] Firmando aplicación..."

    # Firmar todos los ejecutables y frameworks
    find "$BUILD_PATH/Contents/MacOS" -type f -perm +111 -exec \
        codesign --force --sign "$cert_name" \
        --options runtime \
        --timestamp \
        --deep {} \;

    # Firmar frameworks y librerías
    find "$BUILD_PATH/Contents/Frameworks" -name "*.dylib" -o -name "*.framework" -exec \
        codesign --force --sign "$cert_name" \
        --options runtime \
        --timestamp {} \; 2>/dev/null || true

    # Firmar el bundle completo
    codesign --force --sign "$cert_name" \
        --options runtime \
        --timestamp \
        --deep \
        --entitlements "entitlements.plist" \
        "$BUILD_PATH"

    echo "[OK] Aplicación firmada con: $cert_name"

    # Verificar firma
    echo "[INFO] Verificando firma..."
    codesign --verify --deep --strict "$BUILD_PATH"
    echo "[OK] Firma verificada"
}

# Función para notarizar la aplicación (opcional, requiere cuenta Developer)
notarize_app() {
    echo "[INFO] Notarización no implementada en este script"
    echo "[INFO] Para notarizar manualmente:"
    echo "  1. Crear archivo ZIP: ditto -c -k --keepParent '$BUILD_PATH' app.zip"
    echo "  2. Subir a Apple: xcrun notarytool submit app.zip --apple-id YOUR_EMAIL --team-id YOUR_TEAM_ID --password APP_SPECIFIC_PASSWORD"
    echo "  3. Esperar aprobación (puede tomar minutos u horas)"
    echo "  4. Staple: xcrun stapler staple '$BUILD_PATH'"
}

# Función para crear DMG
create_dmg() {
    echo "[INFO] Creando imagen DMG..."

    # Limpiar DMG anterior
    rm -f "$DMG_NAME"

    # Crear DMG temporal
    local temp_dmg="temp_${DMG_NAME}"
    hdiutil create -srcfolder "$BUILD_PATH" -volname "CPOS Hub" -fs HFS+ \
        -fsargs "-c c=64,a=16,e=16" -format UDRW -size 500m "$temp_dmg"

    # Montar DMG
    local device=$(hdiutil attach -readwrite -noverify -noautoopen "$temp_dmg" | \
        grep -Eo '/dev/disk[0-9]+')
    local mount_point="/Volumes/CPOS Hub"

    # Crear alias a Applications
    ln -s /Applications "$mount_point/Applications"

    # Configurar apariencia del DMG (opcional)
    if [ -f "../../assets/dmg-background.png" ]; then
        mkdir -p "$mount_point/.background"
        cp "../../assets/dmg-background.png" "$mount_point/.background/"
    fi

    # Desmontar
    hdiutil detach "$device"

    # Convertir a DMG final comprimido
    hdiutil convert "$temp_dmg" -format UDZO -imagekey zlib-level=9 -o "$DMG_NAME"

    # Limpiar temporal
    rm -f "$temp_dmg"

    echo "[OK] DMG creado: $DMG_NAME"
}

# Crear entitlements.plist si no existe
if [ ! -f "entitlements.plist" ]; then
    cat > entitlements.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.network.server</key>
    <true/>
</dict>
</plist>
EOF
fi

# Ejecutar proceso de firma y empaquetado
if check_certificate; then
    sign_app "$CERT_NAME"
else
    echo "[WARNING] Continuando sin firma de código"
fi

create_dmg

echo ""
echo "[OK] Proceso completado!"
echo ""
echo "Archivo creado: $DMG_NAME"
echo ""
echo "Características:"
echo "  - Formato: DMG montable"
echo "  - Drag & Drop: Arrastra a /Applications"
echo "  - Firma: $(if [ ! -z "$CERT_NAME" ]; then echo "Sí ($CERT_NAME)"; else echo "No firmado"; fi)"
echo "  - Autostart: No (según especificación)"
echo ""
echo "Distribución:"
echo "  - Subir a GitHub Releases"
echo "  - Usuarios: Montan DMG y arrastran a Applications"
echo ""

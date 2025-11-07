#!/bin/bash
# Script para firmar archivos de release con GPG
#
# Uso:
#   ./scripts/sign-release.sh <archivo>
#
# Ejemplo:
#   ./scripts/sign-release.sh CPOS-Hub-0.8.0-windows.zip
#
# Requiere:
#   - GPG_PRIVATE_KEY (variable de entorno con la clave privada)
#   - GPG_KEY_ID (variable de entorno con el Key ID)

set -e

if [ $# -eq 0 ]; then
    echo "[ERROR] Uso: $0 <archivo>"
    echo "Ejemplo: $0 CPOS-Hub-0.8.0-windows.zip"
    exit 1
fi

FILE="$1"

if [ ! -f "$FILE" ]; then
    echo "[ERROR] Archivo no encontrado: $FILE"
    exit 1
fi

if [ -z "$GPG_PRIVATE_KEY" ]; then
    echo "[ERROR] Variable GPG_PRIVATE_KEY no definida"
    exit 1
fi

if [ -z "$GPG_KEY_ID" ]; then
    echo "[ERROR] Variable GPG_KEY_ID no definida"
    exit 1
fi

echo "[INFO] Importando clave GPG..."
echo "$GPG_PRIVATE_KEY" | gpg --batch --import

echo "[INFO] Firmando archivo: $FILE"
gpg --batch --yes --detach-sign --armor --local-user "$GPG_KEY_ID" "$FILE"

SIGNATURE_FILE="${FILE}.asc"

if [ -f "$SIGNATURE_FILE" ]; then
    echo "[OK] Firma generada: $SIGNATURE_FILE"

    # Verificar la firma
    echo "[INFO] Verificando firma..."
    if gpg --verify "$SIGNATURE_FILE" "$FILE" 2>&1 | grep -q "Good signature"; then
        echo "[OK] Firma verificada correctamente"
    else
        echo "[WARNING] No se pudo verificar la firma automáticamente"
    fi
else
    echo "[ERROR] No se generó el archivo de firma"
    exit 1
fi

echo ""
echo "[OK] Archivo firmado exitosamente"
echo "     Archivo: $FILE"
echo "     Firma: $SIGNATURE_FILE"

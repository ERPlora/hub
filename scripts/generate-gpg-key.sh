#!/bin/bash
# Script para generar clave GPG para firma de releases de CPOS Hub
#
# Uso:
#   ./scripts/generate-gpg-key.sh
#
# Output:
#   - Clave GPG generada
#   - gpg-private-key.asc (para GitHub Secrets)
#   - gpg-public-key.asc (para publicar)

set -e

echo "[INFO] Generando clave GPG para CPOS Hub..."

# Configuración de la clave
KEY_NAME="CPOS Team"
KEY_EMAIL="releases@cpos.app"
KEY_COMMENT="CPOS Hub Release Signing Key"
KEY_TYPE="RSA"
KEY_LENGTH="4096"
EXPIRATION="5y"  # 5 años

# Generar configuración para generación batch
cat > gpg-key-config.txt <<EOF
%echo Generating GPG key for CPOS Hub
Key-Type: $KEY_TYPE
Key-Length: $KEY_LENGTH
Subkey-Type: $KEY_TYPE
Subkey-Length: $KEY_LENGTH
Name-Real: $KEY_NAME
Name-Comment: $KEY_COMMENT
Name-Email: $KEY_EMAIL
Expire-Date: $EXPIRATION
%no-protection
%commit
%echo Key generation complete
EOF

# Generar la clave
echo "[INFO] Generando clave (esto puede tomar unos minutos)..."
gpg --batch --generate-key gpg-key-config.txt

# Obtener el Key ID
KEY_ID=$(gpg --list-keys --with-colons "$KEY_EMAIL" | grep '^fpr' | head -1 | cut -d: -f10)

if [ -z "$KEY_ID" ]; then
    echo "[ERROR] No se pudo generar la clave"
    exit 1
fi

echo "[OK] Clave generada con ID: $KEY_ID"

# Exportar clave privada (para GitHub Secrets)
echo "[INFO] Exportando clave privada..."
gpg --armor --export-secret-keys "$KEY_ID" > gpg-private-key.asc
echo "[OK] Clave privada exportada a: gpg-private-key.asc"
echo "     (Agregar a GitHub Secrets como GPG_PRIVATE_KEY)"

# Exportar clave pública (para publicar)
echo "[INFO] Exportando clave pública..."
gpg --armor --export "$KEY_ID" > gpg-public-key.asc
echo "[OK] Clave pública exportada a: gpg-public-key.asc"
echo "     (Publicar en el repositorio para verificación)"

# Exportar passphrase vacía info
echo "[INFO] Esta clave NO tiene passphrase (para automatización CI/CD)"

# Limpiar archivo de configuración
rm gpg-key-config.txt

echo ""
echo "=========================================="
echo "[OK] Clave GPG generada exitosamente"
echo "=========================================="
echo ""
echo "Próximos pasos:"
echo "1. Agregar gpg-private-key.asc a GitHub Secrets:"
echo "   - Nombre: GPG_PRIVATE_KEY"
echo "   - Valor: contenido completo de gpg-private-key.asc"
echo ""
echo "2. Agregar Key ID a GitHub Secrets:"
echo "   - Nombre: GPG_KEY_ID"
echo "   - Valor: $KEY_ID"
echo ""
echo "3. Publicar clave pública:"
echo "   cp gpg-public-key.asc hub/GPG-PUBLIC-KEY.asc"
echo "   git add hub/GPG-PUBLIC-KEY.asc"
echo "   git commit -m 'chore: add GPG public key for release verification'"
echo ""
echo "4. Mantener segura la clave privada (gpg-private-key.asc)"
echo "   - NO la subas al repositorio"
echo "   - Guárdala en un lugar seguro (password manager)"
echo ""

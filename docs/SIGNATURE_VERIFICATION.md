# Verificación de Firmas GPG para CPOS Hub

Todos los archivos de release de CPOS Hub están firmados con GPG para garantizar su autenticidad e integridad.

---

## 🔐 ¿Por Qué Verificar las Firmas?

La verificación de firmas GPG te asegura que:

- ✅ El archivo fue creado por CPOS Team (autenticidad)
- ✅ El archivo no fue modificado después de ser publicado (integridad)
- ✅ No estás descargando malware o versiones comprometidas

---

## 📥 Descargar la Clave Pública

Antes de verificar, necesitas importar la clave pública de CPOS Team:

### Opción 1: Desde la API de CPOS (Recomendado)

```bash
# Descargar e importar directamente desde la API
curl -sL https://erplora.com/api/gpg/public-key/ | gpg --import

# O descargar y guardar
curl -sL https://erplora.com/api/gpg/public-key/ -o cpos-hub-public-key.asc
gpg --import cpos-hub-public-key.asc
```

### Opción 2: Desde el repositorio GitHub

```bash
# Descargar clave pública
curl -O https://raw.githubusercontent.com/ERPlora/hub/main/GPG-PUBLIC-KEY.asc

# Importar clave
gpg --import GPG-PUBLIC-KEY.asc
```

### Opción 3: Obtener información de la clave

```bash
# Ver información detallada en JSON
curl -s https://erplora.com/api/gpg/public-key/info/ | jq
```

### Información de la Clave

```
Name:        CPOS Team
Email:       releases@erplora.com
Comment:     CPOS Hub Release Signing Key
Key Type:    RSA 4096-bit
Key ID:      998A98EF7BE1D222837D30EBC27E75F06D413478
Fingerprint: 998A 98EF 7BE1 D222 837D  30EB C27E 75F0 6D41 3478
Expiration:  2030-11-06 (5 years)
```

---

## ✅ Verificar un Archivo Descargado

### Paso 1: Descargar el archivo y su firma

Cuando descargues una release, obtendrás:
- `CPOS-Hub-0.8.0-windows.zip` (el archivo)
- `CPOS-Hub-0.8.0-windows.zip.asc` (la firma GPG)

### Paso 2: Verificar la firma

#### Linux / macOS

```bash
# Verificar archivo Windows
gpg --verify CPOS-Hub-0.8.0-windows.zip.asc CPOS-Hub-0.8.0-windows.zip

# Verificar archivo macOS
gpg --verify CPOS-Hub-0.8.0-macos.zip.asc CPOS-Hub-0.8.0-macos.zip

# Verificar archivo Linux
gpg --verify CPOS-Hub-0.8.0-linux.tar.gz.asc CPOS-Hub-0.8.0-linux.tar.gz
```

#### Windows (PowerShell)

```powershell
# Instalar GPG4Win primero: https://gpg4win.org/

# Verificar archivo
gpg --verify CPOS-Hub-0.8.0-windows.zip.asc CPOS-Hub-0.8.0-windows.zip
```

### Paso 3: Interpretar el resultado

#### ✅ Firma Válida

```
gpg: Signature made Mon 07 Jan 2025 10:00:00 AM UTC
gpg:                using RSA key <KEY_ID>
gpg: Good signature from "CPOS Team (CPOS Hub Release Signing Key) <releases@erplora.com>" [unknown]
```

Si ves `Good signature`, el archivo es auténtico.

#### ⚠️ Warning sobre "unknown key"

```
gpg: WARNING: This key is not certified with a trusted signature!
gpg:          There is no indication that the signature belongs to the owner.
```

Este warning es **normal** si es la primera vez que usas la clave. Para confiar en la clave:

```bash
# Listar claves importadas
gpg --list-keys releases@erplora.com

# Confiar en la clave (interactivo)
gpg --edit-key releases@erplora.com
> trust
> 5 (I trust ultimately)
> quit
```

#### ❌ Firma Inválida

```
gpg: BAD signature from "CPOS Team..."
```

**NO USES EL ARCHIVO**. Esto significa que:
- El archivo fue modificado después de ser firmado
- El archivo está corrupto
- Posible malware o compromiso

Descarga el archivo nuevamente desde la fuente oficial.

---

## 🔍 Verificar el Fingerprint de la Clave

Para asegurarte de que importaste la clave correcta:

```bash
# Ver fingerprint completo
gpg --fingerprint releases@erplora.com
```

Compara el fingerprint con el publicado en:
- https://github.com/ERPlora/hub/blob/main/GPG-PUBLIC-KEY.asc
- https://erplora.com/security/gpg (página web oficial)

---

## 🛠️ Instalación de GPG

### Linux

```bash
# Debian/Ubuntu
sudo apt install gnupg

# Fedora/RHEL
sudo dnf install gnupg

# Arch
sudo pacman -S gnupg
```

### macOS

```bash
# Con Homebrew
brew install gnupg
```

### Windows

Descargar e instalar **GPG4Win**:
https://gpg4win.org/download.html

---

## 🤝 Confiar en la Clave

Si planeas verificar múltiples releases, marca la clave como confiable:

```bash
gpg --edit-key releases@erplora.com
gpg> trust
Your decision? 5 (I trust ultimately)
gpg> quit
```

Después de esto, no verás el warning "not certified" en futuras verificaciones.

---

## 📋 Script Automatizado

Puedes crear un script para automatizar la verificación:

```bash
#!/bin/bash
# verify-cpos.sh

FILE="$1"

if [ ! -f "$FILE" ]; then
    echo "[ERROR] Archivo no encontrado: $FILE"
    exit 1
fi

if [ ! -f "${FILE}.asc" ]; then
    echo "[ERROR] Archivo de firma no encontrado: ${FILE}.asc"
    exit 1
fi

echo "[INFO] Verificando firma de: $FILE"
if gpg --verify "${FILE}.asc" "$FILE" 2>&1 | grep -q "Good signature"; then
    echo "[OK] Firma válida"
    exit 0
else
    echo "[ERROR] Firma inválida o clave no confiable"
    exit 1
fi
```

Uso:
```bash
chmod +x verify-cpos.sh
./verify-cpos.sh CPOS-Hub-0.8.0-windows.zip
```

---

## ❓ FAQ

### ¿Debo verificar siempre las firmas?

**Sí**, especialmente si:
- Descargas desde fuentes no oficiales
- Instalas en entornos de producción
- Manejas datos sensibles

### ¿Qué hago si la firma es inválida?

1. **NO uses el archivo**
2. Elimínalo inmediatamente
3. Descarga nuevamente desde https://github.com/ERPlora/hub/releases
4. Verifica nuevamente
5. Si persiste, reporta el problema: security@erplora.com

### ¿La firma garantiza que el software es seguro?

La firma solo garantiza que:
- El archivo proviene de CPOS Team
- No fue modificado

NO garantiza que el software esté libre de bugs o vulnerabilidades.

### ¿Puedo verificar releases antiguas?

Sí, mientras la clave GPG no haya expirado (válida hasta 2030-01-07).

---

## 🔒 Seguridad

### Reporte de Vulnerabilidades

Si encuentras un problema de seguridad:
- **NO lo publiques públicamente**
- Envía un email a: security@erplora.com
- Incluye: versión, sistema operativo, pasos para reproducir

### Transparencia

- Clave pública: https://github.com/ERPlora/hub/blob/main/GPG-PUBLIC-KEY.asc
- Historial de firmas: https://github.com/ERPlora/hub/releases
- Policy de seguridad: https://github.com/ERPlora/hub/security/policy

---

## 📚 Recursos Adicionales

- [The GNU Privacy Guard](https://gnupg.org/)
- [GPG Best Practices](https://riseup.net/en/security/message-security/openpgp/best-practices)
- [Verifying signatures (Arch Wiki)](https://wiki.archlinux.org/title/GnuPG#Verify_a_signature)

---

**Última actualización**: 2025-01-07

# Configuración de Firma GPG para Releases

Guía para configurar la firma GPG en GitHub Actions para CPOS Hub.

---

## 🎯 Objetivo

Firmar todos los archivos de release (Windows, macOS, Linux) con GPG para garantizar autenticidad e integridad.

---

## 📋 Requisitos Previos

- GPG instalado localmente
- Acceso a GitHub con permisos de administrador en el repositorio
- Acceso a GitHub Secrets del repositorio

---

## 🔑 Paso 1: Generar Clave GPG

### Opción A: Usando el script automatizado

```bash
cd hub
./scripts/generate-gpg-key.sh
```

Este script generará:
- `gpg-private-key.asc` - Clave privada (para GitHub Secrets)
- `gpg-public-key.asc` - Clave pública (para publicar)
- Key ID en consola

### Opción B: Manualmente

```bash
# Generar clave
gpg --full-generate-key

# Configuración recomendada:
# - Tipo: RSA and RSA
# - Longitud: 4096
# - Validez: 5y
# - Nombre: CPOS Team
# - Email: releases@erplora.com
# - Comentario: CPOS Hub Release Signing Key
# - Passphrase: (dejar vacío para CI/CD)

# Obtener Key ID
gpg --list-keys releases@erplora.com

# Exportar clave privada
gpg --armor --export-secret-keys <KEY_ID> > gpg-private-key.asc

# Exportar clave pública
gpg --armor --export <KEY_ID> > gpg-public-key.asc
```

---

## 🔒 Paso 2: Configurar GitHub Secrets

Ve a: `https://github.com/ERPlora/hub/settings/secrets/actions`

### Secret 1: GPG_PRIVATE_KEY

1. Click "New repository secret"
2. Name: `GPG_PRIVATE_KEY`
3. Value: **Contenido completo** de `gpg-private-key.asc`
   ```
   -----BEGIN PGP PRIVATE KEY BLOCK-----

   [contenido largo de la clave]

   -----END PGP PRIVATE KEY BLOCK-----
   ```
4. Click "Add secret"

### Secret 2: GPG_KEY_ID

1. Click "New repository secret"
2. Name: `GPG_KEY_ID`
3. Value: El Key ID (40 caracteres hexadecimales)
   ```
   ABCD1234EFGH5678...
   ```
4. Click "Add secret"

---

## 📢 Paso 3: Publicar Clave Pública

### En el repositorio

```bash
# Copiar clave pública al repositorio
cp gpg-public-key.asc GPG-PUBLIC-KEY.asc

# Agregar al repositorio
git add GPG-PUBLIC-KEY.asc
git commit -m "chore: add GPG public key for release verification"
git push origin main
```

### En servidor de claves (opcional)

```bash
# Publicar en servidor de claves público
gpg --keyserver keys.openpgp.org --send-keys <KEY_ID>

# También en otros servidores
gpg --keyserver keyserver.ubuntu.com --send-keys <KEY_ID>
gpg --keyserver pgp.mit.edu --send-keys <KEY_ID>
```

---

## ✅ Paso 4: Verificar Configuración

### Test local

```bash
# Simular el proceso de firma
export GPG_PRIVATE_KEY="$(cat gpg-private-key.asc)"
export GPG_KEY_ID="<tu-key-id>"

# Crear archivo de prueba
echo "test" > test.txt

# Firmar
./scripts/sign-release.sh test.txt

# Verificar
gpg --verify test.txt.asc test.txt
```

### Test en GitHub Actions

1. Hacer un commit y push a `main`
2. Ejecutar workflow `build-release.yml` manualmente
3. Verificar que se generan archivos `.asc` en la release
4. Descargar un archivo y verificar la firma localmente

---

## 🔄 Paso 5: Actualizar Workflows

Los workflows ya están configurados para firmar automáticamente:

### build-release.yml (manual)

- ✅ Importa clave GPG desde secrets
- ✅ Firma cada archivo (Windows, macOS, Linux)
- ✅ Sube firmas junto con archivos
- ✅ Publica en GitHub Release

### release.yml (automático staging)

Si quieres también firmar las prereleases de staging, agrega los mismos pasos de firma.

---

## 📚 Documentación para Usuarios

Crea documentación para que los usuarios sepan verificar las firmas:

- ✅ Ya creado: `docs/SIGNATURE_VERIFICATION.md`
- ✅ Mencionar en README.md
- ⏳ Agregar a página web (erplora.com/security)

---

## 🔐 Seguridad de la Clave Privada

### ✅ DO

- **Guardar la clave privada en lugar seguro**:
  - Password manager (1Password, Bitwarden, etc.)
  - Backup cifrado offline
  - GitHub Secrets (para CI/CD)

- **Rotar la clave si se compromete**:
  ```bash
  # Revocar clave comprometida
  gpg --gen-revoke <KEY_ID> > revoke.asc
  gpg --import revoke.asc
  gpg --keyserver keys.openpgp.org --send-keys <KEY_ID>

  # Generar nueva clave
  ./scripts/generate-gpg-key.sh
  ```

- **Documentar el fingerprint** en múltiples lugares

### ❌ DON'T

- ❌ **Subir la clave privada a Git**
- ❌ Compartir la clave privada por email/chat
- ❌ Usar la misma clave para múltiples propósitos
- ❌ Dejar la clave sin backup

---

## 🛠️ Troubleshooting

### Error: "No secret key"

```bash
# Verificar que la clave está importada
gpg --list-secret-keys
```

Si no aparece, reimportar:
```bash
echo "$GPG_PRIVATE_KEY" | gpg --import
```

### Error: "signing failed: Inappropriate ioctl for device"

```bash
# Configurar GPG para modo no interactivo
export GPG_TTY=$(tty)
echo "use-agent" >> ~/.gnupg/gpg.conf
```

### Error: "Public key not found" al verificar

Los usuarios necesitan importar tu clave pública primero:
```bash
curl -O https://raw.githubusercontent.com/ERPlora/hub/main/GPG-PUBLIC-KEY.asc
gpg --import GPG-PUBLIC-KEY.asc
```

---

## 📊 Checklist de Implementación

- [ ] Generar clave GPG (4096-bit RSA)
- [ ] Configurar `GPG_PRIVATE_KEY` en GitHub Secrets
- [ ] Configurar `GPG_KEY_ID` en GitHub Secrets
- [ ] Publicar clave pública en repositorio (`GPG-PUBLIC-KEY.asc`)
- [ ] Publicar clave en servidores públicos (opcional)
- [ ] Test de firma local con scripts
- [ ] Test de workflow completo en GitHub Actions
- [ ] Verificar que firmas aparecen en releases
- [ ] Documentar proceso de verificación para usuarios
- [ ] Guardar backup seguro de clave privada
- [ ] Documentar Key ID y fingerprint

---

## 📅 Mantenimiento

### Renovar clave (antes de expiración)

```bash
# Extender validez de la clave
gpg --edit-key releases@erplora.com
> expire
> 5y
> save

# Re-exportar y actualizar en GitHub Secrets
gpg --armor --export-secret-keys <KEY_ID> > gpg-private-key-new.asc
```

### Auditoría anual

- Verificar que la clave no ha sido comprometida
- Revisar logs de uso en GitHub Actions
- Verificar que backups están seguros
- Actualizar documentación si hay cambios

---

**Última actualización**: 2025-01-07

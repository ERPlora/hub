# GPG Key Storage Guide

Guía de almacenamiento seguro de las claves GPG de CPOS Hub.

## 🔐 Resumen de Claves

| Archivo | Tipo | ¿Subir a Git? | Ubicación |
|---------|------|---------------|-----------|
| `GPG-PUBLIC-KEY.asc` | Clave pública | ✅ SÍ | Repositorio público |
| `gpg-private-key.asc` | Clave privada | ❌ NUNCA | GitHub Secrets + Backup seguro |
| Key ID: `998A98EF7BE1D222837D30EBC27E75F06D413478` | Identificador | N/A | GitHub Secrets |

---

## 1️⃣ Clave Pública (Repositorio) ✅

### Ubicación
```
hub/GPG-PUBLIC-KEY.asc
```

### Estado
✅ Ya está en el repositorio: [GPG-PUBLIC-KEY.asc](../GPG-PUBLIC-KEY.asc)

### Propósito
- Los usuarios la descargan para verificar firmas
- Es seguro compartirla públicamente
- Necesita estar accesible en GitHub

### Verificación
```bash
# Ver clave pública
cat hub/GPG-PUBLIC-KEY.asc

# Importar clave
gpg --import hub/GPG-PUBLIC-KEY.asc

# Ver info de la clave
gpg --list-keys releases@cpos.app
```

---

## 2️⃣ Clave Privada (NUNCA en repositorio) ❌

### ⚠️ IMPORTANTE
**NUNCA subir al repositorio. Si se filtra, cualquiera puede firmar releases falsos.**

### Ubicaciones Recomendadas

#### A. GitHub Secrets (OBLIGATORIO para CI/CD)

1. Ir a: https://github.com/cpos-app/hub/settings/secrets/actions
2. Click "New repository secret"
3. Crear secreto:
   - **Name**: `GPG_PRIVATE_KEY`
   - **Value**: Contenido completo de `gpg-private-key.asc`
   ```bash
   # Copiar contenido al clipboard (macOS)
   cat gpg-private-key.asc | pbcopy

   # Linux
   cat gpg-private-key.asc | xclip -selection clipboard

   # Windows
   type gpg-private-key.asc | clip
   ```
4. Click "Add secret"

#### B. Password Manager (RECOMENDADO)

Guardar en tu gestor de contraseñas preferido:

**1Password**:
```
Título: CPOS Hub GPG Private Key
Tipo: Secure Note
Contenido: [pegar contenido de gpg-private-key.asc]
Tags: gpg, cpos, releases
```

**Bitwarden**:
```
Nombre: CPOS Hub GPG Private Key
Tipo: Nota segura
Notas: [pegar contenido de gpg-private-key.asc]
Carpeta: Development Keys
```

**LastPass**:
```
Nombre: CPOS Hub GPG Private Key
Tipo: Nota segura
Notas: [pegar contenido de gpg-private-key.asc]
```

#### C. Backup Offline Cifrado (RECOMENDADO)

Para recuperación ante desastres:

```bash
# 1. Cifrar la clave privada con AES256
gpg --symmetric --cipher-algo AES256 gpg-private-key.asc

# Te pedirá una contraseña fuerte
# Resultado: gpg-private-key.asc.gpg (archivo cifrado)

# 2. Guardar en:
#    - USB cifrado
#    - Disco externo en caja fuerte
#    - Almacenamiento en la nube cifrado (ej: Tresorit, ProtonDrive)

# 3. Descifrar cuando necesites (emergencia):
gpg --decrypt gpg-private-key.asc.gpg > gpg-private-key-recovered.asc
```

#### D. Sistema GPG Local (RECOMENDADO)

La clave ya está importada en tu sistema:

```bash
# Ver claves privadas en tu sistema
gpg --list-secret-keys

# Exportar desde tu keyring cuando necesites
gpg --armor --export-secret-keys 998A98EF7BE1D222837D30EBC27E75F06D413478 > gpg-private-key-export.asc

# Backup del keyring completo
cp -r ~/.gnupg ~/Backups/gnupg-backup-$(date +%Y%m%d)
```

---

## 3️⃣ Key ID (GitHub Secrets)

### Valor
```
998A98EF7BE1D222837D30EBC27E75F06D413478
```

### Ubicación
GitHub Secrets: https://github.com/cpos-app/hub/settings/secrets/actions

### Pasos
1. Click "New repository secret"
2. **Name**: `GPG_KEY_ID`
3. **Value**: `998A98EF7BE1D222837D30EBC27E75F06D413478`
4. Click "Add secret"

---

## 🗑️ Limpieza de Archivos Temporales

Después de guardar la clave privada en ubicaciones seguras:

```bash
cd /Users/ioan/Desktop/code/cpos/hub

# Borrar archivo temporal (solo después de guardarlo en Password Manager)
rm gpg-private-key.asc

# Verificar que no quede rastro
ls -la gpg-private-key.asc  # Debe dar error "No such file"

# Verificar que NO esté en git
git status  # No debe aparecer gpg-private-key.asc
```

### ⚠️ Antes de borrar, verifica que tienes la clave en:
- ✅ GitHub Secrets (GPG_PRIVATE_KEY)
- ✅ Password Manager
- ✅ Backup cifrado offline
- ✅ Sistema GPG local (`gpg --list-secret-keys`)

---

## 🔄 Recuperación de Clave Privada

Si pierdes acceso a la clave privada:

### Desde GitHub Secrets
❌ No es posible. GitHub Secrets son write-only (no se pueden leer).

### Desde Password Manager
✅ Copiar contenido y guardarlo en archivo:
```bash
# Pegar desde clipboard
pbpaste > gpg-private-key-recovered.asc  # macOS

# Importar a GPG
gpg --import gpg-private-key-recovered.asc
```

### Desde Backup Cifrado
✅ Descifrar y usar:
```bash
gpg --decrypt gpg-private-key.asc.gpg > gpg-private-key-recovered.asc
gpg --import gpg-private-key-recovered.asc
```

### Desde Sistema GPG Local
✅ Re-exportar:
```bash
gpg --armor --export-secret-keys 998A98EF7BE1D222837D30EBC27E75F06D413478 > gpg-private-key-export.asc
```

---

## 📋 Checklist de Configuración

### Paso 1: Clave Pública
- [x] Archivo `GPG-PUBLIC-KEY.asc` en repositorio
- [x] Commit y push a main
- [x] Verificar en GitHub: https://github.com/cpos-app/hub/blob/main/GPG-PUBLIC-KEY.asc

### Paso 2: Clave Privada
- [ ] Subir a GitHub Secrets (`GPG_PRIVATE_KEY`)
- [ ] Guardar en Password Manager
- [ ] Crear backup cifrado offline
- [ ] Verificar que está en sistema GPG local

### Paso 3: Key ID
- [ ] Subir a GitHub Secrets (`GPG_KEY_ID`)

### Paso 4: Limpieza
- [ ] Borrar `gpg-private-key.asc` del disco
- [ ] Verificar que NO está en git

### Paso 5: Prueba
- [ ] Ejecutar workflow `build-release.yml` manualmente
- [ ] Verificar que se generan archivos `.asc`
- [ ] Descargar y verificar firma localmente

---

## 🔒 Buenas Prácticas

### DO ✅
- Guardar clave privada en password manager
- Crear backup cifrado offline
- Rotar clave si se compromete
- Renovar clave antes de expiración (2029)
- Mantener keyring GPG actualizado

### DON'T ❌
- NUNCA subir clave privada a git
- NUNCA compartir clave privada por email/chat
- NUNCA guardar clave privada sin cifrar en la nube
- NUNCA usar la misma clave para otros proyectos
- NUNCA commitear archivo `gpg-private-key.asc`

---

## 📞 Soporte

Si tienes dudas sobre el almacenamiento de claves:

1. Consultar [GPG_SETUP.md](GPG_SETUP.md)
2. Consultar [SIGNATURE_VERIFICATION.md](SIGNATURE_VERIFICATION.md)
3. Abrir issue en GitHub

---

**Última actualización**: 2025-01-07

# ERPlora Hub - Instaladores Nativos

Este directorio contiene scripts para crear instaladores nativos de ERPlora Hub para cada plataforma.

---

## 📦 Formatos de Distribución

| Plataforma | Formato | Características |
|------------|---------|-----------------|
| **Windows** | `.exe` (InnoSetup) | Instalador con autostart |
| **macOS** | `.dmg` | DMG firmado (drag & drop) |
| **Linux** | `.AppImage` | AppImage portable con autostart |

---

## 🪟 Windows - Instalador InnoSetup

### Requisitos
- Inno Setup 6+ instalado
- O Chocolatey: `choco install innosetup`

### Crear Instalador

```powershell
# Opción 1: Script automático
cd installers/windows
.\build-installer.ps1 -Version "0.8.0"

# Opción 2: Manual
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" setup.iss
```

### Características del Instalador

- **Ubicación**: `C:\Program Files\ERPlora Hub\`
- **Autostart**: Opción durante instalación (añade a carpeta Inicio)
- **Accesos directos**:
  - Menú Inicio
  - Escritorio (opcional)
- **Registro**: Añade entradas en Windows Registry
- **Desinstalador**: Incluido en Panel de Control
- **Admin**: Requiere permisos de administrador

### Estructura del Instalador

```
installers/windows/
├── setup.iss           # Script de Inno Setup
└── build-installer.ps1 # Script de build automatizado
```

### Resultado
```
dist/CPOS-Hub-0.8.0-windows-installer.exe
```

---

## 🍎 macOS - DMG Firmado

### Requisitos
- macOS 10.13+
- Xcode Command Line Tools: `xcode-select --install`
- Apple Developer ID (opcional, para firma)

### Crear DMG

```bash
cd installers/macos
chmod +x sign-and-package.sh
./sign-and-package.sh 0.8.0
```

### Características del DMG

- **Formato**: DMG montable
- **Instalación**: Drag & Drop a /Applications
- **Firma**: Con Developer ID (si está disponible)
- **Compresión**: UDZO (zlib-9)
- **Icono**: Personalizado
- **Alias**: Incluye alias a /Applications

### Estructura del Script

```
installers/macos/
├── sign-and-package.sh  # Script de firma y packaging
└── entitlements.plist   # Entitlements para firma
```

### Firma (Opcional)

Si tienes Apple Developer ID:
1. El script detecta automáticamente el certificado
2. Firma con `codesign --sign "Developer ID Application"`
3. Opción de notarización (manual)

**Sin Developer ID:**
- La aplicación se crea sin firmar
- Los usuarios verán advertencia en primera ejecución
- Click derecho → Abrir para ejecutar

### Resultado
```
CPOS-Hub-0.8.0-macos.dmg
```

---

## 🐧 Linux - AppImage

### Requisitos
- `fuse` y `libfuse2` instalados
- `appimagetool` (se descarga automáticamente)

```bash
# Ubuntu/Debian
sudo apt-get install fuse libfuse2

# Fedora
sudo dnf install fuse fuse-libs

# Arch
sudo pacman -S fuse2
```

### Crear AppImage

```bash
cd installers/linux
chmod +x create-appimage.sh
./create-appimage.sh 0.8.0
```

### Características del AppImage

- **Portable**: No requiere instalación
- **Autostart**: Se configura automáticamente en primera ejecución
- **Ubicación autostart**: `~/.config/autostart/cpos-hub.desktop`
- **Permisos**: Usuario actual (no root)
- **Desktop Entry**: Incluido para integración con DE
- **Icon**: Integrado en AppImage

### Estructura del Script

```
installers/linux/
└── create-appimage.sh  # Script de creación de AppImage
```

### Autostart en Linux

El AppImage crea automáticamente el archivo de autostart:

```desktop
# ~/.config/autostart/cpos-hub.desktop
[Desktop Entry]
Type=Application
Name=ERPlora Hub
Exec=/path/to/CPOS-Hub-0.8.0-x86_64.AppImage
Icon=cpos-hub
Terminal=false
X-GNOME-Autostart-enabled=true
```

### Ejecutar AppImage

```bash
# Dar permisos de ejecución
chmod +x CPOS-Hub-0.8.0-x86_64.AppImage

# Ejecutar
./CPOS-Hub-0.8.0-x86_64.AppImage
```

### Resultado
```
CPOS-Hub-0.8.0-x86_64.AppImage
```

---

## 🔐 Firma GPG

Todos los instaladores se firman automáticamente con GPG en GitHub Actions.

### Verificar Firma

```bash
# Descargar clave pública
curl -sL https://erplora.com/api/gpg/public-key/ | gpg --import

# Verificar instalador
gpg --verify CPOS-Hub-0.8.0-windows-installer.exe.asc CPOS-Hub-0.8.0-windows-installer.exe
gpg --verify CPOS-Hub-0.8.0-macos.dmg.asc CPOS-Hub-0.8.0-macos.dmg
gpg --verify CPOS-Hub-0.8.0-x86_64.AppImage.asc CPOS-Hub-0.8.0-x86_64.AppImage
```

---

## 🚀 CI/CD - GitHub Actions

Los instaladores se crean automáticamente en GitHub Actions:

```yaml
# .github/workflows/build-release.yml
# Ejecutar manualmente:
# 1. Ir a Actions → Build Release Executables
# 2. Run workflow → Ingresar versión
# 3. Esperar build (~15-20 min)
# 4. Descargar de Releases
```

### Proceso Automático

1. **Build PyInstaller** (3 plataformas en paralelo)
2. **Crear instaladores**:
   - Windows: InnoSetup
   - macOS: DMG firmado
   - Linux: AppImage
3. **Firma GPG** de todos los archivos
4. **Upload a GitHub Release**

---

## 📊 Comparación de Instaladores

| Característica | Windows (.exe) | macOS (.dmg) | Linux (.AppImage) |
|----------------|----------------|--------------|-------------------|
| **Autostart** | ✅ Sí (opcional) | ❌ No | ✅ Sí (automático) |
| **Instalación** | C:\Program Files | Drag & Drop | No requiere |
| **Admin** | Sí (instalación) | No | No |
| **Desinstalador** | Sí (incluido) | Arrastrar a Papelera | Borrar archivo |
| **Accesos** | Menú + Escritorio | Applications | Menu DE |
| **Tamaño** | ~150 MB | ~150 MB | ~150 MB |
| **Firma** | GPG | Code Sign + GPG | GPG |

---

## 🛠️ Desarrollo Local

### Probar Instaladores Localmente

**Windows:**
```powershell
# 1. Build con PyInstaller
pyinstaller main.spec

# 2. Crear instalador
cd installers/windows
.\build-installer.ps1 -Version "0.8.0"

# 3. Probar
dist\CPOS-Hub-0.8.0-Setup.exe
```

**macOS:**
```bash
# 1. Build con PyInstaller
pyinstaller main.spec

# 2. Crear DMG
cd installers/macos
./sign-and-package.sh 0.8.0

# 3. Montar y probar
open CPOS-Hub-0.8.0-macos.dmg
```

**Linux:**
```bash
# 1. Build con PyInstaller
pyinstaller main.spec

# 2. Crear AppImage
cd installers/linux
./create-appimage.sh 0.8.0

# 3. Ejecutar
chmod +x CPOS-Hub-0.8.0-x86_64.AppImage
./CPOS-Hub-0.8.0-x86_64.AppImage
```

---

## 📝 Notas de Implementación

### Windows
- Autostart usa carpeta: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
- Requiere permisos admin para instalar en Program Files
- Registro en: `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall`

### macOS
- No implementa autostart (según especificación)
- Usuarios pueden agregar manualmente: System Settings → Users & Groups → Login Items
- Firma opcional con Developer ID

### Linux
- Autostart usa: `~/.config/autostart/` (XDG standard)
- Compatible con: GNOME, KDE, XFCE, MATE, Cinnamon
- AppImage integrado con Desktop Environment

---

## 🔄 Actualización de Versión

Para crear nueva versión en todas las plataformas:

```bash
# Actualizar pyproject.toml
# version = "0.9.0"

# GitHub Actions (recomendado)
# 1. Push a main
# 2. Run workflow con nueva versión

# O manual en cada plataforma
./installers/windows/build-installer.ps1 -Version "0.9.0"
./installers/macos/sign-and-package.sh 0.9.0
./installers/linux/create-appimage.sh 0.9.0
```

---

## 📞 Soporte

- **Documentación**: [docs/README.md](../docs/README.md)
- **Issues**: https://github.com/cpos-app/hub/issues
- **Website**: https://erplora.com

---

**Última actualización**: 2025-11-07

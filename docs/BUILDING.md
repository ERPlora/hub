# CPOS Hub - Build System

Sistema de empaquetado multi-plataforma para CPOS Hub usando PyInstaller.

## 🎯 Características

- ✅ **Django embebido** - No requiere Python instalado
- ✅ **pywebview** - Navegador nativo sin dependencias externas
- ✅ **Onedir mode** - Archivos visibles y fáciles de depurar
- ✅ **Multi-plataforma** - Windows, macOS y Linux
- ✅ **GitHub Actions** - Builds automáticos en CI/CD

## 📦 Estructura

```
hub/
├── main.py              # Entry point (cross-platform) - root del proyecto
├── main.spec            # PyInstaller spec (cross-platform) - root del proyecto
├── assets/              # Assets de la aplicación
│   ├── app_icon.ico     # Icono para Windows
│   ├── app_icon.icns    # Icono para macOS
│   └── logo.png         # Logo fuente
├── pyi_hooks/           # Hooks personalizados de PyInstaller
│   └── hook-django.py   # Hook Django personalizado (previene errores)
├── pyproject.toml       # Dependencias y config (fuente única de verdad)
└── docs/
    └── BUILDING.md      # Este archivo
```

## 🚀 Build Local

### Requisitos

- Python 3.11+
- uv (package manager)

### Pasos

```bash
# 1. Instalar dependencias
cd hub
uv venv  # Crea .venv automáticamente
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
uv pip install -e .  # Instala desde pyproject.toml

# 2. Crear base de datos (REQUERIDO antes del build)
python manage.py migrate --noinput

# 3. Build
pyinstaller main.spec --clean

# 4. Resultado
# macOS: dist/CPOS Hub.app
# Windows: dist/main/main.exe
# Linux: dist/main/main
```

**IMPORTANTE:** La base de datos SQLite (`db.sqlite3`) debe existir antes del build y se empaqueta con la aplicación. El workflow de GitHub Actions la crea automáticamente.

## 🤖 Build Automático (GitHub Actions)

### Workflow 1: Prereleases Automáticas (staging)

**Archivo**: `.github/workflows/release.yml`

**Triggers**: Push a `staging`

**Proceso**:
1. Semantic-release analiza commits convencionales
2. Crea versión con sufijo `-rc.X` (ej: `0.8.0-rc.1`)
3. Actualiza `pyproject.toml` y `CHANGELOG.md`
4. Crea tag `v0.8.0-rc.1`
5. Construye ejecutables para Windows, macOS y Linux en paralelo
6. Publica GitHub Release marcada como prerelease

**Artifacts**:
- **Linux**: `CPOS-Hub-0.8.0-rc.1-linux.tar.gz`
- **Windows**: `CPOS-Hub-0.8.0-rc.1-windows.zip`
- **macOS**: `CPOS-Hub-0.8.0-rc.1-macos.zip`

### Workflow 2: Releases Finales (main) - MANUAL

**Archivo**: `.github/workflows/build-release.yml`

**Triggers**: Manual (`workflow_dispatch`)

**Por qué es manual**: Cuando se hace merge de `staging → main`, semantic-release en main no crea automáticamente una nueva versión porque detecta que los commits ya fueron versionados en staging como prerelease. Python-semantic-release v9 no tiene feature de "promoción de prerelease a estable".

**Proceso**:

1. **Merge staging a main**:
   ```bash
   git checkout main
   git merge staging
   git push origin main
   ```

2. **Actualizar versión manualmente**:
   ```bash
   # Editar pyproject.toml
   # De: version = "0.8.0-rc.4"
   # A:  version = "0.8.0"

   git add pyproject.toml
   git commit -m "chore(release): bump to 0.8.0"
   git push origin main

   git tag v0.8.0
   git push origin v0.8.0
   ```

3. **Ejecutar workflow manual**:
   - Ir a: https://github.com/cpos-app/hub/actions/workflows/build-release.yml
   - Click "Run workflow"
   - Ingresar versión: `0.8.0` (sin `v`)
   - Marcar "Create GitHub Release": ✅
   - Click "Run workflow"
   - Esperar ~15 minutos

4. **Resultado**:
   - Release en: `https://github.com/cpos-app/hub/releases/tag/v0.8.0`
   - Con binarios:
     - `CPOS-Hub-0.8.0-windows.zip`
     - `CPOS-Hub-0.8.0-macos.zip`
     - `CPOS-Hub-0.8.0-linux.tar.gz`

### Workflow 3: Builds de Desarrollo (develop)

**Archivo**: `.github/workflows/build-executables.yml`

**Triggers**: Push a `develop`

**Proceso**: Solo construye ejecutables sin crear releases (para testing de CI/CD)

## 🔧 Configuración

### main.py

Entry point cross-platform que:
1. Detecta la plataforma (Windows/Linux/macOS)
2. Localiza el directorio hub correcto
3. Inicia Django en un thread daemon
4. Abre pywebview con la interfaz

### main.spec

Configuración PyInstaller que:
1. Incluye Django y todas las dependencias
2. Empaqueta el proyecto hub completo
3. Configura iconos por plataforma
4. Crea .app bundle en macOS (opcional en otras plataformas)

### Hiddenimports

Los siguientes módulos se incluyen explícitamente:

```python
- django (core y contrib apps)
- decouple
- webview
- pyobjc (macOS)
```

## 📋 Datas (Archivos incluidos)

```python
- hub/manage.py
- hub/config/
- hub/apps/
- hub/static/
- hub/locale/
- hub/db.sqlite3
```

## 🐛 Troubleshooting

### Error: ModuleNotFoundError

Si falta un módulo, agrégalo a `hiddenimports` en `main.spec`:

```python
hiddenimports=[
    'django',
    'tu_modulo_aqui',
]
```

### Error: Hub directory not found

Verifica que la estructura de directorios sea correcta:

- macOS: `.app/Contents/MacOS/_internal/hub/`
- Windows/Linux: `./_internal/hub/`

### Django no arranca

Verifica que:
1. `decouple` esté instalado
2. `config/settings.py` exista
3. El puerto 8001 esté libre

## 📊 Tamaños aproximados

- **macOS**: ~150MB (CPOS Hub.app)
- **Windows**: ~120MB (comprimido)
- **Linux**: ~110MB (comprimido)

## 🔄 Flujo de desarrollo

1. **Desarrollo local**: Usa `python manage.py runserver`
2. **Test build local**: `pyinstaller main.spec`
3. **Test funcional**: Ejecuta el binario
4. **Commit**: Push a develop/staging
5. **Release**: Tag `v*` para crear release

## 📝 Notas

- **Python 3.11** se usa en CI/CD (mejor compatibilidad que 3.14)
- **Onedir mode** es más fácil de depurar que onefile
- **pywebview** usa el navegador del sistema (WebKit/Edge/Chromium)
- **console=False** en producción (sin ventana de consola)

## 🆘 Soporte

Para issues o preguntas, consulta la documentación en `../docs/` o abre un issue en GitHub.

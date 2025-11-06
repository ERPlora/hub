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

El workflow `.github/workflows/build-executables.yml` construye automáticamente para las 3 plataformas:

### Triggers

- Push a `main`, `staging`, `develop`
- Tags `v*` (releases)
- Pull requests a `main`, `staging`
- Manual (`workflow_dispatch`)

### Artifacts

- **Linux**: `CPOS-Hub-Linux-x64.tar.gz`
- **Windows**: `CPOS-Hub-Windows-x64.zip`
- **macOS**: `CPOS-Hub-macOS-arm64.dmg`

### Releases

Cuando se crea un tag `v*`, se genera automáticamente un release en GitHub con los 3 binarios.

```bash
# Crear release
git tag v1.0.0
git push origin v1.0.0
```

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

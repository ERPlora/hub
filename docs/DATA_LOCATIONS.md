# Ubicaciones de Datos de Usuario - CPOS Hub

CPOS Hub almacena todos los datos de usuario **fuera de la aplicación** para garantizar la persistencia entre actualizaciones y reinstalaciones.

---

## 📁 Ubicaciones por Plataforma

### 🪟 Windows

**Directorio base**: `C:\Users\<usuario>\AppData\Local\CPOSHub\`

```
C:\Users\<usuario>\AppData\Local\CPOSHub\
├── db\
│   └── db.sqlite3          # Base de datos principal
├── media\                  # Archivos subidos (imágenes, documentos)
│   ├── products\           # Imágenes de productos
│   ├── categories\         # Imágenes de categorías
│   └── plugins\            # Media de plugins
├── plugins\                # Plugins instalados y sus datos
│   ├── plugin-id\
│   │   ├── data\           # Datos del plugin
│   │   └── ...
├── reports\                # Reportes generados (PDF, Excel)
├── logs\                   # Logs de la aplicación
│   └── cpos-hub.log
├── backups\                # Backups automáticos de la DB
└── temp\                   # Archivos temporales
```

**Acceder al directorio**:
```cmd
# Desde CMD
cd %LOCALAPPDATA%\CPOSHub

# Desde PowerShell
cd $env:LOCALAPPDATA\CPOSHub

# Desde Explorer
Presiona Win+R → escribe: %LOCALAPPDATA%\CPOSHub
```

---

### 🍎 macOS

**Directorio base**: `~/Library/Application Support/CPOSHub/`

```
~/Library/Application Support/CPOSHub/
├── db/
│   └── db.sqlite3          # Base de datos principal
├── media/                  # Archivos subidos (imágenes, documentos)
│   ├── products/           # Imágenes de productos
│   ├── categories/         # Imágenes de categorías
│   └── plugins/            # Media de plugins
├── plugins/                # Plugins instalados y sus datos
│   ├── plugin-id/
│   │   ├── data/           # Datos del plugin
│   │   └── ...
├── reports/                # Reportes generados (PDF, Excel)
├── logs/                   # Logs de la aplicación
│   └── cpos-hub.log
├── backups/                # Backups automáticos de la DB
└── temp/                   # Archivos temporales
```

**Acceder al directorio**:
```bash
# Desde Terminal
cd ~/Library/Application\ Support/CPOSHub

# Desde Finder
Presiona Cmd+Shift+G → escribe: ~/Library/Application Support/CPOSHub
```

**Nota**: El directorio `Library` está oculto por defecto en macOS. La aplicación lo marca como oculto automáticamente para no aparecer en búsquedas normales.

---

### 🐧 Linux

**Directorio base**: `~/.cpos-hub/`

```
~/.cpos-hub/
├── db/
│   └── db.sqlite3          # Base de datos principal
├── media/                  # Archivos subidos (imágenes, documentos)
│   ├── products/           # Imágenes de productos
│   ├── categories/         # Imágenes de categorías
│   └── plugins/            # Media de plugins
├── plugins/                # Plugins instalados y sus datos
│   ├── plugin-id/
│   │   ├── data/           # Datos del plugin
│   │   └── ...
├── reports/                # Reportes generados (PDF, Excel)
├── logs/                   # Logs de la aplicación
│   └── cpos-hub.log
├── backups/                # Backups automáticos de la DB
└── temp/                   # Archivos temporales
```

**Acceder al directorio**:
```bash
# Desde terminal
cd ~/.cpos-hub

# Ver archivos ocultos en file manager
# GNOME Files: Ctrl+H
# Dolphin: Alt+.
# Thunar: Ctrl+H
```

**Nota**: El punto (`.`) al inicio del nombre hace que el directorio sea oculto por defecto en sistemas POSIX.

---

## 🔄 Migración Automática

### Primera Ejecución

La primera vez que ejecutes CPOS Hub después de actualizar:

1. **Detecta datos legacy**: Si existen datos en el directorio de la app antigua
2. **Crea directorios externos**: En la ubicación apropiada para la plataforma
3. **Migra datos automáticamente**:
   - `db.sqlite3` → Ubicación externa
   - `media/` → Ubicación externa
   - `plugins/` → Ubicación externa
4. **Crea backup**: El archivo original se renombra como `.legacy`
5. **Continúa normalmente**: Usa las nuevas ubicaciones

### Proceso de Migración

```
[INFO] Initializing data directories...
[INFO] Platform: darwin
[INFO] Base data directory: /Users/user/Library/Application Support/CPOSHub
[INFO] Database: /Users/user/Library/Application Support/CPOSHub/db/db.sqlite3

[INFO] Migrating legacy database from /path/to/app/hub/db.sqlite3
[OK] Database migrated to /Users/user/Library/Application Support/CPOSHub/db/db.sqlite3
[OK] Legacy database backed up to /path/to/app/hub/db.sqlite3.legacy

[INFO] Migrating legacy media from /path/to/app/hub/media
[OK] Media migrated to /Users/user/Library/Application Support/CPOSHub/media

[OK] Data directories initialized successfully
```

---

## 📊 Tamaños Esperados

| Directorio | Tamaño Típico | Descripción |
|------------|---------------|-------------|
| `db/` | 10-100 MB | Base de datos SQLite |
| `media/` | 100-500 MB | Imágenes de productos, logos |
| `plugins/` | 50-200 MB | Plugins y sus datos |
| `reports/` | 10-50 MB | PDFs y Excel generados |
| `logs/` | 5-20 MB | Logs rotativos (máx 50 MB) |
| `backups/` | 50-500 MB | Backups automáticos de DB |
| `temp/` | 0-50 MB | Temporal (se limpia al cerrar) |

**Total aproximado**: 225-1420 MB

---

## 🗂️ Gestión de Datos

### Ver Ubicaciones desde la App

```python
# Desde consola de Django shell
python manage.py shell

>>> from config.paths import get_data_paths
>>> paths = get_data_paths()
>>> print(paths.base_dir)
>>> print(paths.database_path)
>>> for name, path in paths.get_all_paths().items():
...     print(f"{name}: {path}")
```

### Backup Manual

```bash
# Windows (PowerShell)
Copy-Item -Recurse $env:LOCALAPPDATA\CPOSHub $env:USERPROFILE\Desktop\CPOSHub-Backup

# macOS / Linux
cp -r ~/.cpos-hub ~/Desktop/CPOSHub-Backup
# o
cp -r ~/Library/Application\ Support/CPOSHub ~/Desktop/CPOSHub-Backup
```

### Restaurar Backup

```bash
# Cerrar CPOS Hub primero

# Windows (PowerShell)
Copy-Item -Recurse $env:USERPROFILE\Desktop\CPOSHub-Backup\* $env:LOCALAPPDATA\CPOSHub

# macOS / Linux
cp -r ~/Desktop/CPOSHub-Backup/* ~/.cpos-hub/
# o
cp -r ~/Desktop/CPOSHub-Backup/* ~/Library/Application\ Support/CPOSHub/
```

### Limpiar Datos (Reset Completo)

```bash
# ⚠️ ADVERTENCIA: Esto borra TODOS los datos

# Windows (PowerShell)
Remove-Item -Recurse -Force $env:LOCALAPPDATA\CPOSHub

# macOS
rm -rf ~/Library/Application\ Support/CPOSHub

# Linux
rm -rf ~/.cpos-hub
```

---

## 🔐 Seguridad y Privacidad

### Permisos

- **Propietario**: Usuario actual
- **Lectura/Escritura**: Solo el usuario actual
- **Otros usuarios**: Sin acceso

### Backup

Los backups automáticos se crean:
- **Frecuencia**: Diaria (si hay cambios)
- **Retención**: Últimos 7 días
- **Ubicación**: `backups/db-YYYY-MM-DD.sqlite3`

### Encriptación

- **Base de datos**: No encriptada por defecto
- **Archivos media**: No encriptados
- **Logs**: Texto plano

**Nota**: Si necesitas encriptación, usa:
- Windows: BitLocker (encripta todo el disco)
- macOS: FileVault (encripta todo el disco)
- Linux: LUKS (encripta partición/disco)

---

## 🔧 Desarrollo

### Ubicación en Modo Desarrollo

En desarrollo (sin PyInstaller), los datos se guardan en las **mismas ubicaciones externas**:

```bash
# Desarrollo
python main.py
# Usa: ~/.cpos-hub/ (o equivalente)

# PyInstaller
./main
# Usa: ~/.cpos-hub/ (o equivalente)
```

### Variables de Entorno

Puedes sobrescribir la ubicación base:

```bash
# Linux/macOS
export CPOS_DATA_DIR=/custom/path
python main.py

# Windows
set CPOS_DATA_DIR=C:\custom\path
python main.py
```

**Nota**: Esta funcionalidad está disponible pero no recomendada para usuarios finales.

---

## ❓ FAQ

### ¿Por qué fuera de la app?

1. **Persistencia**: Los datos sobreviven a actualizaciones
2. **Backups**: Más fácil hacer backup de una carpeta
3. **Estándares**: Sigue las guías de cada plataforma
4. **Seguridad**: Separación de código y datos

### ¿Qué pasa al desinstalar?

Los datos **NO se borran automáticamente**. Debes borrar manualmente la carpeta de datos si quieres eliminar todo.

### ¿Puedo mover los datos?

No recomendado. La aplicación espera encontrar los datos en las ubicaciones estándar. Si necesitas moverlos, usa la variable `CPOS_DATA_DIR`.

### ¿Cómo migro datos entre computadoras?

1. Cierra CPOS Hub en ambas máquinas
2. Copia toda la carpeta de datos
3. Pega en la ubicación correspondiente de la otra máquina
4. Inicia CPOS Hub

### ¿Los datos se sincronizan con Cloud?

- **Configuración del Hub**: Sí (automático)
- **Productos/Ventas**: Sí (según configuración)
- **Media**: Opcional (configuración de plugin)
- **Logs**: No
- **Backups locales**: No

---

## 📞 Soporte

Si tienes problemas con las ubicaciones de datos:

1. Verifica permisos de escritura
2. Verifica espacio en disco
3. Revisa los logs en `logs/cpos-hub.log`
4. Contacta soporte: https://cpos.app/support

---

**Última actualización**: 2025-11-07

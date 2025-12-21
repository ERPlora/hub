# ERPlora Hub - Kiosk Mode

Sistema completo para ejecutar ERPlora Hub en modo kiosko (pantalla completa, sin interfaz de navegador).

## 🎯 ¿Qué es el Modo Kiosko?

El modo kiosko es ideal para:
- **Terminales POS dedicadas**: Dispositivos que solo ejecutan el POS
- **Tablets y kioscos**: Dispositivos de autoservicio
- **Tiendas físicas**: Pantallas dedicadas para ventas
- **Restaurantes**: Terminales de cocina y barra

**Características:**
- ✅ Pantalla completa (sin barra de navegador)
- ✅ Sin acceso a menús del navegador
- ✅ Enfoque total en la aplicación
- ✅ Soporta web (navegador) y desktop (PyInstaller)

---

## 📦 Archivos del Sistema

| Archivo | Descripción |
|---------|-------------|
| `launch-kiosk.sh` | Launcher kiosko para macOS/Linux (producción) |
| `launch-kiosk.bat` | Launcher kiosko para Windows (producción) |
| `launch-dev-kiosk.sh` | Launcher kiosko + Django dev server (macOS/Linux) |
| `launch-dev-kiosk.bat` | Launcher kiosko + Django dev server (Windows) |
| `README.md` | Esta documentación |

---

## 🚀 Uso en Producción

### macOS / Linux

```bash
# Auto-detecta si usar desktop app o browser
./launch-kiosk.sh

# Forzar modo browser (Chrome/Edge/Firefox en kiosko)
./launch-kiosk.sh --web

# Forzar desktop app (PyInstaller app)
./launch-kiosk.sh --desktop

# URL personalizada (ej: servidor remoto)
./launch-kiosk.sh --web --url https://erplora.com

# Puerto personalizado
./launch-kiosk.sh --port 8002
```

### Windows

```batch
REM Auto-detecta si usar desktop app o browser
launch-kiosk.bat

REM Forzar modo browser
launch-kiosk.bat --web

REM Forzar desktop app
launch-kiosk.bat --desktop

REM URL personalizada
launch-kiosk.bat --web --url https://erplora.com

REM Puerto personalizado
launch-kiosk.bat --port 8002
```

---

## 🛠️ Uso en Desarrollo

Para probar el modo kiosko durante desarrollo **sin necesidad de compilar la app desktop**.

### macOS / Linux

```bash
cd /path/to/cpos/hub/kiosk

# Inicia Django + browser en kiosko (puerto 8001 por defecto)
./launch-dev-kiosk.sh

# Puerto personalizado
./launch-dev-kiosk.sh --port 8002

# Virtual env personalizado
./launch-dev-kiosk.sh --venv ../.venv
```

### Windows

```batch
cd C:\path\to\cpos\hub\kiosk

REM Inicia Django + browser en kiosko
launch-dev-kiosk.bat

REM Puerto personalizado
launch-dev-kiosk.bat --port 8002

REM Virtual env personalizado
launch-dev-kiosk.bat --venv ..\.venv
```

**¿Qué hace `launch-dev-kiosk`?**
1. ✅ Activa el virtual environment
2. ✅ Mata procesos existentes en el puerto
3. ✅ Inicia Django development server en background
4. ✅ Espera a que Django esté listo
5. ✅ Abre navegador en modo kiosko
6. ✅ Cleanup automático al presionar Ctrl+C

**Logs:** Los logs de Django se guardan en:
- macOS/Linux: `/tmp/erplora-dev-kiosk.log`
- Windows: `%TEMP%\erplora-dev-kiosk.log`

---

## 🖥️ Desktop App (PyInstaller) con Kiosk Mode

La aplicación desktop compilada con PyInstaller ahora soporta el flag `--kiosk`.

### Actualización en `main.py`

```python
# Argumentos de línea de comandos
parser.add_argument('--kiosk', action='store_true',
                    help='Start in kiosk mode (fullscreen, no browser UI)')
parser.add_argument('--width', type=int, default=1200,
                    help='Window width (default: 1200)')
parser.add_argument('--height', type=int, default=800,
                    help='Window height (default: 800)')
```

### Usar la Desktop App en Kiosk Mode

**macOS:**
```bash
# Modo normal
/Applications/ERPlora\ Hub.app/Contents/MacOS/ERPlora\ Hub

# Modo kiosko
/Applications/ERPlora\ Hub.app/Contents/MacOS/ERPlora\ Hub --kiosk

# Kiosko con tamaño personalizado
/Applications/ERPlora\ Hub.app/Contents/MacOS/ERPlora\ Hub --kiosk --width 1920 --height 1080
```

**Windows:**
```batch
REM Modo normal
"C:\Program Files\ERPlora Hub\ERPloraHub.exe"

REM Modo kiosko
"C:\Program Files\ERPlora Hub\ERPloraHub.exe" --kiosk
```

**Linux:**
```bash
# Modo normal
/opt/erplora-hub/ERPloraHub

# Modo kiosko
/opt/erplora-hub/ERPloraHub --kiosk
```

---

## 🌐 Web Browser Kiosk Mode

Cuando usas el modo web (`--web`), el sistema detecta automáticamente el navegador disponible y lo lanza en modo kiosko.

### Navegadores Soportados

#### Chrome / Chromium / Edge
```bash
# Flags usados:
--kiosk                              # Pantalla completa sin UI
--no-first-run                       # Sin wizard de primera ejecución
--disable-pinch                      # Deshabilita zoom con gestos
--overscroll-history-navigation=0    # Sin navegación con gestos
--disable-features=Translate         # Sin popup de traducción
```

**Salir del modo kiosko:**
- macOS: `Cmd+Q` o `Cmd+W`
- Windows/Linux: `Alt+F4` o `F11`

#### Firefox
```bash
# Flag usado:
--kiosk  # Modo kiosko nativo de Firefox
```

**Salir del modo kiosko:**
- `F11` o `Alt+F4`

#### Safari (macOS)
Safari no soporta verdadero modo kiosko, pero se puede usar modo pantalla completa:
- **Entrar:** `Cmd+Ctrl+F` después de abrir
- **Salir:** `Cmd+Ctrl+F` o `Esc`

### Orden de Prioridad de Navegadores

**macOS:**
1. Google Chrome
2. Microsoft Edge
3. Safari (fallback, requiere fullscreen manual)

**Linux:**
1. Google Chrome
2. Chromium
3. Firefox

**Windows:**
1. Google Chrome
2. Microsoft Edge

---

## 🔧 Configuración Avanzada

### Auto-inicio en el Sistema (Producción)

#### macOS - LaunchAgent

Crea un archivo `~/Library/LaunchAgents/com.erplora.hub.kiosk.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.erplora.hub.kiosk</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/ERPlora Hub.app/Contents/MacOS/ERPlora Hub</string>
        <string>--kiosk</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Activar:
```bash
launchctl load ~/Library/LaunchAgents/com.erplora.hub.kiosk.plist
launchctl start com.erplora.hub.kiosk
```

#### Linux - systemd

Crea un archivo `/etc/systemd/system/erplora-hub-kiosk.service`:

```ini
[Unit]
Description=ERPlora Hub Kiosk Mode
After=network.target

[Service]
Type=simple
User=pos
ExecStart=/opt/erplora-hub/ERPloraHub --kiosk
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl enable erplora-hub-kiosk
sudo systemctl start erplora-hub-kiosk
```

#### Windows - Startup Folder

Crea un acceso directo en:
```
C:\Users\<user>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
```

**Destino:**
```
"C:\Program Files\ERPlora Hub\ERPloraHub.exe" --kiosk
```

---

## 🔒 Seguridad y Restricciones

### Deshabilitar Salida del Kiosk (Producción)

Para terminales POS en producción, es recomendable deshabilitar la capacidad de salir del modo kiosko.

#### macOS - Guided Access (iPad/Tablet)
Para iPads, usa "Guided Access" en Settings > Accessibility.

#### Windows - Assigned Access (Kiosk Mode)
Windows 10/11 Pro tiene "Assigned Access" para crear verdaderos kiosks:

```powershell
# PowerShell como administrador
Set-AssignedAccess -AppUserModelId "ERPloraHub" -UserName "KioskUser"
```

#### Linux - Kiosk Mode con X11
Edita `~/.xinitrc`:

```bash
#!/bin/bash
xset -dpms     # Disable DPMS (Energy Star)
xset s off     # Disable screen saver
xset s noblank # Don't blank the video device

/opt/erplora-hub/ERPloraHub --kiosk
```

---

## 🐛 Troubleshooting

### Problema: "No supported browser found"

**Solución:**
```bash
# macOS
brew install --cask google-chrome

# Linux (Ubuntu/Debian)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
sudo apt update
sudo apt install google-chrome-stable

# Windows
# Descargar instalador desde https://www.google.com/chrome/
```

### Problema: "Desktop app not found"

**Solución:** Compilar la app primero:
```bash
cd /path/to/cpos/hub
python build.py
```

### Problema: Django no inicia (dev kiosk)

**Solución:**
```bash
# Ver logs
tail -f /tmp/erplora-dev-kiosk.log  # macOS/Linux
type %TEMP%\erplora-dev-kiosk.log   # Windows

# Verificar puerto libre
lsof -i :8001  # macOS/Linux
netstat -ano | findstr :8001  # Windows

# Matar proceso existente
lsof -ti:8001 | xargs kill -9  # macOS/Linux
taskkill /F /PID <PID>  # Windows
```

### Problema: No puedo salir del modo kiosko

**Solución:**
- Chrome/Edge: `Alt+F4` (Windows/Linux), `Cmd+Q` (macOS)
- Firefox: `F11` o `Alt+F4`
- Safari: `Esc` o `Cmd+Ctrl+F`

Si no responde, usar Task Manager:
- macOS: `Cmd+Opt+Esc`
- Windows: `Ctrl+Shift+Esc`
- Linux: `Ctrl+Alt+Del`

---

## 📊 Comparativa: Web vs Desktop Kiosk

| Característica | Web Kiosk (Browser) | Desktop Kiosk (PyInstaller) |
|----------------|---------------------|------------------------------|
| **Instalación** | Solo navegador | Requiere compilar app |
| **Rendimiento** | Bueno | Excelente |
| **Impresión directa** | No (usa window.print) | Sí (Python → OS) |
| **Hardware USB** | No (sin drivers) | Sí (escáneres, básculas) |
| **Actualizaciones** | Automáticas (web) | Requiere rebuild |
| **Offline** | No | Sí |
| **Recomendado para** | Testing, desarrollo | Producción, POS físico |

---

## 🎨 Personalización

### Cambiar URL por Defecto

Editar scripts y cambiar:
```bash
# launch-kiosk.sh / launch-dev-kiosk.sh
URL="http://localhost:8001"

# O usar flag --url
./launch-kiosk.sh --web --url https://mi-servidor.com
```

### Cambiar Navegador Preferido

Editar `launch-kiosk.sh` y reordenar la sección de detección de navegadores:

```bash
# Ejemplo: Preferir Firefox sobre Chrome
if command -v firefox &> /dev/null; then
    echo "Using Firefox"
    firefox --kiosk "$URL" &
elif command -v google-chrome &> /dev/null; then
    echo "Using Google Chrome"
    google-chrome --kiosk "$URL" &
fi
```

### Flags Adicionales de Chrome

Añadir más flags en `launch-kiosk.sh`:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --kiosk \
    --no-first-run \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-features=Translate \
    --disable-infobars \              # Sin barra de info
    --disable-extensions \            # Sin extensiones
    --disable-modules \               # Sin modules
    --disable-dev-tools \             # Sin DevTools
    --disable-translate \             # Sin traducción
    --disable-sync \                  # Sin sincronización
    --incognito \                     # Modo incógnito
    "$URL" &
```

---

## 📚 Referencias

- [Chrome Kiosk Mode](https://support.google.com/chrome/a/answer/3273084)
- [Firefox Kiosk Mode](https://support.mozilla.org/en-US/kb/firefox-kiosk-mode)
- [Windows Assigned Access](https://docs.microsoft.com/en-us/windows/configuration/kiosk-methods)
- [PyWebView Documentation](https://pywebview.flowrl.com/)

---

## ✅ Testing Checklist

Antes de desplegar en producción, probar:

- [ ] Script `launch-kiosk.sh` en modo auto
- [ ] Script `launch-kiosk.sh --web`
- [ ] Script `launch-kiosk.sh --desktop`
- [ ] Script `launch-dev-kiosk.sh` (desarrollo)
- [ ] Desktop app con `--kiosk` flag
- [ ] Navegador abre en pantalla completa
- [ ] No se puede acceder a menús del navegador
- [ ] Impresión funciona correctamente
- [ ] Salida del kiosk con teclas apropiadas
- [ ] Auto-inicio en sistema (si aplica)
- [ ] Reinicio automático tras crash (si aplica)

---

## 🤝 Contribuir

¿Mejoras o sugerencias? Abre un issue o PR en el repositorio.

---

**Creado por:** ERPlora Team
**Licencia:** BUSL-1.1
**Última actualización:** 2025-01-24

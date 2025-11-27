# Kiosk Mode - Technical Documentation

Sistema completo de modo kiosko para ERPlora Hub con soporte multi-plataforma.

---

## 🎯 Objetivo

Permitir que ERPlora Hub funcione como terminal dedicada (kiosko) en:
1. **Desktop apps** (PyInstaller con PyWebView)
2. **Web browsers** (Chrome, Edge, Firefox)
3. **PWA** (Progressive Web Apps)

---

## 📐 Arquitectura

### Componentes del Sistema

```
ERPlora Hub Kiosk System
│
├─ Desktop App (PyInstaller + PyWebView)
│  ├─ main.py --kiosk flag
│  ├─ Fullscreen mode
│  ├─ No browser chrome
│  └─ Native window management
│
├─ Web Browser Kiosk
│  ├─ Chrome/Edge: --kiosk flag
│  ├─ Firefox: --kiosk flag
│  ├─ Safari: Fullscreen API (manual)
│  └─ PWA: fullscreen manifest option
│
└─ Launch Scripts
   ├─ launch-kiosk.{sh,bat}           # Producción
   ├─ launch-dev-kiosk.{sh,bat}       # Desarrollo
   └─ Auto-detect mode (web vs desktop)
```

---

## 🖥️ Desktop App Kiosk Mode

### Implementación en `main.py`

**Cambios realizados:**

1. **Añadir argparse para flags de línea de comandos:**
```python
import argparse

parser = argparse.ArgumentParser(description='ERPlora Hub - Desktop Application')
parser.add_argument('--kiosk', action='store_true',
                    help='Start in kiosk mode (fullscreen, no browser UI)')
parser.add_argument('--width', type=int, default=1200,
                    help='Window width (default: 1200)')
parser.add_argument('--height', type=int, default=800,
                    help='Window height (default: 800)')
args = parser.parse_args()
```

2. **Aplicar configuración de kiosko en PyWebView:**
```python
window = webview.create_window(
    'ERPlora Hub',
    'http://localhost:8001',
    width=args.width,
    height=args.height,
    resizable=not args.kiosk,  # No resizable en kiosk
    fullscreen=args.kiosk,     # Fullscreen en kiosk
    js_api=api
)
```

### Uso

```bash
# Modo normal
./ERPloraHub

# Modo kiosko
./ERPloraHub --kiosk

# Kiosko con resolución personalizada
./ERPloraHub --kiosk --width 1920 --height 1080
```

### Comportamiento en Kiosk Mode (Desktop)

| Característica | Normal | Kiosk |
|----------------|--------|-------|
| Fullscreen | No | Sí |
| Resizable | Sí | No |
| Window chrome | Sí | No |
| Title bar | Sí | No |
| Minimize/Maximize | Sí | No |

---

## 🌐 Web Browser Kiosk Mode

### Chrome / Chromium / Edge

**Flags usados:**
```bash
--kiosk                              # Modo kiosko (fullscreen sin UI)
--no-first-run                       # Sin wizard de primera ejecución
--disable-pinch                      # Deshabilita zoom con gestos
--overscroll-history-navigation=0    # Sin navegación con gestos
--disable-features=Translate         # Sin popup de traducción
```

**Ejemplo completo:**
```bash
google-chrome \
    --kiosk \
    --no-first-run \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-features=Translate \
    http://localhost:8001
```

### Firefox

**Flag usado:**
```bash
firefox --kiosk http://localhost:8001
```

Firefox tiene soporte nativo para kiosk mode desde la versión 71.

### Safari (macOS)

Safari **NO soporta** modo kiosko vía línea de comandos. Alternativas:

1. **Usar fullscreen API manualmente:**
   - Abrir URL con `open -a Safari`
   - Presionar `Cmd+Ctrl+F` para fullscreen

2. **Safari Web App Mode:**
   ```bash
   open -a Safari --args --webapp http://localhost:8001
   ```

### Salir del Modo Kiosko

| Navegador | macOS | Windows/Linux |
|-----------|-------|---------------|
| Chrome/Edge | `Cmd+Q` | `Alt+F4` o `F11` |
| Firefox | `Cmd+Q` | `Alt+F4` o `F11` |
| Safari | `Esc` o `Cmd+Ctrl+F` | N/A |

---

## 🚀 Launch Scripts

### Script de Producción: `launch-kiosk.{sh,bat}`

**Funcionalidad:**
1. Auto-detecta el sistema operativo
2. Auto-detecta si desktop app está instalada
3. Si hay desktop app → usa desktop kiosk
4. Si no hay desktop app → usa browser kiosk
5. Detecta navegador disponible automáticamente
6. Lanza en modo kiosko

**Opciones:**
```bash
./launch-kiosk.sh                    # Auto-detect mode
./launch-kiosk.sh --web              # Force web browser kiosk
./launch-kiosk.sh --desktop          # Force desktop app kiosk
./launch-kiosk.sh --port 8001        # Custom port
./launch-kiosk.sh --url <URL>        # Custom URL
```

### Script de Desarrollo: `launch-dev-kiosk.{sh,bat}`

**Funcionalidad:**
1. Activa virtual environment
2. Mata procesos existentes en el puerto
3. Inicia Django development server en background
4. Espera a que Django esté listo (health check)
5. Lanza navegador en modo kiosko
6. Cleanup automático al presionar Ctrl+C

**Opciones:**
```bash
./launch-dev-kiosk.sh                # Default port 8001
./launch-dev-kiosk.sh --port 8002    # Custom port
./launch-dev-kiosk.sh --venv .venv   # Custom venv path
```

**Logs:**
- macOS/Linux: `/tmp/erplora-dev-kiosk.log`
- Windows: `%TEMP%\erplora-dev-kiosk.log`

---

## 🔧 Integración con Sistemas

### macOS - LaunchAgent

Archivo: `~/Library/LaunchAgents/com.erplora.hub.kiosk.plist`

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
    <key>StandardOutPath</key>
    <string>/tmp/erplora-hub-kiosk.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/erplora-hub-kiosk.error.log</string>
</dict>
</plist>
```

**Comandos:**
```bash
# Instalar
launchctl load ~/Library/LaunchAgents/com.erplora.hub.kiosk.plist

# Iniciar
launchctl start com.erplora.hub.kiosk

# Detener
launchctl stop com.erplora.hub.kiosk

# Desinstalar
launchctl unload ~/Library/LaunchAgents/com.erplora.hub.kiosk.plist
```

### Linux - systemd Service

Archivo: `/etc/systemd/system/erplora-hub-kiosk.service`

```ini
[Unit]
Description=ERPlora Hub Kiosk Mode
After=network.target graphical.target

[Service]
Type=simple
User=pos
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/pos/.Xauthority"
ExecStart=/opt/erplora-hub/ERPloraHub --kiosk
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
```

**Comandos:**
```bash
# Instalar
sudo systemctl enable erplora-hub-kiosk

# Iniciar
sudo systemctl start erplora-hub-kiosk

# Estado
sudo systemctl status erplora-hub-kiosk

# Logs
sudo journalctl -u erplora-hub-kiosk -f

# Detener
sudo systemctl stop erplora-hub-kiosk

# Desinstalar
sudo systemctl disable erplora-hub-kiosk
```

### Windows - Task Scheduler

**Crear tarea programada:**

1. Abrir Task Scheduler
2. Create Task → General Tab:
   - Name: "ERPlora Hub Kiosk"
   - Run with highest privileges: ✓
   - Configure for: Windows 10/11

3. Triggers Tab:
   - New → Begin the task: At log on
   - Specific user: [POS User]

4. Actions Tab:
   - New → Action: Start a program
   - Program: `C:\Program Files\ERPlora Hub\ERPloraHub.exe`
   - Arguments: `--kiosk`

5. Conditions Tab:
   - Start only if computer is on AC power: ✗

6. Settings Tab:
   - If task fails, restart: ✓
   - Restart every: 5 minutes
   - Attempt to restart up to: 3 times

**PowerShell (alternativa):**
```powershell
$action = New-ScheduledTaskAction -Execute "C:\Program Files\ERPlora Hub\ERPloraHub.exe" -Argument "--kiosk"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ERPlora Hub Kiosk" -Action $action -Trigger $trigger
```

---

## 🔒 Seguridad y Restricciones

### Deshabilitar Salida del Kiosk

#### Windows - Assigned Access (Shell Launcher)

Windows 10/11 Pro/Enterprise tienen "Assigned Access" para crear kiosks verdaderos:

```powershell
# PowerShell como administrador

# Crear usuario kiosk
New-LocalUser -Name "KioskUser" -NoPassword

# Asignar app como shell
$ShellLauncherClass = [wmiclass]"\\localhost\root\standardcimv2\embedded:WESL_UserSetting"
$ShellLauncherClass.SetCustomShell("KioskUser", "C:\Program Files\ERPlora Hub\ERPloraHub.exe --kiosk")
```

#### Linux - Kiosk Mode con X11

**Método 1: .xinitrc**

Archivo: `~/.xinitrc`
```bash
#!/bin/bash
xset -dpms      # Disable DPMS (Energy Star)
xset s off      # Disable screen saver
xset s noblank  # Don't blank the video device

# Disable exit hotkeys
setxkbmap -option terminate:

# Launch kiosk
/opt/erplora-hub/ERPloraHub --kiosk
```

**Método 2: Openbox Kiosk**

Archivo: `~/.config/openbox/autostart`
```bash
# Disable screensaver
xset -dpms &
xset s off &
xset s noblank &

# Hide cursor after 2 seconds
unclutter -idle 2 &

# Launch kiosk
/opt/erplora-hub/ERPloraHub --kiosk &
```

#### macOS - Guided Access (iPad/Kiosk)

Para iPads usados como kiosks:
1. Settings → Accessibility → Guided Access
2. Enable Guided Access
3. Set passcode
4. Launch ERPlora Hub
5. Triple-click Home button → Start Guided Access

---

## 📊 Comparativa de Soluciones

### Desktop vs Web Kiosk

| Característica | Desktop (PyWebView) | Web (Browser) |
|----------------|---------------------|---------------|
| **Instalación** | Requiere build | Solo navegador |
| **Rendimiento** | Excelente | Bueno |
| **Impresión directa** | ✅ Sí | ❌ No (window.print) |
| **Hardware USB** | ✅ Sí | ❌ No (excepto teclados) |
| **Barcode scanners** | ✅ Sí | ✅ Sí (como teclado) |
| **Offline** | ✅ Sí | ❌ No |
| **Actualizaciones** | Requiere rebuild | Automáticas |
| **Tamaño binario** | ~100-150 MB | N/A |
| **Startup time** | 3-5s | Instantáneo |
| **Memoria RAM** | ~150-200 MB | ~200-300 MB |
| **CPU idle** | Bajo | Bajo |

### Navegadores para Web Kiosk

| Navegador | Kiosk Nativo | Flags | Salida | Recomendado |
|-----------|--------------|-------|--------|-------------|
| Chrome | ✅ Sí | `--kiosk` | Alt+F4, F11 | ⭐ Sí |
| Edge | ✅ Sí | `--kiosk` | Alt+F4, F11 | ⭐ Sí |
| Firefox | ✅ Sí | `--kiosk` | Alt+F4, F11 | ⭐ Sí |
| Safari | ❌ No | N/A | Cmd+Ctrl+F | ⚠️ Limitado |
| Chromium | ✅ Sí | `--kiosk` | Alt+F4, F11 | ⭐ Sí |

---

## 🧪 Testing

### Test Checklist

Antes de desplegar en producción:

#### Desktop Kiosk
- [ ] App arranca con `--kiosk` flag
- [ ] Ventana en fullscreen
- [ ] No hay title bar
- [ ] No se puede redimensionar
- [ ] Impresión directa funciona
- [ ] Hardware USB detectado
- [ ] Barcode scanner funciona
- [ ] App se reinicia tras crash (systemd/launchd)

#### Web Kiosk
- [ ] Chrome kiosk mode funciona
- [ ] Edge kiosk mode funciona
- [ ] Firefox kiosk mode funciona
- [ ] No se pueden ver menús del navegador
- [ ] window.print() funciona
- [ ] Barcode scanner como teclado funciona
- [ ] Salida con teclas apropiadas funciona

#### Scripts
- [ ] `launch-kiosk.sh --web` funciona
- [ ] `launch-kiosk.sh --desktop` funciona
- [ ] `launch-kiosk.sh` auto-detecta correctamente
- [ ] `launch-dev-kiosk.sh` inicia Django + browser
- [ ] Ctrl+C hace cleanup correcto
- [ ] Logs se escriben correctamente

#### Integración Sistema
- [ ] LaunchAgent/systemd service funciona
- [ ] Auto-inicio al login
- [ ] Auto-restart tras crash
- [ ] Logs accesibles
- [ ] Puede detenerse manualmente

### Comandos de Testing

```bash
# Test desktop kiosk
./ERPloraHub --kiosk
# → Debe abrir en fullscreen, sin title bar

# Test web kiosk (auto-detect)
cd kiosk
./launch-kiosk.sh
# → Debe detectar navegador y abrir en kiosk

# Test web kiosk (forzado)
./launch-kiosk.sh --web
# → Debe usar navegador incluso si hay desktop app

# Test dev kiosk
./launch-dev-kiosk.sh
# → Debe iniciar Django + browser kiosk
# → Ctrl+C debe hacer cleanup

# Test con URL remota
./launch-kiosk.sh --web --url https://int.erplora.com
# → Debe abrir URL remota en kiosk
```

---

## 🐛 Troubleshooting

### Problema: Desktop app no inicia en kiosk mode

**Síntomas:**
- App abre en modo normal aunque se use `--kiosk`
- Ventana tiene title bar

**Causas posibles:**
1. PyWebView no soporta fullscreen en tu OS
2. Window manager no permite fullscreen

**Solución:**
```python
# Verificar logs en main.py
print(f"[INFO] Starting in KIOSK MODE (fullscreen)")

# Verificar que args se parsean correctamente
print(f"[DEBUG] args.kiosk = {args.kiosk}")
```

### Problema: Browser no abre en kiosk mode

**Síntomas:**
- Browser abre en ventana normal
- Se ven menús y barras de navegación

**Causas posibles:**
1. Navegador no instalado en ruta esperada
2. Flags de kiosk no soportados en esa versión

**Solución:**
```bash
# Verificar que navegador existe
which google-chrome
which chromium-browser
which firefox

# Test manual de flags
google-chrome --kiosk http://localhost:8001

# Ver logs del script
./launch-kiosk.sh --web 2>&1 | tee kiosk-debug.log
```

### Problema: Django no inicia con launch-dev-kiosk

**Síntomas:**
- Script se queda esperando
- "Django failed to start within 15 seconds"

**Causas posibles:**
1. Puerto ya en uso
2. Virtual environment no activado
3. Django con errores

**Solución:**
```bash
# Verificar puerto libre
lsof -i :8001  # macOS/Linux
netstat -ano | findstr :8001  # Windows

# Matar proceso existente
lsof -ti:8001 | xargs kill -9  # macOS/Linux
taskkill /F /PID <PID>  # Windows

# Ver logs de Django
tail -f /tmp/erplora-dev-kiosk.log  # macOS/Linux
type %TEMP%\erplora-dev-kiosk.log  # Windows

# Test manual
cd ../hub
source .venv/bin/activate
python manage.py runserver 8001
```

### Problema: No puedo salir del kiosk mode

**Síntomas:**
- Teclas de salida no funcionan
- Browser/app no responde

**Solución:**

**macOS:**
```bash
# Task Manager
Cmd+Opt+Esc
# → Force Quit ERPlora Hub o Browser

# Kill desde terminal
pkill -9 "ERPlora Hub"
pkill -9 "Google Chrome"
```

**Linux:**
```bash
# Task Manager
Ctrl+Alt+Del

# Kill desde terminal
pkill -9 ERPloraHub
pkill -9 chrome
```

**Windows:**
```batch
REM Task Manager
Ctrl+Shift+Esc
REM → End Task

REM Kill desde cmd
taskkill /F /IM ERPloraHub.exe
taskkill /F /IM chrome.exe
```

### Problema: Auto-inicio no funciona

**Síntomas:**
- App no inicia al login
- systemd/launchd service no corre

**Solución:**

**macOS:**
```bash
# Verificar que plist está cargado
launchctl list | grep erplora

# Ver logs
tail -f /tmp/erplora-hub-kiosk.log

# Reload plist
launchctl unload ~/Library/LaunchAgents/com.erplora.hub.kiosk.plist
launchctl load ~/Library/LaunchAgents/com.erplora.hub.kiosk.plist
```

**Linux:**
```bash
# Verificar que service está enabled
systemctl list-unit-files | grep erplora

# Ver logs
sudo journalctl -u erplora-hub-kiosk -f

# Reload service
sudo systemctl daemon-reload
sudo systemctl restart erplora-hub-kiosk
```

**Windows:**
```powershell
# Verificar que tarea existe
Get-ScheduledTask | Where-Object {$_.TaskName -like "*ERPlora*"}

# Ver última ejecución
Get-ScheduledTask "ERPlora Hub Kiosk" | Get-ScheduledTaskInfo

# Ejecutar manualmente
Start-ScheduledTask -TaskName "ERPlora Hub Kiosk"
```

---

## 📚 Referencias

### Documentación Oficial

- [Chrome Kiosk Mode](https://support.google.com/chrome/a/answer/3273084)
- [Firefox Kiosk Mode](https://support.mozilla.org/en-US/kb/firefox-kiosk-mode)
- [PyWebView Documentation](https://pywebview.flowrl.com/)
- [Windows Assigned Access](https://docs.microsoft.com/en-us/windows/configuration/kiosk-methods)
- [systemd Service Units](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [macOS LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

### Artículos Relacionados

- [Building Kiosk Applications](https://webkit.org/blog/8918/webkit-introduces-window-controls-overlay/)
- [PWA Fullscreen API](https://developer.mozilla.org/en-US/docs/Web/API/Fullscreen_API)
- [Electron Kiosk Mode](https://www.electronjs.org/docs/latest/api/browser-window#new-browserwindowoptions) (similar a PyWebView)

---

## ✅ Conclusión

El sistema de kiosk mode de ERPlora Hub ofrece:

1. **Flexibilidad**: Funciona en desktop (PyWebView) y web (navegadores)
2. **Multi-plataforma**: Windows, macOS, Linux
3. **Fácil deployment**: Scripts listos para usar
4. **Producción-ready**: Integración con systemd, launchd, Task Scheduler
5. **Testing-friendly**: Scripts de desarrollo incluidos

**Recomendaciones por caso de uso:**

| Caso de Uso | Solución Recomendada |
|-------------|----------------------|
| POS físico con hardware USB | Desktop kiosk (PyWebView) |
| Tablet como terminal | Web kiosk (Chrome/Edge) |
| Desarrollo y testing | launch-dev-kiosk.sh |
| Cloud POS sin hardware | Web kiosk (Chrome/Edge) |
| Restaurante (cocina/barra) | Desktop kiosk + impresoras |

---

**Creado por:** ERPlora Team
**Licencia:** BUSL-1.1
**Última actualización:** 2025-01-24

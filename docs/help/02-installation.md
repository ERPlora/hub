# Instalación

ERPlora Hub se puede usar de varias formas según tu necesidad.

## Opción 1: Navegador Web (Recomendado)

La forma más sencilla. Solo necesitas un navegador moderno:

1. Abre **Chrome**, **Firefox**, **Safari** o **Edge**
2. Navega a la URL de tu Hub
3. Inicia sesión con tu PIN

### Instalar como App (PWA)

Puedes instalar el Hub como una aplicación en tu dispositivo sin necesidad de tiendas de aplicaciones:

**En Chrome (escritorio):**
1. Accede a tu Hub en Chrome
2. Haz clic en el icono de **instalar** (⊕) en la barra de direcciones
3. O ve al menú lateral y pulsa **"Instalar App"**
4. La app aparecerá en tu escritorio y se abrirá en su propia ventana

**En Chrome (Android):**
1. Accede a tu Hub en Chrome
2. Toca **"Añadir a pantalla de inicio"** en el banner o menú (⋮)
3. La app aparecerá como un icono en tu launcher

**En Safari (iOS/iPadOS):**
1. Accede a tu Hub en Safari
2. Toca el botón de **compartir** (↑)
3. Selecciona **"Añadir a pantalla de inicio"**
4. La app aparecerá como un icono en tu pantalla

## Opción 2: Modo Kiosco

Ideal para terminales de punto de venta dedicados. El navegador ocupa toda la pantalla sin barras ni controles.

### Chrome Kiosco (Windows)

Crea un acceso directo con estos parámetros:

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --disable-pinch --overscroll-history-navigation=disabled https://tu-hub.a.erplora.com
```

**Flags importantes:**
- `--kiosk` — Pantalla completa sin barras
- `--disable-pinch` — Desactiva zoom con pellizco
- `--overscroll-history-navigation=disabled` — Evita navegación accidental con gestos

Para salir del modo kiosco: `Alt + F4` (Windows) o `Cmd + Q` (macOS).

### Chrome Kiosco (macOS)

Abre Terminal y ejecuta:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --kiosk --disable-pinch https://tu-hub.a.erplora.com
```

### Chrome Kiosco (Linux)

```bash
google-chrome --kiosk --disable-pinch --overscroll-history-navigation=disabled https://tu-hub.a.erplora.com
```

### Kiosco con Arranque Automático

Para que el terminal arranque directamente en modo kiosco:

**Windows:**
1. Crea el acceso directo con los flags anteriores
2. Colócalo en `shell:startup` (Win + R → `shell:startup`)
3. El PC arrancará directamente en el Hub

**Linux (autostart):**
1. Crea el archivo `~/.config/autostart/erplora-kiosk.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=ERPlora Kiosk
Exec=google-chrome --kiosk --disable-pinch https://tu-hub.a.erplora.com
X-GNOME-Autostart-enabled=true
```

## Opción 3: Aplicación de Escritorio

Próximamente disponible como aplicación nativa para macOS, Windows y Linux.

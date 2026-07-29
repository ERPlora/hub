# ERPlora → Google Play (canal Android único de cliente)

**Decisión (ADR-0160, 2026-07-29):** una sola app instalable por plataforma bajo la
identidad única **`com.erplora.app`**. En Android esa app es la **Kotlin** (shell webview
ADR-0159 + bridge Ktor) y vive **SOLO** en el repo
[`ERPlora-Bridge-android`](https://github.com/ERPlora/ERPlora-Bridge-android) — el
Tauri-Android de este repo se **retiró** (los jobs `check-secrets`/`build-android`/
`publish-play` de [`tauri-release.yml`](../../.github/workflows/tauri-release.yml) se
eliminaron; la Variable `PLAY_PACKAGE_NAME_APP` murió con ellos).

Sigue vigente la decisión de canal (2026-07-16): Android de cara al cliente se distribuye
**SOLO por Google Play** (UE; confianza; todos los terminales objetivo tienen Play). La
landing no ofrece APK: el endpoint de descarga del SaaS hace **redirect 302** a Play
(saas#707).

**Fichas previas:** los 2 drafts anteriores en Play Console (`com.erplora.hub` y
`com.erplora.bridge`, ambos con **0 releases**) los borra **Ioan** en la consola. No hay
usuarios ni migración.

## Requisitos verificados (julio 2026)

- **Cuenta de ORGANIZACIÓN verificada** — ✅ hecha (hub#125 cerrado 2026-07-29). Las cuentas
  org están **EXENTAS** del requisito de closed testing (12 testers/14 días, solo cuentas
  personales) → **producción directa**.
- **AAB obligatorio + Play App Signing**: Google custodia la app signing key; nuestra
  keystore (alias `erplora`, ADR-0053 — antes compartida app↔bridge, ahora upload key de la
  **única** app) actúa de **upload key** (registro por-app; reseteable vía soporte).
  Verificar expiración (`keytool -list -v`, > 22-oct-2033) + copia fuera de GitHub.
- **Target API 36** desde el 31-ago-2026 (apps nuevas y updates) — responsabilidad del CI
  del repo Kotlin.
- **La PRIMERA subida del AAB es MANUAL** en Play Console (requisito de Google) y es la que
  **registra la upload key**; después, el CI del repo Kotlin publica cada release
  automáticamente.
- **versionCode monotónico**: `major*1e6 + minor*1e3 + patch` → **1.0.0 = 1000000** (la
  serie arranca en 1.0.0, ADR-0160); el build Kotlin lo recibe por `-PversionCode`.
- **FGS** (`connectedDevice`, el bridge Ktor embebido): exige declaración en Play Console
  con **vídeo demo**.

## Cableado

| Pieza | Dónde | Gate |
| --- | --- | --- |
| Build AAB + publicación | `ERPlora-Bridge-android/.github/workflows/build.yml` job `publish-play` | Variable `PLAY_PACKAGE_NAME=com.erplora.app` |
| Track | ídem | Variable `PLAY_TRACK` (default `internal`) |
| Redirect 302 a Play | SaaS `apps/public/downloads.py::store_url_for` | settings `GOOGLE_PLAY_APP_ID=com.erplora.app` (Dokploy, saas-web); `GOOGLE_PLAY_BRIDGE_ID` queda obsoleto (limpieza SaaS-side) |

En este repo (`hub`) **no queda cableado Android**.

## Pasos manuales (Ioan) — en orden

1. **Play Console**: borrar los 2 drafts previos (`com.erplora.hub`, `com.erplora.bridge`,
   0 releases) y crear la ficha única **`com.erplora.app`**.
2. Subir **a mano** el primer AAB (artifact del CI del repo Kotlin) al track `internal` —
   esto registra la upload key (keystore ADR-0053) y activa Play App Signing. Formularios:
   Data safety · content rating IARC · privacy policy URL · **declaración FGS + vídeo** ·
   screenshots (mín. 2) + feature graphic 1024×500 + icono 512×512.
3. Service account (Google Play Android Developer API) con permisos por-app → secret
   `PLAY_SERVICE_ACCOUNT_JSON` + Variable `PLAY_PACKAGE_NAME=com.erplora.app` en el repo
   `ERPlora-Bridge-android`.
4. Promoción `internal` → `production` manual en consola (cuenta org = sin closed testing
   obligatorio); cuando haya confianza, `PLAY_TRACK=production`.
5. Con la ficha LIVE: setting `GOOGLE_PLAY_APP_ID=com.erplora.app` en Dokploy (saas-web) →
   la landing y el Hub redirigen solos a Play.

## Verificación

- Release del repo Kotlin → AAB firmado; `jarsigner -verify`; `bundletool build-apks
  --mode=universal` + instalar en dispositivo real (shell webview carga el Hub; el bridge
  Ktor imprime test TCP:9100).
- Release con Variables puestas → publicación en el track `internal` sin intervención.
- Producción: instalar desde Play en dispositivo limpio; la siguiente release llega como
  update OTA de Play.

## Riesgos conocidos

- La primera revisión (FGS + Bluetooth) suele llevar revisión humana de Google — el vídeo
  demo es la clave.
- Sin `ACCESS_FINE_LOCATION`, el discovery BT clásico en API 26–30 no devuelve resultados
  (solo bonded devices) — decisión minSdk pendiente: bridge-android#4.

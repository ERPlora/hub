# ERPlora → Google Play (canal Android único de cliente)

**Decisión (2026-07-16, plan tiendas Fase 1):** Android de cara al cliente se distribuye
**SOLO por Google Play** (UE; confianza; todos los terminales objetivo tienen Play). El APK
firmado sigue subiéndose a S3 como **artefacto interno de QA** — la landing ya no lo ofrece:
el endpoint de descarga hace **redirect 302** a Play cuando `GOOGLE_PLAY_*_ID` está
configurado en el SaaS (saas#707).

Aplica a las DOS apps: **ERPlora** (`com.erplora.hub`, este repo, job `build-android` de
[`tauri-release.yml`](../../.github/workflows/tauri-release.yml)) y **ERPlora Bridge**
(`com.erplora.bridge`, repo [`ERPlora-Bridge-android`](https://github.com/ERPlora/ERPlora-Bridge-android)).

## Requisitos verificados (julio 2026)

- **Cuenta de ORGANIZACIÓN** ($25 one-time): exige **D-U-N-S** — ✅ **ya disponible**
  (2026-07-16: `COMPANY_DUNS` en el `.env` raíz del workspace, bloque «Datos de empresa»);
  hub#125 queda en crear la cuenta + verificaciones. Las cuentas org están **EXENTAS** del
  requisito de closed testing (12 testers/14 días, solo cuentas personales) → producción directa.
- **AAB obligatorio + Play App Signing**: Google custodia la app signing key; nuestra keystore
  (alias `erplora`, compartida app↔bridge — ADR-0053) actúa de **upload key** de ambas apps
  (permitido; registro por-app; reseteable vía soporte). Verificar expiración
  (`keytool -list -v`, > 22-oct-2033) + copia fuera de GitHub.
- **Target API 36** desde el 31-ago-2026 (apps nuevas y updates). El CI ya instala
  `platforms;android-36` y parchea el gradle generado por `tauri android init` (idempotente).
- **La PRIMERA subida de cada app es MANUAL** en Play Console (requisito de Google); después,
  el job `publish-play` publica cada tag `v*` automáticamente.
- **versionCode monotónico**: `major*1e6 + minor*1e3 + patch` — Tauri lo deriva de la versión
  (que el workflow fija desde el tag); el bridge Kotlin lo recibe por `-PversionCode`.
- **FGS del bridge** (`connectedDevice`): exige declaración en Play Console con **vídeo demo**.

## Cableado (ya hecho, inerte por gates)

| Pieza | Dónde | Gate |
| --- | --- | --- |
| Build AAB + firma jarsigner (upload key) | `tauri-release.yml` job `build-android` | siempre (artefacto extra) |
| Publicación app | `tauri-release.yml` job `publish-play` | Variable `PLAY_PACKAGE_NAME_APP` |
| Publicación bridge | `ERPlora-Bridge-android/.github/workflows/build.yml` job `publish-play` | Variable `PLAY_PACKAGE_NAME` |
| Track | ambos | Variable `PLAY_TRACK` (default `internal`) |
| Redirect 302 a Play | SaaS `apps/public/downloads.py::store_url_for` | settings `GOOGLE_PLAY_APP_ID` / `GOOGLE_PLAY_BRIDGE_ID` |

## Pasos manuales (Ioan) — en orden

1. **hub#125** — crear la cuenta Play Console de organización con el D-U-N-S del `.env` raíz
   (`COMPANY_DUNS`) → verificaciones de identidad/empresa. Keystore: verificar expiración + backup.
2. **hub#128** — crear las 2 apps → subir a mano el AAB de cada una (artifact del CI de un tag)
   al track `internal` (esto registra la upload key y activa Play App Signing) → formularios:
   Data safety · content rating IARC · privacy policy URL · **declaración FGS + vídeo** (bridge)
   · screenshots (mín. 2) + feature graphic 1024×500 + icono 512×512.
3. **hub#129** — GCP: proyecto + Google Play Android Developer API + service account con key
   JSON → secret org-level `PLAY_SERVICE_ACCOUNT_JSON`; invitar la SA en Play Console con
   permisos mínimos por-app («Release to testing tracks»); Variables `PLAY_PACKAGE_NAME_APP`
   (repo hub) y `PLAY_PACKAGE_NAME` (repo bridge-android).
4. Promoción `internal` → `production` manual en consola; cuando haya confianza,
   `PLAY_TRACK=production`.
5. Con las fichas LIVE: settings `GOOGLE_PLAY_APP_ID=com.erplora.hub` y
   `GOOGLE_PLAY_BRIDGE_ID=com.erplora.bridge` en Dokploy (saas-web) → la landing y el Hub
   redirigen solos a Play.

## Verificación

- Tag de prueba → artifacts `erplora-app.aab` + `erplora-bridge.aab`; `jarsigner -verify`;
  `bundletool build-apks --mode=universal` + instalar en dispositivo real (app hasta el
  EntitlementGate; bridge imprime test TCP:9100).
- Tag real con Variables puestas → release en el track `internal` sin intervención y sin
  builds duplicados (solo `build-android` compila; `publish-play` consume el artifact).
- Producción: instalar ambas desde Play en dispositivo limpio; el siguiente tag llega como
  update OTA de Play.

## Riesgos conocidos

- El targetSdk que emite `tauri android init` puede ir por detrás — el patch `sed` del workflow
  lo cubre; re-verificar tras el 31-ago-2026.
- El dir del bundle varía (`universalRelease` vs `aarch64Release`) — el staging usa glob.
- La primera revisión del bridge (FGS + Bluetooth) suele llevar revisión humana de Google —
  el vídeo demo es la clave.
- Sin `ACCESS_FINE_LOCATION`, el discovery BT clásico en API 26–30 no devuelve resultados
  (solo bonded devices) — decisión minSdk pendiente: bridge-android#4.

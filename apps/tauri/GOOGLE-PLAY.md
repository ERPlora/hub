# ERPlora → Google Play (canal Android único de cliente)

**Decisión vigente (ADR-0180, 2026-08-01, confirmada por ADR-0196, 2026-08-03):** Android es
la **MISMA app Tauri** de este repo, bajo la identidad única **`com.erplora.app`**
(ADR-0160). ADR-0180 revierte el §3 de ADR-0160 —que había sacado el Tauri-Android de
[`tauri-release.yml`](../../.github/workflows/tauri-release.yml)— y devuelve el build aquí:
job **`build-android`**. ADR-0196 remata la dirección: **la app Kotlin de
`ERPlora-Bridge-android` muere**, y con ella el bridge como proceso aparte.

> ⚠️ **Hueco de cableado abierto:** este workflow **construye** el AAB (`erplora-app.aab`) y
> lo sube a Object Storage, pero **no lo publica** en Play — aquí no hay job `publish-play`.
> El único `publish-play` que existe vive en `ERPlora-Bridge-android/.github/workflows/build.yml`
> y publica el AAB **Kotlin**, que es justo el que ADR-0196 retira. Nadie publica
> `erplora-app.aab`. Seguimiento: hub#308.

Sigue vigente la decisión de canal (2026-07-16): Android de cara al cliente se distribuye
**SOLO por Google Play** (UE; confianza; todos los terminales objetivo tienen Play). La
landing no ofrece APK: el endpoint de descarga del SaaS hace **redirect 302** a Play
(saas#707).

## Requisitos

- **Cuenta de ORGANIZACIÓN verificada.** Las cuentas org están **EXENTAS** del requisito de
  closed testing (12 testers/14 días, solo cuentas personales) → **producción directa**.
- **AAB obligatorio + Play App Signing**: Google custodia la app signing key; nuestra
  keystore (alias `erplora`, ADR-0053) actúa de **upload key** (registro por-app; reseteable
  vía soporte). Verificar expiración (`keytool -list -v`, > 22-oct-2033) + copia fuera de
  GitHub.
- **Target API 36** desde el 31-ago-2026 (apps nuevas y updates).
- **La PRIMERA subida del AAB es MANUAL** en Play Console (requisito de Google) y es la que
  **registra la upload key**.
- **versionCode monotónico**: `major*1e6 + minor*1e3 + patch` → **1.0.0 = 1000000** (la serie
  arranca en 1.0.0, ADR-0160). Lo fija el Gradle, no el que calcula Tauri (ADR-0180 §4): en
  Play es una puerta de un solo sentido.
- **Sin declaración de FGS.** ADR-0196 §2 retira el *foreground service*: la app no corre en
  segundo plano. El `AndroidManifest.xml` de `gen/android` es la fuente — consúltalo en vez de
  fiarte de una lista aquí.

## Cableado

| Pieza | Dónde |
| --- | --- |
| Build del AAB | este repo, [`tauri-release.yml`](../../.github/workflows/tauri-release.yml) job `build-android` |
| Subida a Object Storage | ídem, job `upload-s3` |
| Publicación en Play | **no cableada** (ver aviso de arriba) |
| Redirect 302 a Play | SaaS `apps/public/downloads.py::store_url_for` + setting `GOOGLE_PLAY_APP_ID` |

## Pasos manuales (Ioan) — en orden

1. **Play Console**: crear la ficha única **`com.erplora.app`**.
2. Subir **a mano** el primer AAB (artifact de `build-android`) al track `internal` — esto
   registra la upload key (keystore ADR-0053) y activa Play App Signing. Formularios: Data
   safety · content rating IARC · privacy policy URL · screenshots (mín. 2) + feature graphic
   1024×500 + icono 512×512.
3. Cablear la publicación automática en **este** repo (hub#308): poner la Variable
   `PLAY_PACKAGE_NAME` (+ el secret `PLAY_SERVICE_ACCOUNT_JSON`) y **quitar `play` de
   `RELEASE_CHANNELS_PENDING`** (hub#895). Mientras `play` siga en esa lista, el job
   `release-gate` deja pasar el tag en verde avisando de que Play no publicó; en cuanto se
   quita, un tag que no llegue a Play sale **rojo**.
4. Promoción `internal` → `production` manual en consola (cuenta org = sin closed testing
   obligatorio).
5. Con la ficha LIVE: setting `GOOGLE_PLAY_APP_ID=com.erplora.app` en Dokploy (saas-web) → la
   landing y el Hub redirigen solos a Play.

## Verificación

- `bundletool build-apks --mode=universal` + instalar en dispositivo real: la webview carga el
  Hub y la impresora de **red** imprime (TCP:9100). Sin Bluetooth: ADR-0180 retiró el SPP.
- ADR-0180 deja la validación en **dispositivo real sobre una LAN con impresora** como puerta
  —el emulador no puede darla, su red es NAT— junto con la actualización OTA por encima del
  APK instalado.
- Producción: instalar desde Play en dispositivo limpio; la siguiente release llega como
  update OTA de Play.

## Riesgos conocidos

- Los permisos de runtime son **parte del producto**, no empaquetado (ADR-0180 §2): sin
  `ACCESS_LOCAL_NETWORK` el descubrimiento devuelve `[]` —indistinguible de «no hay
  impresoras»— y sin `POST_NOTIFICATIONS` la comanda entra en cocina sin avisar. Ninguno de
  los dos da error. Se piden **en contexto**.

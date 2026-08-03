# ERPlora Desktop → Microsoft Store (canal Windows principal)

**Decisión (ADR-0136, 2026-07-16):** el canal de distribución Windows es **Microsoft Store
con MSIX sin firmar** — la Store re-firma con su certificado tras la certificación, así que
**no se compra certificado Authenticode** (0€ vs OV ~300–500€/año + token). El argumento
decisivo: la lógica de negocio vive en los **módulos**, que se actualizan al instante por el
marketplace del SaaS sin pasar por certificación de Microsoft; por la Store solo pasan las
releases del shell Tauri (poco frecuentes). El NSIS/MSI de S3 (`downloads/app/`) queda como
canal secundario sin firmar; si un cliente real no puede usar la Store → Azure Artifact
Signing (~10€/mes, orgs UE), **aplazado** (lean).

Verificado 2026-07: cuenta de desarrollador **gratuita** (particulares y empresas), la Store
firma los MSIX, Web Installer modo Direct para «descargar desde erplora.com», y la
automatización con GitHub Actions está soportada **solo para productos gratuitos** — que es
exactamente nuestro modelo (app gratis + suscripción/módulos en erplora.com, Stripe propio,
0% comisión de Microsoft en apps no-juego con pasarela propia).

**Una sola ficha por tienda (ADR-0160, 2026-07-29):** «ERPlora» (`com.erplora.app`). El
bridge headless NO tiene ficha de Store — ver la última sección.

## Cómo se empaqueta (ya cableado)

- [`src-tauri/msix/Package.appxmanifest`](src-tauri/msix/Package.appxmanifest) — manifest con
  tokens `__MSIX_*__` que se sustituyen en build-time con la identidad de Partner Center.
- [`../../scripts/pack-msix.ps1`](../../scripts/pack-msix.ps1) — post-build **puro** (no toca
  Tauri): stagea el exe de `target/release`, `apps/web/dist` (mismo layout que instala NSIS)
  y los iconos de Store; parchea el manifest y corre `winapp pack` (CLI oficial de Microsoft,
  `winget install microsoft.winappcli`). Sin `-Cert` = sin firmar (lo que exige la submission).
- [`../../.github/workflows/tauri-release.yml`](../../.github/workflows/tauri-release.yml) —
  en el leg Windows del build (tag `v*`): pack MSIX → artifact `app-msix` → job
  `publish-store` (`msstore publish`). Todo **gated por Variables del repo**: hasta que
  existan, los pasos se saltan en silencio y el workflow actual no cambia.

En la ruta MSIX **no aplica** `webviewInstallMode` (el instalador NSIS no se ejecuta);
Win10/11 actualizados traen WebView2 Evergreen. El updater de Tauri no está configurado en la
app; si algún día se añade, **excluirlo del build de Store** (las updates las entrega la Store).

## Pasos manuales (Ioan) — en orden

### Fase 0 — cuenta y ficha (una vez)

1. Cuenta de desarrollador (empresa, **gratuita**) en <https://storedeveloper.microsoft.com/>.
2. Reservar el nombre **ERPlora** y crear la ficha (descripción, iconos, capturas) como
   producto **gratuito** (requisito del Web Installer y de la automatización).
3. Apuntar de Partner Center → *Product identity*:
   - `Package/Identity/Name` (p.ej. `12345Erplora.ERPlora`)
   - `Package/Identity/Publisher` (`CN=…`)
   - `PublisherDisplayName`
   - **Store ID / Product ID** (para los enlaces y `msstore publish`)

### Fase 1 — variables del repo `hub`

En GitHub → Settings → Secrets and variables → Actions → **Variables**:

| Variable | Valor (de Partner Center) |
| --- | --- |
| `MSIX_IDENTITY_NAME` | `Package/Identity/Name` |
| `MSIX_PUBLISHER` | `Package/Identity/Publisher` (`CN=…`) |
| `MSIX_PUBLISHER_DISPLAY` | `PublisherDisplayName` |
| `MICROSOFT_STORE_PRODUCT_ID` | Store ID de la ficha (activa el job `publish-store`) — **poner DESPUÉS de la Fase 2** |

### Fase 2 — primera publicación (manual, requisito de Microsoft)

La automatización exige que la app esté **ya publicada y live**. Lanza un tag `v*` (o
`workflow_dispatch`) con `MSIX_IDENTITY_NAME` ya puesto → descarga el artifact `app-msix`
→ súbelo a mano en la submission de Partner Center → certificación → publicar → esperar
a verla live en `apps.microsoft.com`.

> Antes de la primera submission conviene pasar el **WACK** (Windows App Certification Kit)
> en una máquina Windows sobre el MSIX: hay un issue abierto de Tauri v2 fallando WACK por
> S-mode ([tauri#14935](https://github.com/tauri-apps/tauri/issues/14935)).

### Fase 3 — automatización

1. Registrar una app en **Microsoft Entra ID** (tenant asociado a Partner Center) + crear
   un client secret.
2. En Partner Center → Account settings → User management → **Microsoft Entra applications**:
   añadir esa app con rol **Manager**.
3. Secrets del repo `hub`: `AZURE_AD_TENANT_ID` · `AZURE_AD_APPLICATION_CLIENT_ID` ·
   `AZURE_AD_APPLICATION_SECRET` · `SELLER_ID` (Partner Center → Account settings → Identifiers).
4. Poner la Variable `MICROSOFT_STORE_PRODUCT_ID`. Desde entonces, cada tag `v*` publica la
   actualización sola (build → MSIX → `msstore publish` → certificación → la Store la entrega).

### Fase 4 — botón en erplora.com (repo `saas`)

Con la ficha live: generar la insignia en <https://apps.microsoft.com/badge> con
**Launch mode: Direct** (Web Installer: stub de `get.microsoft.com`, instala y auto-abre —
parece descarga propia pero firma/updates son de la Store) y ponerla en la página de
descargas junto a macOS/Linux (que siguen sirviéndose de `downloads/` en Object Storage).
Enlace a ficha: `https://apps.microsoft.com/detail/<STORE_ID>`.

## Bridge headless: canal S3, SIN ficha de Store (ADR-0160, 2026-07-29)

> **ADR-0196 (2026-08-03) retira el bridge entero**, no solo su ficha de Store: mueren
> `apps/bridge` y el WS `:12321`, y con ellos este canal de descarga. **La retirada aún no se
> ha ejecutado** — comprueba si `apps/bridge/` sigue en el árbol antes de dar por buena
> ninguna de las notas de abajo.

**Decisión (Ioan, ADR-0160):** NO hay segunda ficha en ninguna tienda. Una sola ficha
**«ERPlora»** (`com.erplora.app`) por tienda: la app es el antiguo bridge con interfaz de
configuración rápida y, al abrirse, abre la PWA del Hub. La antigua «segunda ficha ERPlora
Bridge» (hub#120–#124) queda **descartada**.

El binario headless `apps/bridge` (`erplora-bridge`) **sigue existiendo**, pero SOLO como
descarga de S3 (`downloads/bridge/`, CI
[`bridge-release.yml`](../../.github/workflows/bridge-release.yml)); nunca pasa por
Partner Center.

Notas operativas que siguen vigentes (heredadas de la sección retirada):

- **hub#121** (devices.json → LocalAppData) está implementado en el binario y sigue siendo
  válido con independencia del canal (persistencia fuera del directorio de instalación).
- El cableado MSIX del bridge que quedó en el repo (manifest `apps/bridge/msix/`,
  `pack-msix.ps1 -Flavor bridge`, gates `BRIDGE_MSIX_IDENTITY_NAME` /
  `BRIDGE_MICROSOFT_STORE_PRODUCT_ID` en `bridge-release.yml`) queda **inerte por gates
  vacíos** — esas Variables NO se configuran nunca; su retirada física es follow-up aparte.
- El switch del SaaS (saas#707, `MICROSOFT_STORE_BRIDGE_ID`) queda **obsoleto**: sin
  configurar, `bridge:download/windows/` sigue sirviendo la descarga de S3 — exactamente
  el canal del headless.

## Prueba local del MSIX (opcional, en Windows)

La submission va sin firmar, pero para **instalarlo tú** localmente hace falta un devcert:

```powershell
winget install microsoft.winappcli
winapp cert generate --if-exists skip     # el Publisher debe coincidir con el manifest parcheado
winapp cert install .\devcert.pfx         # como admin, una vez
pwsh scripts/pack-msix.ps1 -Version 1.0.0 -IdentityName "…" -Publisher "CN=…" -PublisherDisplay "…" -Cert .\devcert.pfx
Add-AppxPackage dist-msix\erplora-app.msix
```

## Referencias (verificadas 2026-07)

- [Registro gratis empresas (Blog Windows Dev, 2026-05)](https://blogs.windows.com/windowsdeveloper/2026/05/07/publish-to-microsoft-store-as-a-company-now-with-free-registration-and-faster-onboarding/)
- [Code signing options (la Store firma los MSIX)](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Store Web Installer (modo Direct)](https://learn.microsoft.com/en-us/windows/apps/distribute-through-store/how-to-use-store-web-installer-for-distribution)
- [GitHub Actions + msstore CLI (solo productos gratuitos)](https://learn.microsoft.com/en-us/windows/apps/publish/msstore-dev-cli/github-actions)
- [winapp CLI con Tauri (guía oficial)](https://learn.microsoft.com/en-us/windows/apps/dev-tools/winapp-cli/guides/tauri)

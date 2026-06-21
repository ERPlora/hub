# hub — contexto de trabajo para UI

## Qué es

`hub` es la nueva generación del Hub de ERPlora. La UI es una shell
**Vue 3 + Ionic 8 + Vite + TypeScript + Tailwind v4**, sin Capacitor. La misma shell
debe servir para cloud y para Tauri. Los módulos se cargan en runtime como Web
Components, actualmente con **Lit**.

El producto que representa ERPlora es un ERP modular para pymes y autonomos:
TPV, inventario, facturacion, agenda/reservas, empleados, marketplace,
billing, sistema y asistente AI. El Cloud Portal Django sigue existiendo para
marketplace, billing, provisioning y proxy AI. `hub` es el runtime/UI del
tenant que sustituira progresivamente al hub actual.

## Fuentes de verdad

- `README.md`: estado real del repo y comandos.
- `ARQUITECTURA.md`: decisiones de arquitectura. Si hay conflicto, gana este
  documento frente a docs antiguas.
- `apps/web/README.md`: validacion de la shell web, CSP y Web Components.
- Reglas de UI vigentes: **Ionic primero** (ver "Reglas de UI actuales" abajo).

## Reglas de UI actuales

1. Usar componentes Ionic reales como base: `IonPage`, `IonContent`,
   `IonHeader`, `IonToolbar`, `IonList`, `IonItem`, `IonSelect`, `IonToggle`,
   `IonSegment`, `IonCard`, `IonModal`, `IonButton`, etc.
2. La navegacion global por secciones vive en el navbar/menu (`PageHeader` +
   `SideMenu`). El tabbar es para navegacion interna de la pantalla: tabs,
   vistas, modos o subsecciones propias de esa pagina. No mezclar estos dos
   niveles.
3. Toda pantalla con navegacion interna debe usar un tabbar reutilizable, no un
   segmento ad hoc en cada pagina.
4. Tailwind es apoyo para layout, spacing y pequenos ajustes visuales.
5. Si una combinacion de clases Tailwind se repite, crear una clase semantica en
   `apps/web/src/styles.css` y usar ahi `@apply`/clases Tailwind v4 cuando aporte
   mantenimiento.
6. Mantener los componentes custom al minimo. Hoy los custom propios justificados
   son `Logo` y `PinPad`; el resto debe ser Ionic + estilos reutilizables.
7. Para controles comunes, preferir el componente Ionic equivalente. Ejemplo:
   selector de tema/configuracion como `IonList` + `IonItem` + `IonSelect` con
   `IonSelectOption`, no un select hecho a mano.
8. No crear tarjetas o wrappers custom si `IonCard`, `IonList` o `IonItem` cubren
   el caso.
9. Tematizar por variables Ionic `--ion-*` en
   `apps/web/src/theme/ionic-theme.css`; evitar hardcodear la marca en cada pantalla
   salvo que sea parte de una clase reutilizable.
10. Evitar estilos inline y patrones que rompan CSP. Los Web Components de modulos
   se cargan por `import()` dinamico y deben seguir siendo CSP-safe.

## Arquitectura que no se debe romper

- La UI nunca toca la BD. UI/WC -> SDK -> runtime Rust.
- La seguridad real no esta en `hasPermission()` de JS; Rust revalida permisos,
  `hub_id` y payload en cada query/command.
- Los modulos declaran contrato tecnico en `module.json`. La clasificacion de
  marketplace vive en Cloud, no en el modulo.
- Dos ejes ortogonales (ARQUITECTURA.md §1): backend de datos (`single`/SQLite vs
  `cloud`/Aurora) x shell (`tauri` vs `web-pwa`). No atar Tauri a "local".
- Transport de datos por backend: `cloud` usa HTTP (query/command) + WebSocket (solo
  eventos); `single` usa Tauri `invoke` + events. En cualquier shell Tauri, `invoke`
  es ademas el canal de hardware local (independiente del backend) -> combo `cloud + Tauri`.
- **Dos productos, SIN sync ni Cloud DB remota** (ADR-0040, 2026-06-13; supera el
  "local-first + sync" de ADR-0031 y el tier "Cloud DB" de ADR-0030, ambos RETIRADOS):
  - **Local** (gratis): backend `single`, **SQLite local autoritativo**, un dispositivo,
    100% offline. El respaldo a la nube (cifrado a S3, manual o programado) lo da el módulo
    **`backup`** premium — no hay base de datos remota intermedia ni motor de sincronización.
  - **Cloud** (online): backend `cloud`, **Aurora por organización** + 1 contenedor ECS por hub,
    multi-dispositivo / web, *online-only*.
  - No existe migración Local→Cloud, ni RDS Proxy/NLB, ni crate `datasync`. El crate `sync`
    que sigue vivo es **solo** el cliente WebSocket de eventos en vivo, NO un motor de datos.
- El `bridge/` no se elimina: sidecar de hardware en Tauri, o standalone opcional
  para `cloud + web-PWA` (§2.7).
- AI y embeddings siempre pasan por el proxy del Cloud Portal, no directo desde
  hub.

## Referencia visual

Lenguaje visual y patrones de marca: ver el Cloud Portal (`../cloud/`) y `apps/web`.

La referencia visual no obliga a copiar implementacion. En hub se traduce a
Ionic: listas, items, selects, toggles, cards, modals y segmentos nativos.

## Comandos de verificacion

Desde la raiz de `hub`:

```sh
pnpm -F @erplora/web typecheck
pnpm -F @erplora/web verify
pnpm -F @erplora/web dev
```

Toda modificacion visual debe revisarse con Playwright. Flujo recomendado:

1. Arrancar `pnpm -F @erplora/web dev`.
2. Abrir las rutas tocadas con Playwright.
3. Sacar capturas desktop y mobile.
4. Corregir solapes, texto cortado, controles no Ionic o layout roto.
5. Ejecutar `typecheck` y, cuando aplique, `verify`.

## Forma de trabajar con varios workers

- Dividir por pantallas o por componentes compartidos con ownership claro.
- No editar todos `styles.css` a la vez sin coordinar. Si varios workers necesitan
  clases nuevas, uno debe ser owner de estilos globales o cada worker debe limitarse
  a clases de su pantalla y luego integrar.
- Cada worker debe indicar rutas tocadas, capturas Playwright revisadas y comandos
  ejecutados.
- No revertir cambios de otros workers. Adaptar el parche a lo que exista al
  integrar.

## Primeros objetivos probables

- Sustituir selects, toggles, tabs, listas y acciones custom por componentes Ionic.
- Mantener marketplace alineado con el hub actual: el Hub expone/proxy
  `/api/v1/modules/marketplace/catalog/`, que a su vez consulta el Cloud Portal en
  `/api/v1/marketplace/modules/`.
- Reducir HTML/CSS artesanal repetido creando pocas clases semanticas en
  `styles.css`.
- Mantener la apariencia de `uploads` donde aporte continuidad, pero con
  estructura Ionic.
- Revisar especialmente Ajustes, Roles/Permisos, Empleados, Marketplace, Billing,
  Sistema y selector de tema.

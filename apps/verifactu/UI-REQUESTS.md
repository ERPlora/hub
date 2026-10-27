# Peticiones a `@erplora/ui` de la app VeriFactu

Lo que la app necesita del submódulo `packages/ui` y no puede añadir ella misma (fuera de su carril). Mientras
no llegue, la app usa lo indicado en «Mientras tanto».

**Al cerrar la app** (CLOSE-VERIFACTU, 2026-10-27), contra `ERPlora/ui` `origin/main` defc6c0:
`ion:shield-checkmark-outline` ya está registrado en `src/shell/icons.ts` (ui#34) y sale de esta lista: la app lo pinta
desde este cierre (hub#281) en su icono, Recuperación, el paso y el panel del Inicio. Lo demás no ha llegado, todo tiene
sustituto en uso y ningún flujo está roto. Queda propuesto para `## 6` de `MIGRATION.md` como
`verifactu:ui-icons`, `verifactu:ui-money-format`, `verifactu:ui-page-tabs`, `verifactu:ui-format-moment` y
`verifactu:ui-file-drop`.

| Petición | Para qué | Mientras tanto |
|---|---|---|
| Registrar `ion:document-text-outline` en `packages/ui/src/shell/icons.ts` | El icono de «Registros» del módulo actual (menú y pestaña) | `ion:list-outline` |
| Registrar `ion:stats-chart-outline` | El icono del panel «Registros por estado» del Inicio del módulo actual | `ion:list-outline` |
| Un formateador de dinero en `@erplora/ui/components/format` | Pintar importes en céntimos («€12.10», «-12,10 €») sin copia por app | `frontend/lib/format.ts`, copia del de Facturación |
| Un componente de pestañas internas de una página (dos vías en Configuración) | Las pestañas «Lo remite ERPlora» / «Mi certificado» como las demás páginas | `ion-segment` con `mode="md"` |
| El formateador de momentos de la cronología del Inicio (`formatMoment` de `base/frontend/lib/home.ts`) en `@erplora/ui/components/format` | Que «Eventos AEAT recientes» diga «16:37», «Ayer 16:37» o la fecha corta, como «Actividad reciente» de Ventas en el mismo tablero | `formatDateTime`: fecha y hora enteras, como la pestaña Eventos |
| Un componente de subida de un fichero cualquiera con zona para soltarlo (`ImageUpload` es solo de imágenes y sin soltar) | Subir el `.p12` / `.pfx` en «Mi certificado» y los PDF del otorgamiento arrastrándolos, como el módulo actual | Un botón y el nombre del fichero (`frontend/lib/files.ts`) |

Al registrar un icono, cambiar a la vez `apps.py` (`icon`, `navigation`, `setup` y `widgets`), `frontend/tabs.ts`,
las páginas que lo pintan y sus tests (`tests/test_apps.py`, `frontend/tabs.test.ts`), y correr `pnpm gen:app-icons`.

# Página web (`website`)

La página pública de cada negocio en su propia dirección (`<slug>.erplora.com`, en `/`): el propietario elige una de
cuatro plantillas, una paleta y el fondo, rellena unas secciones fijas (barra y cabecera, sobre nosotros, catálogo,
galería, reseñas de Google, contacto con horario, ubicación y pie), oculta lo que no usa y publica. Quien abre la
dirección sin sesión ve la página; el equipo entra por su botón **Entrar**. Sin publicar, desconectada o con la app
apagada, la dirección sigue llevando al acceso del equipo. App nueva (PLAN §29 y su ampliación del 2026-10-22): el
producto actual no tenía página por negocio.

- **Estado**: completa (2026-10-23): los 12 flujos, `WEBSITE-F01` … `F12`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`**: ninguna abierta (sin `UI-REQUESTS.md`): `ColorInput` e `ImageUpload` llegaron con
  ERPlora/ui#20. El hueco que falta entre la miniatura y el texto de `ImageUpload` es un arreglo en la cola
  (`FIX-UI-IMAGEUPLOAD-THUMBNAIL-TOUCHES-TEXT`), no una petición.

## Qué hace hoy

- **El editor** (F01–F04, F06, F11, F12): borrador con autoguardado; cuatro plantillas intercambiables sin perder el
  contenido, ocho paletas en claro y oscuro (WCAG AA) con dos colores propios y fondo claro, oscuro o automático;
  secciones que se ocultan sin borrarse; imágenes jpeg, png o webp de hasta 5 MB guardadas por su contenido en el
  almacén del hub, dentro del espacio del plan que cuenta Archivos (409 `base.file_no_space`, su misma frase; la misma
  imagen otra vez no ocupa más); galería de hasta 12 fotos en su orden; enlace de Google Maps o Place ID para las reseñas; vista
  previa pintada por el mismo código que la página pública.
- **El catálogo** (F05): los productos a la venta de Inventario o los servicios ofrecidos de Servicios, por categoría y
  con su precio en la moneda del negocio (la de su país, con sus decimales), solo si esa app está activa en el hub (si
  no, vacío y el editor lo dice, nunca un error); copia al publicar y refresco al abrir la página.
- **Publicar y desconectar** (F07, F08): publicar copia el borrador y sube la versión; desconectar devuelve la
  dirección al acceso del equipo sin perder nada.
- **Compartir** (F09): la dirección, **Copiar enlace** y el QR en PNG y SVG.
- **La página pública** (F10): plantilla de Django con Bootstrap 5.3, en el idioma del navegador, sin cookies, con su
  propia CSP sin nonce, caché de una hora en el servidor por versión, idioma, día y moneda y un minuto en el navegador; sus tres
  lecturas públicas (`website.public.*`) admiten 60 por minuto por hub y visitante; las reseñas de Google las pide el
  servidor (Places API (New)), nunca el navegador.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:globe-outline`, categoría `organization`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` (entra en sus plantillas) |
| `requires` | `[]` |
| Usa de otras apps | Inventario y Servicios por el nombre de sus consultas (`inventory.product.list_for_sale`, `inventory.category.list`, `inventory.product_category.list`, `service.service.list_for_sale`, `service.category.list`), solo con la app activa en el hub (`base.relay.active_apps`). De la plataforma: `base.operations.hub_id`, `base.operations.business_currency` (la moneda de los precios en la vista previa y el catálogo público), `base.business.currency_of` (la misma moneda en la página pública, de la fila del registro que el host ya cargó, sin una transacción por visita) y `base.business.currency_decimals` (sus decimales), `storages["hub_files"]`, `base.media` (`/p/media/…`), `base.throttle` y la zona horaria del hub (`control.Hub.timezone`, el «hoy» del horario; Madrid si está vacía) |
| La usa | `base.public_home`: la entrada `/` del host del hub carga `apps/website/public_home.py` (`is_published`, `respond`) por `import_module`; ninguna app de negocio la lee |
| Pantallas | `/website` (editor, vista previa y «Compartir y QR») y la página pública en `/` |
| Operaciones | 7 consultas (`queries.py`) y 4 acciones (`services.py`), todas con su ruta en `/api/website/…` (11; las 3 `website.public.*` sin sesión) y `expose_api`; 5 con `ai=` (las que usa el asistente) |
| Eventos | 4, `website.<entidad>.<hecho>` (`events.py`); no reacciona a ninguno |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial`, `0002_theme_palettes`, `0003_theme_overrides` (las dos, solo JSON del tema) y `0004_site_reviews_snapshot`; todas reversibles |
| Admin | Django admin en `hubs.erplora.com`, de solo lectura salvo `is_live` (desconectar una página por soporte) |
| Fuera del Hub | Places API (New) de Google con `GOOGLE_PLACES_API_KEY` (Secrets Manager; ERPlora/aws#10) |
| Paquete público | entrada `website` de Vite, en la raíz del Hub (`frontend/website.ts`: Bootstrap 5.3, su `collapse` y `apps/website/frontend/public/`) |

Las decisiones de diseño (una fila por hub en la fase 1, la guarda única de lo público, render y caché, CSP, imágenes,
reseñas de Google, paletas, plantillas y licencias) están en «Para quien lo mantiene» del WORKBOOK; las de la
migración, en la ronda 2026-10-23 (CLOSE-WEBSITE) de `PLAN-HUB.md` (raíz de erplora-next), y la decisión de fondo en
PLAN §29 y §30.

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/website base/tests/test_public_home.py base/tests/test_media.py
pnpm test apps/website
pnpm e2e tests/e2e/website-flows.spec.ts tests/e2e/website.spec.ts   # sin GOOGLE_PLACES_API_KEY en el entorno
```

- Servidor: un `tests/test_<fichero>.py` por fichero; `test_live.py` prueba que guardar y publicar en un hub no avisa
  a otro, y `test_queries.py`/`test_services.py` que cada hub lee y escribe solo su fila.
- Pantallas y paquete público: `frontend/**/*.test.ts`; el catálogo y las reseñas se pintan igual en el servidor y en
  el paquete (`frontend/public/*.fixture.json`, comprobados por los dos lados).
- `website-flows.spec.ts` recorre un test por flujo en 390, 834 y 1440 px y deja la página de `a` desconectada al
  terminar (las demás e2e esperan el salto al acceso); se niega a correr con `GOOGLE_PLACES_API_KEY` y enseña las
  reseñas desde una respuesta guardada en la fila. `website.spec.ts`, las cuatro plantillas en claro y oscuro.

## Qué queda fuera

- `ai=` en las seis operaciones que no son herramienta del asistente, a la espera de `INTERNAL` y `live.E017` (PLAN
  §30) en `packages/live`.
- El dominio propio para la web (HUBS-F17, `## 6` de `MIGRATION.md`; PLAN-SAAS §8).
- `FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE` (`base/spa.py`) y `FIX-UI-IMAGEUPLOAD-THUMBNAIL-TOUCHES-TEXT`
  (`packages/ui`), en la cola.
- Lo que la app no hace a propósito (más páginas, HTML del usuario, horario importado de Horarios, sitemap…): «Lo que
  NO hace, a propósito» del WORKBOOK.

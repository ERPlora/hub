# @erplora/outfitkit

Web Components (**Lit**) que **extienden Ionic** con lo que falta para UIs de admin densas y
landings: `ok-data-table` y el *chrome* de landing (`ok-navbar`, `ok-footer`, `ok-container`,
`ok-container-full`, `ok-hero`). **No sustituye a Ionic**: para todo lo que Ionic hace bien
(form controls, botones, overlays…) se usa `ion-*` directo.

- **Standalone**: npm + CDN, **imports individuales** (tree-shake).
- **CSP estricta** (`script-src 'self'`, sin eval) — mismo listón que `apps/web`.
- **Tema** vía tokens `--ok-*` con fallback a `--ion-*` (hereda el tema/dark de Ionic si está).
- Funciona en el **shell Ionic React**, dentro de **módulos Lit** y en **plantillas Django**.

## Uso

### Bundler (hub `apps/web`, módulos, cualquier app)

```ts
import '@erplora/outfitkit/ok-data-table';                  // registra <ok-data-table>
import type { DataTableColumn, DataTableAction } from '@erplora/outfitkit';
```

### CDN / Django (sin bundler)

```html
<link rel="stylesheet" href="/static/css/outfitkit-theme.css" />  <!-- copia de theme.css -->
<script type="importmap">
  { "imports": { "lit": "https://esm.run/lit@3" } }
</script>
<script type="module" src="https://cdn.example.com/outfitkit/ok-navbar.js"></script>
<ok-navbar sticky>
  <img slot="brand" src="/logo.svg" alt="ERPlora" />
  <a href="/features">Características</a>
  <a href="/pricing">Precios</a>
  <ion-button slot="actions" href="/signup">Empezar</ion-button>
</ok-navbar>
```

`lit` queda **external** en todos los bundles → una sola copia compartida (impórtala con tu
bundler o con un `importmap` en CDN).

## Tema (`--ok-*`)

OutfitKit **no define valores por defecto**: copia `dist/theme.example.css`
(`@erplora/outfitkit/theme.css`) a tu `style.css` y ajústalo. Lo más cómodo es heredar de Ionic:

```css
:root {
  --ok-primary: var(--ion-color-primary);
  --ok-bg: var(--ion-background-color);
  --ok-surface: var(--ion-card-background);
  --ok-text: var(--ion-text-color);
  --ok-border: rgba(var(--ion-text-color-rgb), 0.12);
}
```

Cada token tiene fallback interno a `--ion-*` y a un hex, así que sin Ionic también funciona.

### Override por componente (estilo Ionic)

Igual que en Ionic (`ion-button { --background: … }`), cada componente expone variables
**sin guion bajo** que puedes sobreescribir por componente. Su valor por defecto sale de la
cadena `--ok-*` → `--ion-*` → hex:

```css
ok-navbar { --background: #0b0b0c; --color: #fff; }
ok-data-table { --header-background: #f4f4f5; --border-radius: 8px; }
ok-container { --max-width: 960px; }
```

Vars comunes: `--background`, `--color`, `--color-muted`, `--border-color`,
`--border-color-soft`, `--primary-color`, `--max-width`, `--padding`, `--radius`/`--border-radius`,
`--font` (según el componente; `ok-data-table` añade `--header-background`).

## `ok-data-table`

Port 1:1 del antiguo `<data-table>` de `@erplora/module-ui` — **misma API** (props, eventos y
tipos). Solo cambian el tag (`data-table` → `ok-data-table`) y la ruta de import.

- **Props**: `columns`, `rows`, `searchKeys`, `rowKeyField` (=`id`), `pageSize` (=10),
  `emptyMessage`, `searchPlaceholder`, `actions`, `serverSide`, `total`, `page`, `searchable`,
  `sort`, `sortDir`.
- **Eventos**: `rowAction` `{actionId,row}`, `pageChange` `number`, `sortChange` `{sort,dir}`,
  `searchChange` `string`, `filterChange` `{col,value}`.
- **Slot** `toolbar`. Usa `ion-searchbar`/`ion-button`/`ion-icon` por dentro (Ionic debe estar
  registrado por el host).

## Componentes de landing

| Tag | Slots | Notas |
|---|---|---|
| `ok-navbar` | `brand`, default (links), `actions` | responsive, burger en móvil; attrs `sticky`/`open` |
| `ok-footer` | default (columnas), `bottom` | grid responsive auto-fit |
| `ok-container` | default | ancho máx centrado (`--ok-container-max`) |
| `ok-container-full` | default | full-bleed con padding |
| `ok-hero` | `title`, `subtitle`, `actions`, default | pon un `<h1 slot="title">` para SEO |

Texto en **light DOM (slots)** → crawlable para SEO.

## Scripts

```sh
pnpm -F @erplora/outfitkit build        # vite (dist/*.js) + tsc (dist/*.d.ts)
pnpm -F @erplora/outfitkit typecheck
pnpm -F @erplora/outfitkit verify:csp   # rechaza eval/new Function en dist
```

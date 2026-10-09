// Carga de módulos en runtime: pregunta al runtime qué módulos ACTIVOS hay (y su navegación)
// y monta su Web Component (Lit) con import() dinámico. ARQUITECTURA.md §1, §7.7, §12 (Fase 0 #1).
//
// Fuente de la lista de módulos = el RUNTIME, no un set hardcodeado: el shell pide
// `GET /api/navigation`, que devuelve las entradas de navegación de los módulos INSTALADOS y
// ACTIVOS (el runtime ya filtra por estado). Para cada módulo se lee su `module.json` (de
// `/modules/<id>/module.json`) para resolver `ui.entry` (el bundle ESM a importar) y el sidecar
// de iconos. Así el shell sirve a CUALQUIER hub: lista exactamente lo que el runtime tiene.
//
// Los assets (module.json + dist/<id>.esm.js + icons.json) se sirven desde `/modules/**`:
//   - dev: copiados a public/ por sync-modules.mjs (puente del shell de desarrollo),
//   - prod: el runtime (crates/server, ServeDir) los sirve desde el web dir.
import { warnOnOutfitkitSkew } from './outfitkit-skew';
import type { ModuleManifest, NavigationItem } from '@erplora/module-types';
import { addIcons } from 'ionicons';

import { isModuleEntitled } from './entitlement';
import { moduleIconRegistry } from './icons';
import type { ModuleSettingsLocale } from './module-settings';
import { moduleBase } from './module-url';
import type { ModuleBillingLocale } from './module-quota';
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { orderSlotFillers } from './slot-fillers';
import type { SlotDef } from './slot-fillers';
import { getLocale } from '../i18n';

export interface MenuEntry {
  moduleId: string;
  /** Nombre legible del módulo (manifest.name) — para sidebar/título del shell. */
  moduleName: string;
  nav: NavigationItem;
  entryUrl: string;
  /**
   * SVG inline del icono de esta entrada, horneado por el módulo en build (ADR option-b:
   * `module-toolkit build` resuelve el nombre Iconify de `nav.icon` y escribe `dist/icons.json`).
   * `undefined` si el módulo no trae ese sidecar; el shell cae a resolver `nav.icon` por nombre
   * contra su propio registro (lib/icons.ts). Se pasa tal cual a `<HubIcon :name>`.
   */
  iconSvg?: string;
}

/** Una entrada de `GET /api/navigation` del runtime (un item por pestaña de navegación). */
interface RuntimeNavItem {
  module_id: string;
  /** Nombre del módulo ya traducido al idioma activo (ADR-0055; fallback locale→en→manifest). */
  module_name: string;
  /**
   * Versión INSTALADA del módulo (hub#935). Con ella se direcciona el bundle por versión. Viene del
   * runtime a propósito y no del `module.json`: esta respuesta va autenticada y ninguna caché la
   * toca, mientras que el manifest es un asset y sí puede llegar atrasado. `undefined` = runtime
   * anterior a hub#935 → se cae al `version` del manifest y, si tampoco está, a la url sin versión.
   */
  module_version?: string | null;
  id: string;
  label: string;
  icon?: string | null;
  component: string;
}

/**
 * Lo que contesta `/api/navigation`: el menú + cuántos módulos se espera que aporten uno (hub#894).
 *
 * `activeModules` es el número contra el que se comprueba una lista vacía. Cuenta los módulos
 * instalados **y activos**: uno que el admin apagó no se espera que aporte menú, así que contarlo
 * convertiría un hub apagado a propósito en un falso «no he podido cargar tus apps».
 * `undefined` = un runtime anterior que no lo dice, y «no lo ha dicho» nunca puede ser el motivo de
 * gritar.
 */
interface Navigation {
  items: RuntimeNavItem[];
  activeModules?: number;
}

const loadedEntries = new Set<string>();
/** Base bajo la que el runtime sirve los assets de los módulos (`/modules/<id>/...`). */
const MODULES_BASE = '/modules';

/**
 * Pide al runtime la navegación de los módulos instalados y ACTIVOS.
 * `GET /api/navigation` → `{ ok, data: [{ module_id, id, label, icon, component }] }`.
 * El runtime ya filtra por módulos activos; aquí no se vuelve a filtrar por estado.
 */
async function fetchNavigation(): Promise<Navigation> {
  // `?locale=` (ADR-0055): el runtime devuelve los labels ya traducidos (fallback locale→en→manifest).
  const res = await fetch(`${RUNTIME_URL}/api/navigation?locale=${encodeURIComponent(getLocale())}`, {
    headers: runtimeHeaders(),
  });
  if (!res.ok) throw new Error(`navigation → ${res.status}`);
  const env = (await res.json()) as {
    ok: boolean;
    data?: RuntimeNavItem[];
    active_modules?: number;
  };
  return { items: env.ok && env.data ? env.data : [], activeModules: env.active_modules };
}

/**
 * Sidecar `dist/icons.json` del módulo (nombre Iconify → SVG inline). `{}` si no lo trae.
 *
 * Además de devolverlo (para el icono del MENÚ), lo REGISTRA en ionicons: el Web Component del
 * módulo pinta sus iconos por nombre (`<ion-icon name="file-tray-stacked-outline">`) y, sin
 * registrar, ion-icon intenta bajar el SVG por red → en el Hub (offline, sin la carpeta svg/
 * servida) el icono sale VACÍO y sin ningún error. El shell no puede llevar una lista con los
 * iconos de cada módulo —menos aún de uno de terceros—, así que el módulo los trae en su zip y
 * aquí se registran al cargarlo.
 */
async function loadOutfitkitStamp(base: string, entry: string, moduleId: string): Promise<void> {
  // `dist/outfitkit.json` lo escribe `erplora build` (module-toolkit) con la versión que horneó.
  // Vive junto al bundle, como `icons.json`. Su ausencia NO es un defecto: es lo que traen los
  // módulos publicados antes del sello, y `warnOnOutfitkitSkew` se calla en ese caso.
  const distDir = entry.includes('/') ? entry.replace(/\/[^/]+$/, '') : '';
  await readOnce(
    `${base}/${distDir ? `${distDir}/` : ''}outfitkit.json`,
    async (url) => {
      try {
        const res = await fetch(url);
        if (!res.ok) return false;
        const stamp = (await res.json()) as { outfitkit?: string };
        warnOnOutfitkitSkew(moduleId, stamp.outfitkit, __OUTFITKIT_VERSION__);
        return true;
      } catch {
        // Sin sello legible no hay nada que comparar. Silencio: el módulo carga igual.
        return false;
      }
    },
    (ok) => !ok,
  );
}

/**
 * The bundle the module declares in `ui.entry`, or `null` when it declares none (hub#2635). The
 * install gate does not require a `ui` block, so the manifest is read as it arrives and not as the
 * type promises: reading `manifest.ui.entry` blindly threw for such a module and took the menu and
 * the home board of EVERY module down with it.
 */
function uiEntryOf(manifest: ModuleManifest): string | null {
  return (manifest as Partial<ModuleManifest>).ui?.entry || null;
}

async function loadIconMap(base: string, entry: string): Promise<Record<string, string>> {
  // icons.json vive junto al bundle del WC (dist/), lo genera `module-toolkit build`.
  const distDir = entry.includes('/') ? entry.replace(/\/[^/]+$/, '') : '';
  return readOnce(
    `${base}/${distDir ? `${distDir}/` : ''}icons.json`,
    async (url) => {
      try {
        const res = await fetch(url);
        if (!res.ok) return null;
        const icons = (await res.json()) as Record<string, string>;
        // Registrar los iconos una vez es cuantas veces vale: `addIcons` alimenta un registro
        // global del documento, y volver a llenarlo en cada pasada era trabajo puro.
        addIcons(moduleIconRegistry(icons));
        return icons;
      } catch {
        return null;
      }
    },
    (icons) => icons === null,
  ).then((icons) => icons ?? {});
}

/**
 * Los `module.json` ya leídos en ESTA sesión, por módulo (hub#1099).
 *
 * Se guarda la PROMESA, no el manifest: eso hace la caché y el dedupe de peticiones en vuelo la
 * misma cosa. Y hacen falta las dos: hay **tres** puertas que recorren todos los módulos instalados
 * en cada montaje de ruta —`loadMenu`, `loadInstalledManifests` (widgets ADR-0054 + slots ADR-0043)
 * y `resolveProtectsGuard` (hub#775)—, y arrancan solapadas, así que una caché que solo guardara el
 * resultado no llegaría a tiempo para ninguna de las tres.
 *
 * Sin esto, con los 25 módulos de un hub real, cada navegación pedía los 25 manifests **4 veces**
 * (~1,6 MB) y cualquier llamador repetido —`globalThis.erplora.loadSlot`, que main.ts cablea a
 * `loadSlotComponents` → `loadInstalledManifests`— multiplicaba SU cadencia por 25. Ese era el
 * amplificador que hacía crecer el ritmo hasta ~75 req/s con la pestaña en reposo: el shell no
 * ponía techo a cuántas veces se podía preguntar lo mismo. Ahora lo pone, y el techo es UNA.
 */
const manifestCache = new Map<string, Promise<ModuleManifest | null>>();

/**
 * Los SIDECARS ya leídos, por url (hub#1099): `dist/icons.json`, `dist/outfitkit.json` y
 * `locales/<lang>.json`. Se barren módulo a módulo en la misma pasada que el manifest, así que
 * cachear solo el manifest habría dejado tres cuartas partes de la tormenta en pie.
 *
 * Se guarda por URL y no por módulo porque la url ya lleva dentro todo lo que distingue una lectura
 * de otra —la versión instalada (hub#935) y el idioma activo—, así que un módulo actualizado o un
 * cambio de idioma son direcciones distintas y no pueden servirse de lo guardado para la anterior.
 */
const sidecarCache = new Map<string, Promise<unknown>>();

/**
 * Hace `read(url)` UNA sola vez por url, en toda la sesión, y comparte la petición en vuelo con
 * quien llegue mientras tanto. Los efectos de la lectura (registrar los iconos del módulo, avisar
 * del desfase de OutfitKit) también ocurren una vez, que es exactamente cuantas veces valen.
 *
 * Un fallo no se recuerda, por el mismo motivo que en `loadManifest`: un 5xx pasajero dejaría al
 * módulo sin iconos —mudos, sin ningún error— para el resto de la sesión.
 */
function readOnce<T>(url: string, read: (url: string) => Promise<T>, isFailure: (v: T) => boolean): Promise<T> {
  const cached = sidecarCache.get(url) as Promise<T> | undefined;
  if (cached) return cached;
  const pending = read(url);
  sidecarCache.set(url, pending as Promise<unknown>);
  void pending.then(
    (value) => {
      if (isFailure(value) && sidecarCache.get(url) === pending) sidecarCache.delete(url);
    },
    () => sidecarCache.delete(url),
  );
  return pending;
}

/**
 * Olvida lo cacheado (todo, o un módulo). Lo llama quien CAMBIA el conjunto instalado —instalar un
 * módulo desde el drawer del asistente, otro dispositivo o un blueprint—, que es el único momento
 * en que un manifest guardado puede haber dejado de ser el vigente sin recargar la página.
 *
 * Actualizar un módulo NO necesita esto: `reloadForModuleUpdate()` recarga la página entera (un
 * custom element solo se registra una vez, hub#935) y la recarga se lleva esta caché por delante.
 */
export function invalidateManifestCache(moduleId?: string): void {
  if (moduleId === undefined) {
    manifestCache.clear();
    sidecarCache.clear();
    return;
  }
  manifestCache.delete(moduleId);
  for (const url of sidecarCache.keys()) {
    if (url.startsWith(`${MODULES_BASE}/${moduleId}/`)) sidecarCache.delete(url);
  }
}

/**
 * Lee el `module.json` de un módulo instalado (`/modules/<id>/module.json`). `null` si falla.
 * Una vez por sesión y por módulo: la segunda llamada —y las que lleguen mientras la primera sigue
 * en vuelo— no vuelven a la red (hub#1099).
 */
export async function loadManifest(moduleId: string): Promise<ModuleManifest | null> {
  const cached = manifestCache.get(moduleId);
  if (cached) return cached;

  const pending = (async (): Promise<ModuleManifest | null> => {
    try {
      const res = await fetch(`${MODULES_BASE}/${moduleId}/module.json`);
      if (!res.ok) return null;
      return (await res.json()) as ModuleManifest;
    } catch {
      return null;
    }
  })();
  manifestCache.set(moduleId, pending);
  // Un fallo NO se recuerda. Cachear el `null` sería peor que no cachear nada: un 5xx pasajero
  // durante el arranque dejaría al módulo sin menú, sin widgets y sin guard para el resto de la
  // sesión —y sin nada en pantalla que lo explique—. Se recuerda solo lo que se leyó de verdad.
  void pending.then((manifest) => {
    if (!manifest && manifestCache.get(moduleId) === pending) manifestCache.delete(moduleId);
  });
  return pending;
}

/**
 * Construye las entradas de menú del shell a partir de lo que el runtime reporta como instalado
 * y activo (`/api/navigation`), resolviendo por módulo su `ui.entry` (del manifest) y los iconos.
 *
 * **LANZA si no ha podido construir la lista** (hub#894). Antes devolvía `[]` en ese caso, y ahí
 * estaba el defecto: `refreshModuleNav` recibía una lista vacía correcta, marcaba `moduleNavState`
 * como `ready`, y `ready` + cero filas se pinta «aún no tienes apps». Un 401 —la forma cotidiana de
 * una sesión desplazada por un segundo dispositivo en plan Free— le decía así a un hub con 12
 * módulos registrados que no tenía ninguno, en las DOS pantallas que listan apps, y le ofrecía
 * instalar lo que ya tenía. hub#770 escribió la regla (cargando / falló / vacío son tres frases
 * distintas) y su máquina de estados; esta función la saltaba porque nunca rechazaba.
 *
 * Lanza en dos casos, y son el mismo error visto por sus dos lados:
 *   1. la petición falló (401, 5xx, sin runtime) — no hay respuesta que creer;
 *   2. la respuesta llegó, el runtime esperaba menú (`active_modules > 0`) y no queda ninguna app que
 *      montar. Eso es una contradicción, no un hub vacío: alguno de los descartes silenciosos de
 *      abajo (entitlement, manifest ilegible) se los llevó todos.
 *
 * Lo que NO lanza: un hub sin módulos activos (`active_modules: 0` → `[]` es la respuesta verdadera,
 * incluido el hub que el admin apagó a propósito), un runtime que no reporta la cuenta (se toma al
 * pie de la letra, como antes), ni un módulo roto
 * entre varios buenos (los demás siguen en pantalla — «los datos ganan», hub#770).
 */
export async function loadMenu(): Promise<MenuEntry[]> {
  // Un fallo aquí sale hacia arriba a propósito: quien pinta la lista tiene que poder distinguir
  // «no pude preguntar» de «este hub no tiene apps».
  const { items: navItems, activeModules } = await fetchNavigation();

  // Agrupa las entradas de navegación por módulo (un manifest/icon-map por módulo, no por item).
  const byModule = new Map<string, RuntimeNavItem[]>();
  for (const item of navItems) {
    // Gate por entitlement (§2.10): solo se montan los módulos a los que el hub tiene derecho.
    // (El runtime ya filtra por activos; este filtro es el de licencia del shell.)
    if (!isModuleEntitled(item.module_id)) continue;
    const list = byModule.get(item.module_id);
    if (list) list.push(item);
    else byModule.set(item.module_id, [item]);
  }

  // Every module is read AT ONCE (hub#2021). The reads are independent, and one after another they
  // cost a round-trip per app: ~7 s on a 21-app hub after `module.activated` empties the manifest
  // cache, with the «Open» button of the app just switched on waiting for the last one. The
  // navigation order is kept: `Promise.all` answers in the order it was asked, not the order it heard.
  const perModule = await Promise.all(
    [...byModule].map(async ([moduleId, items]): Promise<MenuEntry[]> => {
      const manifest = await loadManifest(moduleId);
      if (!manifest) return []; // no manifest, no way to know which bundle to import → module left out.
      // The RUNTIME decides the version (hub#935); the manifest is only the fallback for an older
      // runtime. Believing the manifest once the runtime has spoken would rebuild the bug: a cached
      // `module.json` would point at the —also cached— url of the old version.
      const base = moduleBase(moduleId, items[0].module_version ?? manifest.version);
      const entry = uiEntryOf(manifest);
      if (!entry) return []; // no bundle to mount → module left out, the other apps stay (hub#2635).
      const icons = await loadIconMap(base, entry);
      return items.map((item) => ({
        moduleId,
        // Translated name from the runtime (ADR-0055); the manifest's one if it were missing.
        moduleName: item.module_name || manifest.name,
        nav: {
          id: item.id,
          label: item.label,
          icon: item.icon ?? undefined,
          component: item.component,
        },
        entryUrl: `${base}/${entry}`,
        iconSvg: item.icon ? icons[item.icon] : undefined,
      }));
    }),
  );
  const entries = perModule.flat();
  // Cero apps que montar cuando el runtime esperaba menú = contradicción (hub#894). Lo afirmó él
  // (`active_modules`), así que la lista vacía no puede ser la respuesta: se sube como fallo para que
  // se pinte un error y no la frase «aún no tienes apps», que manda al dueño a instalar lo que ya
  // tiene. `activeModules == null` = un runtime que no lo dice; ahí no hay contradicción que detectar.
  if (entries.length === 0 && (activeModules ?? 0) > 0) {
    throw new Error(
      `navigation → 0 apps to mount with ${activeModules} active module(s) on this hub`,
    );
  }
  return entries;
}

/**
 * Carga (una sola vez) el ESM del Web Component y devuelve el tag a montar.
 * Bajo `script-src 'self'` el import() dinámico de un módulo del mismo origen está
 * permitido — sin `unsafe-inline`/`unsafe-eval`.
 */
export async function loadComponent(entry: MenuEntry): Promise<string> {
  // Carga el bundle (registra el custom element) y devuelve el TAG a instanciar — NO la URL.
  // `loadEntryUrl` devuelve el entryUrl (lo necesita la recolección de widgets); aquí el llamador
  // (ModuleView) hace `document.createElement(tag)`, así que debe recibir `nav.component`.
  await loadEntryUrl(entry.entryUrl);
  return entry.nav.component;
}

/**
 * Carga (una sola vez) el ESM de un `entryUrl` ya resuelto y devuelve. Idempotente: misma
 * deduplicación que `loadComponent`. Lo usa la recolección de widgets de dashboard para la vía
 * `component` (cargar el bundle del módulo dueño del widget antes de `createElement(tag)`).
 */
async function loadEntryUrl(entryUrl: string): Promise<string> {
  if (!loadedEntries.has(entryUrl)) {
    await import(/* @vite-ignore */ entryUrl);
    loadedEntries.add(entryUrl);
  }
  return entryUrl;
}

/**
 * Recarga la página después de actualizar un módulo (hub#935).
 *
 * **Un custom element solo se puede registrar UNA vez por documento.** Cuando el dueño actualiza un
 * módulo, esta página ya importó el bundle anterior y ya definió su tag: el bundle nuevo no puede
 * sustituirlo por mucho que ahora viva en otra url y el servidor mande el código nuevo (el segundo
 * `customElements.define` del mismo tag ni siquiera se aplica). Direccionar por versión arregla la
 * ENTREGA; esto arregla la otra mitad, que es que lo entregado llegue a ejecutarse.
 *
 * Sin esto la pantalla mentiría igual que antes —lista y manifest en la versión nueva, componente en
 * la vieja—, que es justo el fallo mudo del que va la issue.
 *
 * El retardo es para que dé tiempo a leer el aviso de que se va a recargar: recargar de golpe deja
 * al dueño sin saber por qué se le ha movido la pantalla.
 */
export const MODULE_UPDATE_RELOAD_DELAY_MS = 1200;

export function reloadForModuleUpdate(delayMs = MODULE_UPDATE_RELOAD_DELAY_MS): void {
  setTimeout(() => window.location.reload(), delayMs);
}

/** Un módulo instalado + su manifest crudo (incluye `widgets`, `provides_slots`, etc.). */
/**
 * Traducciones del módulo para el idioma activo (`locales/<lang>.json`, ADR-0055). El runtime ya
 * traduce `name`/`navigation`; los TÍTULOS de widget los lee el shell del `module.json` crudo
 * (ADR-0054), así que su traducción también se resuelve en cliente desde este mismo fichero,
 * espejando `navigation.<id>.label`. Inglés canónico en el manifest; ES aquí.
 */
export interface ModuleLocaleFile {
  /** Per widget id: its `title`, `options.label`, chart legend (`options.seriesName`) and picker
   *  `category` in this language (sales#473 added the last two). */
  widgets?: Record<string, { title?: string; label?: string; seriesName?: string; category?: string }>;
  /** The label of each `bell` counter (hub#1678), by full id (`appointments.to_confirm`). */
  bell?: Record<string, { label?: string }>;
  /** Nombre del módulo traducido (el runtime ya lo resuelve para la nav; aquí sirve al diálogo de
   *  aprobación, que no pasa por `GET /api/navigation`). */
  name?: string;
  /** Cómo se llama cada command **en palabras del negocio** (hub#579), para que el encargado lea
   *  qué está aprobando en vez de una clave nuestra. Misma forma que `widgets`: clave completa
   *  (`sales.void`) → `{ label }`. Opcional: un módulo que no lo traiga hace que el diálogo caiga a
   *  su nombre localizado, nunca al nombre del command. */
  commands?: Record<string, { label?: string }>;
  /**
   * Strings of the module's SETTINGS screen (hub#1094): the heading and one entry per JSON Schema
   * property. The screen the shell generates read only the schema — canonical English — so it came
   * out in English on a Spanish hub even though `kitchen` and `tables` had been publishing these
   * very keys for weeks. Resolved in `lib/module-settings.ts`.
   */
  settings?: ModuleSettingsLocale;
  /**
   * Strings of the module's «Plan» tab: how each quota METRIC of `billing.tiers[].quota` is named
   * (hub#1604) and how each TIER of `billing.tiers[]` is called, by slug (hub#1748). Same story as
   * `settings` — the shell generates that screen out of the manifest, which is canonical English,
   * so «Estás en Free · Incluye 30 conversations per month» is what a Spanish hub read. Resolved in
   * `lib/module-quota.ts`.
   */
  billing?: ModuleBillingLocale;
  /**
   * The module's own screen strings, flat by key (`ui.cash` → `ui: { cash }`). The shell reads one
   * of them only where it paints a module's data outside that module's screen: Home › Activity
   * names `sales`' factory payment methods with these words (hub#2590).
   */
  ui?: Record<string, unknown>;
}

export interface InstalledManifest {
  moduleId: string;
  manifest: ModuleManifest;
  /**
   * URL of the module's ESM bundle (`/modules/<id>/<ui.entry>`), or `null` when the manifest
   * declares no `ui` block (hub#2635): its declarative widgets still render, a `component` widget
   * or slot of it cannot be mounted.
   */
  entryUrl: string | null;
  /** The module strings for the active language (`undefined` if it ships no `locales/<lang>.json`). */
  locale?: ModuleLocaleFile;
}

/**
 * Lee `locales/<lang>.json` del módulo (asset estático) desde su `base` — versionada cuando se sabe
 * la versión (hub#935), que es lo que evita leer las traducciones de la versión anterior.
 * `undefined` si no existe o falla.
 */
export async function loadModuleLocale(
  base: string,
  lang: string,
): Promise<ModuleLocaleFile | undefined> {
  return readOnce(
    `${base}/locales/${lang}.json`,
    async (url) => {
      try {
        const res = await fetch(url);
        if (!res.ok) return undefined;
        return (await res.json()) as ModuleLocaleFile;
      } catch {
        return undefined;
      }
    },
    (locale) => locale === undefined,
  );
}

/**
 * Reúne los manifests CRUDOS de TODOS los módulos instalados, ACTIVOS y con entitlement
 * (misma fuente que `loadMenu`: `GET /api/navigation`). Devuelve un manifest por módulo (no por
 * pestaña), leído del `module.json` servido por `ServeDir` — así sobreviven campos que la API
 * NO re-sirve (`widgets`, `provides_slots`, `chrome`; ADR-0043/0048/0054). `[]` si el runtime no
 * responde aún (boot temprano) — la recolección degrada con elegancia.
 */
export async function loadInstalledManifests(): Promise<InstalledManifest[]> {
  let navItems: RuntimeNavItem[];
  try {
    navItems = (await fetchNavigation()).items;
  } catch {
    return [];
  }

  const moduleIds: string[] = [];
  // Versión instalada que reporta el runtime, por módulo (hub#935) — la que direcciona el bundle.
  const versions = new Map<string, string | undefined>();
  for (const item of navItems) {
    if (!isModuleEntitled(item.module_id)) continue;
    if (versions.has(item.module_id)) continue;
    versions.set(item.module_id, item.module_version ?? undefined);
    moduleIds.push(item.module_id);
  }

  // Active language (ADR-0055): `locales/<lang>.json` is read for EVERY language, English included
  // (hub#2179). The manifest is canonical English for names and navigation, but `commands[].label`
  // has no place in it — `locales/en.json` is its only English source, and skipping it left the
  // approval dialog saying «an action in Sales / POS». Best-effort: missing file → manifest fallback.
  const lang = getLocale();
  const out: InstalledManifest[] = [];
  for (const moduleId of moduleIds) {
    const manifest = await loadManifest(moduleId);
    if (!manifest) continue;
    // Misma url versionada que el menú (hub#935): esta es la SEGUNDA puerta al mismo `import()`
    // (widgets del dashboard ADR-0054, slots cross-módulo ADR-0043). Arreglar solo el menú dejaría
    // el dashboard montando el bundle viejo del módulo recién actualizado.
    const base = moduleBase(moduleId, versions.get(moduleId) ?? manifest.version);
    // Registra los iconos HORNEADOS del módulo (dist/icons.json) también por esta vía: el dashboard
    // usa `loadInstalledManifests` (no la navegación), así que sin esto los iconos de cabecera de
    // widget que SÍ están horneados salían vacíos si su módulo no tenía entrada de navegación (P2).
    // A module without a `ui` block has no bundle, no `icons.json` and no stamp next to it; it is
    // still collected, so its declarative widgets and the other modules' ones survive (hub#2635).
    const entry = uiEntryOf(manifest);
    if (entry) {
      await loadIconMap(base, entry);
      void loadOutfitkitStamp(base, entry, moduleId);
    }
    const locale = await loadModuleLocale(base, lang);
    out.push({
      moduleId,
      manifest,
      entryUrl: entry ? `${base}/${entry}` : null,
      locale,
    });
  }
  return out;
}

/**
 * Asegura cargado el ESM del módulo dueño de un widget `component` (misma maquinaria CSP-safe que
 * `loadComponent`/`provides_slots`) y devuelve el tag a montar. El WC consulta sus datos él mismo.
 */
export async function loadModuleComponent(mod: InstalledManifest, tag: string): Promise<string> {
  // Rejecting is the caller's error state: the widget card says «No disponible», the settings
  // preview skips the field (hub#2635).
  if (!mod.entryUrl) throw new Error(`module ${mod.moduleId} declares no ui.entry to mount <${tag}>`);
  await loadEntryUrl(mod.entryUrl);
  return tag;
}

/**
 * Makes sure a module's custom element is DEFINED in this page, for a shell piece that needs it
 * outside that module's screen — the automatic ticket asks `sales` for its paper (hub#1921) on a
 * device that may never have opened the till. Nothing to do if the tag is already defined; a module
 * that is not installed (or not entitled) resolves without defining anything, and the caller
 * decides what that means. Same versioned bundle url as the menu and the slots.
 */
export async function loadModuleElement(moduleId: string, tag: string): Promise<void> {
  if (customElements.get(tag)) return;
  const mod = (await loadInstalledManifests()).find((m) => m.moduleId === moduleId);
  if (mod) await loadModuleComponent(mod, tag);
}

/**
 * Resuelve los componentes que los módulos instalados aportan a un SLOT cross-módulo (ADR-0043,
 * `provides_slots`). Reúne las entradas que matchean `slot` de TODOS los manifests, las ordena por
 * `priority` ascendente, asegura cargado el ESM de cada módulo dueño (CSP-safe, registra su WC) y
 * devuelve los tags a montar. El WC consulta sus datos él mismo y el permiso se revalida en server
 * (misma filosofía que la recolección de widgets). Lo consume `globalThis.erplora.loadSlot` que
 * llaman los WC de módulo (p.ej. el POS monta el picker de mesa/cliente). `[]` si el runtime no
 * responde, ningún módulo aporta al slot, o el ESM de un aportante falla (ese se omite).
 */
/** Un aportante resuelto de un slot: el tag a montar + la metadata del def (tab_label, tab_icon…). */
export type SlotComponent = SlotDef & { component: string };

export async function loadSlotComponents(slot: string): Promise<SlotComponent[]> {
  let manifests: InstalledManifest[];
  try {
    manifests = await loadInstalledManifests();
  } catch {
    return [];
  }
  // Match + orden por `priority` = lógica pura testeada en `slot-fillers.test.ts`. Aquí solo queda
  // la I/O: cargar el ESM de cada aportante (registra su WC) en orden y devolver los tags a montar.
  // Se propaga la metadata del def (p.ej. `tab_label`/`tab_icon` del modal de pestañas del POS,
  // ADR-0043 B); `component` queda garantizado. El consumidor lee lo que necesite.
  const out: SlotComponent[] = [];
  for (const { mod, component, def } of orderSlotFillers(manifests, slot)) {
    try {
      await loadModuleComponent(mod, component);
      out.push({ ...def, component });
    } catch {
      /* un aportante cuyo ESM falle se omite (no rompe el resto del slot) */
    }
  }
  return out;
}

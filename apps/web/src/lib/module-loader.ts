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
import type { ModuleManifest, NavigationItem } from '@erplora/module-types';
import { addIcons } from 'ionicons';

import { isModuleEntitled } from './entitlement';
import { moduleIconRegistry } from './icons';
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
  id: string;
  label: string;
  icon?: string | null;
  component: string;
}

/**
 * Lo que contesta `/api/navigation`: el menú + cuántos módulos TIENE el hub (hub#894).
 *
 * `installed` es el número contra el que se comprueba una lista vacía. `undefined` = un runtime
 * anterior que no lo dice, y «no lo ha dicho» nunca puede ser el motivo de gritar.
 */
interface Navigation {
  items: RuntimeNavItem[];
  installed?: number;
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
  const env = (await res.json()) as { ok: boolean; data?: RuntimeNavItem[]; installed?: number };
  return { items: env.ok && env.data ? env.data : [], installed: env.installed };
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
async function loadIconMap(base: string, entry: string): Promise<Record<string, string>> {
  // icons.json vive junto al bundle del WC (dist/), lo genera `module-toolkit build`.
  const distDir = entry.includes('/') ? entry.replace(/\/[^/]+$/, '') : '';
  try {
    const res = await fetch(`${base}/${distDir ? `${distDir}/` : ''}icons.json`);
    if (!res.ok) return {};
    const icons = (await res.json()) as Record<string, string>;
    addIcons(moduleIconRegistry(icons));
    return icons;
  } catch {
    return {};
  }
}

/** Lee el `module.json` de un módulo instalado (`/modules/<id>/module.json`). `null` si falla. */
export async function loadManifest(moduleId: string): Promise<ModuleManifest | null> {
  try {
    const res = await fetch(`${MODULES_BASE}/${moduleId}/module.json`);
    if (!res.ok) return null;
    return (await res.json()) as ModuleManifest;
  } catch {
    return null;
  }
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
 *   2. la respuesta llegó, el hub TIENE módulos (`installed > 0`) y aun así no queda ninguna app que
 *      montar. Eso es una contradicción, no un hub vacío: alguno de los descartes silenciosos de
 *      abajo (entitlement, manifest ilegible) se los llevó todos.
 *
 * Lo que NO lanza: un hub genuinamente vacío (`installed: 0` → `[]` es la respuesta verdadera), un
 * runtime que no reporta `installed` (se toma al pie de la letra, como antes), ni un módulo roto
 * entre varios buenos (los demás siguen en pantalla — «los datos ganan», hub#770).
 */
export async function loadMenu(): Promise<MenuEntry[]> {
  // Un fallo aquí sale hacia arriba a propósito: quien pinta la lista tiene que poder distinguir
  // «no pude preguntar» de «este hub no tiene apps».
  const { items: navItems, installed } = await fetchNavigation();

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

  const entries: MenuEntry[] = [];
  for (const [moduleId, items] of byModule) {
    const manifest = await loadManifest(moduleId);
    if (!manifest) continue; // sin manifest no sabemos qué bundle importar → se omite el módulo.
    const base = `${MODULES_BASE}/${moduleId}`;
    const entry = manifest.ui.entry;
    const icons = await loadIconMap(base, entry);
    for (const item of items) {
      entries.push({
        moduleId,
        // Nombre traducido que da el runtime (ADR-0055); fallback al del manifest si faltara.
        moduleName: item.module_name || manifest.name,
        nav: {
          id: item.id,
          label: item.label,
          icon: item.icon ?? undefined,
          component: item.component,
        },
        entryUrl: `${base}/${entry}`,
        iconSvg: item.icon ? icons[item.icon] : undefined,
      });
    }
  }
  // Cero apps que montar en un hub que SÍ tiene módulos = contradicción (hub#894). El runtime lo
  // afirmó (`installed`), así que la lista vacía no puede ser la respuesta: se sube como fallo para
  // que se pinte un error y no la frase «aún no tienes apps», que manda al dueño a instalar lo que ya
  // tiene. `installed == null` = un runtime que no lo dice; ahí no hay contradicción que detectar.
  if (entries.length === 0 && (installed ?? 0) > 0) {
    throw new Error(
      `navigation → 0 apps to mount with ${installed} module(s) installed on this hub`,
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

/** Un módulo instalado + su manifest crudo (incluye `widgets`, `provides_slots`, etc.). */
/**
 * Traducciones del módulo para el idioma activo (`locales/<lang>.json`, ADR-0055). El runtime ya
 * traduce `name`/`navigation`; los TÍTULOS de widget los lee el shell del `module.json` crudo
 * (ADR-0054), así que su traducción también se resuelve en cliente desde este mismo fichero,
 * espejando `navigation.<id>.label`. Inglés canónico en el manifest; ES aquí.
 */
export interface ModuleLocaleFile {
  widgets?: Record<string, { title?: string; label?: string }>;
}

export interface InstalledManifest {
  moduleId: string;
  manifest: ModuleManifest;
  /** URL del bundle ESM del WC del módulo (`/modules/<id>/<ui.entry>`). */
  entryUrl: string;
  /** Traducciones del módulo para el idioma activo (o `undefined` si no trae/idioma canónico). */
  locale?: ModuleLocaleFile;
}

/** Lee `/modules/<id>/locales/<lang>.json` (asset estático). `undefined` si no existe o falla. */
export async function loadModuleLocale(
  moduleId: string,
  lang: string,
): Promise<ModuleLocaleFile | undefined> {
  try {
    const res = await fetch(`${MODULES_BASE}/${moduleId}/locales/${lang}.json`);
    if (!res.ok) return undefined;
    return (await res.json()) as ModuleLocaleFile;
  } catch {
    return undefined;
  }
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
  const seen = new Set<string>();
  for (const item of navItems) {
    if (!isModuleEntitled(item.module_id)) continue;
    if (seen.has(item.module_id)) continue;
    seen.add(item.module_id);
    moduleIds.push(item.module_id);
  }

  // Idioma activo (ADR-0055): para el canónico inglés no se busca locale (el manifest ya está en EN);
  // para otros se intenta `locales/<lang>.json` (best-effort, fallback al título del manifest).
  const lang = getLocale();
  const out: InstalledManifest[] = [];
  for (const moduleId of moduleIds) {
    const manifest = await loadManifest(moduleId);
    if (!manifest) continue;
    // Registra los iconos HORNEADOS del módulo (dist/icons.json) también por esta vía: el dashboard
    // usa `loadInstalledManifests` (no la navegación), así que sin esto los iconos de cabecera de
    // widget que SÍ están horneados salían vacíos si su módulo no tenía entrada de navegación (P2).
    await loadIconMap(`${MODULES_BASE}/${moduleId}`, manifest.ui.entry);
    const locale = lang === 'en' ? undefined : await loadModuleLocale(moduleId, lang);
    out.push({
      moduleId,
      manifest,
      entryUrl: `${MODULES_BASE}/${moduleId}/${manifest.ui.entry}`,
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
  await loadEntryUrl(mod.entryUrl);
  return tag;
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

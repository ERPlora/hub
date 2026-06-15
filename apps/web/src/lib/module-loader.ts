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

import { isModuleEntitled } from './entitlement';
import { RUNTIME_URL } from './runtime';

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
  id: string;
  label: string;
  icon?: string | null;
  component: string;
}

const loadedEntries = new Set<string>();
/** Base bajo la que el runtime sirve los assets de los módulos (`/modules/<id>/...`). */
const MODULES_BASE = '/modules';

/**
 * Pide al runtime la navegación de los módulos instalados y ACTIVOS.
 * `GET /api/navigation` → `{ ok, data: [{ module_id, id, label, icon, component }] }`.
 * El runtime ya filtra por módulos activos; aquí no se vuelve a filtrar por estado.
 */
async function fetchNavigation(): Promise<RuntimeNavItem[]> {
  const res = await fetch(`${RUNTIME_URL}/api/navigation`);
  if (!res.ok) throw new Error(`navigation → ${res.status}`);
  const env = (await res.json()) as { ok: boolean; data?: RuntimeNavItem[] };
  return env.ok && env.data ? env.data : [];
}

/** Sidecar `dist/icons.json` del módulo (nombre Iconify → SVG inline). `{}` si no lo trae. */
async function loadIconMap(base: string, entry: string): Promise<Record<string, string>> {
  // icons.json vive junto al bundle del WC (dist/), lo genera `module-toolkit build`.
  const distDir = entry.includes('/') ? entry.replace(/\/[^/]+$/, '') : '';
  try {
    const res = await fetch(`${base}/${distDir ? `${distDir}/` : ''}icons.json`);
    if (!res.ok) return {};
    return (await res.json()) as Record<string, string>;
  } catch {
    return {};
  }
}

/** Lee el `module.json` de un módulo instalado (`/modules/<id>/module.json`). `null` si falla. */
async function loadManifest(moduleId: string): Promise<ModuleManifest | null> {
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
 * Si el runtime no responde aún (boot temprano, sin runtime en dev), devuelve `[]` sin romper:
 * el shell deja la nav vacía y `refreshModuleNav` reintentará tras instalar/activar.
 */
export async function loadMenu(): Promise<MenuEntry[]> {
  let navItems: RuntimeNavItem[];
  try {
    navItems = await fetchNavigation();
  } catch {
    return [];
  }

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
        moduleName: manifest.name,
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
  return entries;
}

/**
 * Carga (una sola vez) el ESM del Web Component y devuelve el tag a montar.
 * Bajo `script-src 'self'` el import() dinámico de un módulo del mismo origen está
 * permitido — sin `unsafe-inline`/`unsafe-eval`.
 */
export async function loadComponent(entry: MenuEntry): Promise<string> {
  if (!loadedEntries.has(entry.entryUrl)) {
    await import(/* @vite-ignore */ entry.entryUrl);
    loadedEntries.add(entry.entryUrl);
  }
  return entry.nav.component;
}

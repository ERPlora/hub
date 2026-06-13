// Carga de módulos en runtime: lee los manifests de los módulos instalados y monta su
// Web Component (Lit) con import() dinámico. ARQUITECTURA.md §1, §7.7, §12 (Fase 0 #1).
//
// En producción la lista de módulos vendría del runtime (tabla hub_module) y los assets los
// serviría crates/server. Aquí, en el shell web, se sirven desde /modules/** (copiados a
// public/ por sync-modules.mjs).
import type { ModuleManifest, NavigationItem } from '@erplora/module-types';

import { isModuleEntitled } from './entitlement';

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

const INSTALLED_MODULES = ['/modules/inventory/module.json'];
const loadedEntries = new Set<string>();

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

/** Lee los manifests y devuelve las entradas de menú (desde `navigation`). */
export async function loadMenu(): Promise<MenuEntry[]> {
  const entries: MenuEntry[] = [];
  for (const url of INSTALLED_MODULES) {
    const res = await fetch(url);
    const manifest = (await res.json()) as ModuleManifest;
    // Gate por entitlement (§2.10): solo se montan los módulos a los que el hub tiene derecho.
    if (!isModuleEntitled(manifest.id)) continue;
    const base = url.replace(/\/module\.json$/, '');
    const icons = await loadIconMap(base, manifest.ui.entry);
    for (const nav of manifest.navigation ?? []) {
      entries.push({
        moduleId: manifest.id,
        moduleName: manifest.name,
        nav,
        entryUrl: `${base}/${manifest.ui.entry}`,
        iconSvg: nav.icon ? icons[nav.icon] : undefined,
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

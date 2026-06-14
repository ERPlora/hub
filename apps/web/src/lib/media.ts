// Cliente de la pantalla /files — contrato `GET /api/media` del runtime del Hub.
//
// La carpeta `media/` es el path por defecto de TODOS los ficheros del Hub: se crea en el
// despliegue/instalación y allí escriben los módulos (adjuntos, exports, PDFs…), los registros
// de sistema (`_logs/`) y el monitor de actividad (`_system/`). Esta pantalla la navega como un
// gestor tipo Drive (componente `ok-file-manager` de OutfitKit).
//
// Igual que `lib/system.ts`, la FUENTE depende del eje A de la arquitectura (hub/ARQUITECTURA.md §1):
//   • single (Tauri/desktop) → listado del disco local bajo `media/`
//   • cloud  (ECS)           → listado de objetos S3 `erplora-storage` con prefijo del hub
// El runtime Rust es la autoridad: él lista, calcula tamaños/quota y firma las URLs de descarga.
// El navegador NUNCA toca el disco/S3 directamente (contrato Hub↔Cloud, hub/CLAUDE.md).
//
// Contrato recomendado (lo implementa el humano en `crates/server`; ver architecture/hub):
//   GET /api/media?folder=<id>  → envelope { ok, data: MediaListing }
//     - folder ausente o "" ⇒ raíz (la carpeta `media/`).
//     - `folders` = ÁRBOL completo de carpetas (para el panel lateral; se pide una vez).
//     - `files`   = contenido de la carpeta `folder` pedida.
//     - `path`    = breadcrumb de la raíz a `folder`.
//     - `quota`   = espacio usado/total (opcional; disco en single, plan en cloud).
//
// Mientras el endpoint no exista (404) o el runtime no responda, `fetchMedia` devuelve `null`:
// la pantalla muestra su estado vacío propio (sin ficheros), nunca datos inventados.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Carpeta del árbol lateral (recursiva). Shape directo de `OkFmFolder` del file-manager. */
export interface MediaFolder {
  /** Id único / clave de navegación (p.ej. "modules/inventory" o "_logs"). */
  id: string;
  /** Texto visible. */
  label: string;
  /** Nombre de ionicon opcional (p.ej. "cube-outline" para un módulo, "terminal-outline" para logs). */
  icon?: string;
  /** Recuento de elementos. */
  count?: number;
  /** Sub-carpetas. */
  children?: MediaFolder[];
}

/** Fichero del contenido de la carpeta actual. Shape directo de `OkFmFile`. */
export interface MediaFile {
  id: string;
  name: string;
  /** Extensión/tipo (pdf, xlsx, png, log…); si falta, se deriva del nombre. */
  ext?: string;
  /** Categoría informativa opcional. */
  kind?: string;
  /** Tamaño ya formateado (p.ej. "218 KB"). */
  sizeLabel?: string;
  /** Fecha de modificación ya formateada (p.ej. "2026-06-14 09:14"). */
  modified?: string;
  /** URL firmada de descarga/abrir (S3 en cloud, ruta local en Tauri); ausente = no descargable. */
  url?: string;
  /** Miniatura opcional (imágenes). */
  thumb?: string;
}

/** Migaja del breadcrumb (de raíz a carpeta actual). */
export interface MediaCrumb {
  id: string;
  label: string;
}

/** Medidor de espacio de la carpeta media. */
export interface MediaQuota {
  /** Espacio usado formateado (p.ej. "1,8 GB"). */
  usedLabel: string;
  /** Espacio total formateado (p.ej. "5 GB"). */
  totalLabel: string;
  /** Fracción ocupada 0..1. */
  fraction: number;
}

/** Respuesta de `GET /api/media` (campo `data` del envelope del runtime). */
export interface MediaListing {
  /** Árbol completo de carpetas (panel lateral). */
  folders: MediaFolder[];
  /** Contenido de la carpeta pedida. */
  files: MediaFile[];
  /** Breadcrumb de raíz a la carpeta pedida. */
  path: MediaCrumb[];
  /** Medidor de espacio (opcional). */
  quota?: MediaQuota;
}

/** Envelope estándar del runtime (`{ ok, data }`). */
interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: { message?: string };
}

/**
 * Lista el contenido de una carpeta de `media/` (raíz si `folder` se omite).
 *
 * NO lanza ni inventa datos: si el endpoint todavía no existe (404) o el runtime no responde,
 * devuelve `null` para que la UI muestre su estado vacío real en vez de mock.
 */
export async function fetchMedia(folder = ''): Promise<MediaListing | null> {
  try {
    const qs = folder ? `?folder=${encodeURIComponent(folder)}` : '';
    const res = await fetch(`${RUNTIME_URL}/api/media${qs}`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    const env = (await res.json()) as Envelope<MediaListing>;
    return env.ok && env.data ? env.data : null;
  } catch {
    return null;
  }
}

/**
 * Sube ficheros a una carpeta de `media/` vía `POST /api/media/upload` (multipart).
 * Devuelve `true` si el runtime aceptó la subida. Degrada a `false` si el endpoint no existe.
 */
export async function uploadMedia(folder: string, files: File[]): Promise<boolean> {
  try {
    const form = new FormData();
    if (folder) form.append('folder', folder);
    for (const f of files) form.append('files', f, f.name);
    // No fijar Content-Type: el navegador pone el boundary del multipart.
    const res = await fetch(`${RUNTIME_URL}/api/media/upload`, {
      method: 'POST',
      headers: runtimeHeaders(),
      body: form,
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Elimina un fichero de `media/` vía `DELETE /api/media?path=<id>`.
 * Devuelve `true` si el runtime lo aceptó. Degrada a `false` si el endpoint no existe.
 */
export async function deleteMedia(id: string): Promise<boolean> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/media?path=${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: runtimeHeaders(),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Crea una sub-carpeta dentro de `parent` vía `POST /api/media/folder`.
 * Devuelve `true` si el runtime la creó. Degrada a `false` si el endpoint no existe.
 */
export async function createMediaFolder(parent: string, name: string): Promise<boolean> {
  try {
    const res = await fetch(`${RUNTIME_URL}/api/media/folder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ parent, name }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

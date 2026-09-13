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
// A refusal is returned, never invented away (hub#1776): every call answers either its data or a
// `MediaFailure` carrying the runtime's stable code, and the screen turns that code into a sentence
// (`mediaFailureSentence`). Only a request that never reached the hub comes back without a code.

import { RUNTIME_URL, runtimeHeaders } from './runtime';
import { localDoorSentence, type Translator } from './runtime-error-sentence';

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
  /** Carpeta de solo lectura (reservada del hub o de un módulo que no opta en `user_actions`):
   *  no se puede arrastrar, ni renombrar, ni recibir drops. La calcula el runtime (ADR-0172). */
  readOnly?: boolean;
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

/**
 * Qué puede hacer el usuario en la carpeta pedida (ADR-0172). La decide el módulo dueño de esa
 * carpeta; el runtime la calcula y la manda para que la UI no pinte botones que darán 403.
 * **No es la barrera**: cada endpoint la revalida. Ausente = runtime antiguo → sin restricciones.
 */
export interface MediaPolicy {
  upload: boolean;
  rename: boolean;
  delete: boolean;
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
  /** Acciones permitidas en esta carpeta (ausente en runtimes anteriores al ADR-0172). */
  policy?: MediaPolicy;
}

/** Envelope estándar del runtime (`{ ok, data }`). */
interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: { code?: string; message?: string };
}

/**
 * A media door said no (hub#1776). `code` is the runtime's stable reason (`media.read_only_folder`,
 * `cloud_unreachable`…); it is absent only when the request never reached the hub (`status` 0) or
 * an old hub answered without one.
 */
export interface MediaFailure {
  ok: false;
  status: number;
  code?: string;
}

/** What an action on media answers: done, or refused with its reason. */
export type MediaOutcome = { ok: true } | MediaFailure;

/** Whether a listing call came back refused rather than with the listing. */
export function isMediaFailure(value: unknown): value is MediaFailure {
  return typeof value === 'object' && value !== null && (value as { ok?: unknown }).ok === false;
}

/** The refusal of a response that is not a success, with the code the runtime put in it. */
async function failureOf(res: Response): Promise<MediaFailure> {
  const env = (await res.json().catch(() => null)) as Envelope<unknown> | null;
  const code = typeof env?.error?.code === 'string' ? env.error.code : undefined;
  return { ok: false, status: res.status, code };
}

/** A request that never reached the hub: the one failure that IS the connection. */
const UNREACHED: MediaFailure = { ok: false, status: 0, code: undefined };

/** The outcome of an action call. */
async function outcomeOf(request: () => Promise<Response>): Promise<MediaOutcome> {
  let res: Response;
  try {
    res = await request();
  } catch {
    return { ...UNREACHED };
  }
  return res.ok ? { ok: true } : failureOf(res);
}

/**
 * The sentence a person reads for a refusal of Files (hub#1776): the catalogue's sentence for the
 * code (`files.errors.*`, then the shared `runtimeErrors.*`), or `fallback` — the screen's own line —
 * when there is no code or this shell has no sentence for it.
 */
export function mediaFailureSentence(failure: MediaFailure, i18n: Translator, fallback: string): string {
  if (!failure.code) return fallback;
  return localDoorSentence({ code: failure.code }, i18n, ['files.errors', 'runtimeErrors'], fallback);
}

/**
 * Lista el contenido de una carpeta de `media/` (raíz si `folder` se omite).
 *
 * Never throws and never invents data: a refusal comes back as a {@link MediaFailure} with the
 * runtime's code, so the screen can say why instead of «check the connection» (hub#1776).
 */
export async function fetchMedia(folder = ''): Promise<MediaListing | MediaFailure> {
  const qs = folder ? `?folder=${encodeURIComponent(folder)}` : '';
  let res: Response;
  try {
    res = await fetch(`${RUNTIME_URL}/api/media${qs}`, { headers: runtimeHeaders() });
  } catch {
    return { ...UNREACHED };
  }
  if (!res.ok) return failureOf(res);
  const env = (await res.json().catch(() => null)) as Envelope<MediaListing> | null;
  return env?.ok && env.data ? env.data : { ok: false, status: res.status, code: 'cloud_unreadable' };
}

/**
 * Sube ficheros a una carpeta de `media/` vía `POST /api/media/upload` (multipart).
 * Answers `{ ok: true }` or the refusal with its code (hub#1776).
 */
export async function uploadMedia(folder: string, files: File[]): Promise<MediaOutcome> {
  const form = new FormData();
  if (folder) form.append('folder', folder);
  for (const f of files) form.append('files', f, f.name);
  // No fijar Content-Type: el navegador pone el boundary del multipart.
  return outcomeOf(() =>
    fetch(`${RUNTIME_URL}/api/media/upload`, { method: 'POST', headers: runtimeHeaders(), body: form }),
  );
}

/**
 * Elimina un fichero de `media/` vía `DELETE /api/media?path=<id>`.
 * Answers `{ ok: true }` or the refusal with its code (hub#1776).
 */
export async function deleteMedia(id: string): Promise<MediaOutcome> {
  return outcomeOf(() =>
    fetch(`${RUNTIME_URL}/api/media?path=${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: runtimeHeaders(),
    }),
  );
}

/**
 * Contenido de un fichero de media, para el visor del modal (`FilePreviewModal`).
 *
 * La URL relativa la sirve el runtime (`/api/media/raw`) y lleva la sesión del hub: es la vía
 * normal en LOS DOS productos, porque el runtime es quien lee el disco (single) o pide los bytes
 * al Cloud (cloud). Una URL absoluta solo aparece si el listado viene de un runtime antiguo que
 * aún devolvía la URL firmada de S3: se pide tal cual y SIN la cabecera de sesión (es un secreto
 * del hub, no viaja a un tercero); si el bucket no tiene CORS, fallará y el modal avisará.
 *
 * `null` = no hay bytes que enseñar (sin URL, error de red o respuesta no OK).
 */
export async function fetchMediaBytes(file: MediaFile): Promise<ArrayBuffer | null> {
  if (!file.url) return null;
  const absolute = /^https?:\/\//.test(file.url);
  try {
    const res = absolute
      ? await fetch(file.url)
      : await fetch(`${RUNTIME_URL}${file.url}`, { headers: runtimeHeaders() });
    if (!res.ok) return null;
    return await res.arrayBuffer();
  } catch {
    return null;
  }
}

/**
 * Renombra un fichero o una carpeta vía `POST /api/media/rename` (ADR-0172).
 * `name` es un NOMBRE, no una ruta: renombrar nunca mueve nada de sitio.
 * Answers `{ ok: true }` or the refusal with its code, e.g. `media.read_only_folder` (hub#1776).
 */
export async function renameMedia(path: string, name: string): Promise<MediaOutcome> {
  return outcomeOf(() =>
    fetch(`${RUNTIME_URL}/api/media/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ path, name }),
    }),
  );
}

/**
 * Crea una sub-carpeta dentro de `parent` vía `POST /api/media/folder`.
 * Answers `{ ok: true }` or the refusal with its code (hub#1776).
 */
export async function createMediaFolder(parent: string, name: string): Promise<MediaOutcome> {
  return outcomeOf(() =>
    fetch(`${RUNTIME_URL}/api/media/folder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ parent, name }),
    }),
  );
}

/**
 * Mueve un fichero o carpeta de `from` a `to` vía `POST /api/media/move` (ADR-0172).
 * El runtime valida que el origen pueda modificarse (sacarlo = delete) y el destino recibir
 * escritura (meterlo = upload): las carpetas de solo lectura no se mueven ni reciben drops.
 * `to` es la carpeta destino (relativa a `media/`; `''` = raíz). Answers `{ ok: true }` or the refusal.
 */
export async function moveMedia(from: string, to: string): Promise<MediaOutcome> {
  return outcomeOf(() =>
    fetch(`${RUNTIME_URL}/api/media/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({ from, to }),
    }),
  );
}

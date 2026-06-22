// Reporte AUTOMÁTICO de errores del frontend al runtime local (que los reenvía al Cloud).
// Sin modal, sin captura de pantalla, sin acción del usuario: enganchamos los eventos globales
// del navegador + el errorHandler de Vue y hacemos un POST best-effort al runtime local.
//
// Contrato (lo implementa el worker del runtime — coincidir EXACTAMENTE):
//   POST /api/error-report
//   body: { type:"js_error", message, stack, url, component, module_id }
//   → { ok: true }. Best-effort: ignoramos la respuesta y cualquier error.
//
// El POST va al RUNTIME LOCAL (mismo origen), NO al Cloud → sin headers de auth. RUNTIME_URL
// se define aquí (igual que en lib/cloud.ts) y por defecto es "" = mismo origen (prod: el hub
// sirve el dist; dev: ruta relativa → proxy de Vite hacia :8787, sin CORS).
import type { App } from 'vue';

const RUNTIME_URL: string = (import.meta.env.VITE_RUNTIME_URL as string | undefined) || '';

/** Body del contrato. `module_id` se deja null: el shell no conoce el módulo activo aquí. */
interface ErrorReportBody {
  type: 'js_error';
  message: string;
  stack: string | null;
  url: string | null;
  component: string | null;
  module_id: string | null;
}

export interface ClientErrorInput {
  message: string;
  stack?: string | null;
  url?: string | null;
  component?: string | null;
}

// --- Throttle de errores idénticos -----------------------------------------
// Algunos errores se disparan en bucle (p. ej. un render roto). Guardamos una huella
// (message + primera línea del stack) → timestamp del último envío y saltamos si se repitió
// en los últimos WINDOW_MS. Capamos el tamaño del mapa para no crecer sin límite.
const WINDOW_MS = 30_000;
const MAX_FINGERPRINTS = 50;
const lastSent = new Map<string, number>();

// Evita bucles de reporte: si fallar el propio POST disparase un error capturado, no queremos
// reentrar. Mientras enviamos, marcamos esta bandera para que report() salga sin hacer nada.
let reporting = false;

function firstStackLine(stack: string | null | undefined): string {
  if (!stack) return '';
  const line = stack.split('\n').find((l) => l.trim().length > 0);
  return (line ?? '').trim();
}

function fingerprintOf(message: string, stack: string | null | undefined): string {
  return `${message}|${firstStackLine(stack)}`;
}

/** True si esta huella se envió hace menos de WINDOW_MS (→ saltar). Si no, la registra. */
function throttled(fingerprint: string): boolean {
  const now = Date.now();
  const prev = lastSent.get(fingerprint);
  if (prev !== undefined && now - prev < WINDOW_MS) return true;
  // Cap: si llegamos al tope, descartamos la entrada más vieja antes de añadir.
  if (lastSent.size >= MAX_FINGERPRINTS && !lastSent.has(fingerprint)) {
    const oldest = lastSent.keys().next().value;
    if (oldest !== undefined) lastSent.delete(oldest);
  }
  lastSent.set(fingerprint, now);
  return false;
}

/**
 * Envía un error del cliente al runtime local. 100% best-effort: nunca lanza, nunca espera de
 * forma que rompa al llamante, y no genera bucles de reporte. Throttlea errores idénticos.
 */
export function reportClientError(input: ClientErrorInput): void {
  if (reporting) return; // no reentrar desde un fallo del propio envío
  const message = (input.message || '').toString();
  if (!message) return;
  const stack = input.stack ?? null;

  if (throttled(fingerprintOf(message, stack))) return;

  const body: ErrorReportBody = {
    type: 'js_error',
    message,
    stack,
    url: input.url ?? (typeof window !== 'undefined' ? window.location.href : null),
    component: input.component ?? null,
    module_id: null,
  };

  reporting = true;
  try {
    // keepalive: el report sobrevive a una navegación/recarga (útil si el error la provoca).
    void fetch(`${RUNTIME_URL}/api/error-report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {
      /* best-effort: si el runtime no responde, lo ignoramos (no reintentamos, no reportamos) */
    });
  } catch {
    /* fetch puede lanzar de forma síncrona en casos raros: lo tragamos */
  } finally {
    reporting = false;
  }
}

/**
 * Engancha la captura automática de errores: errores globales no capturados, promesas
 * rechazadas sin manejar, y el errorHandler de Vue. Llamar una vez en el bootstrap.
 */
export function installErrorReporting(app: App): void {
  if (typeof window !== 'undefined') {
    window.addEventListener('error', (ev: ErrorEvent) => {
      reportClientError({
        message: ev.message || (ev.error instanceof Error ? ev.error.message : 'Unknown error'),
        stack: ev.error instanceof Error ? ev.error.stack ?? null : null,
        url: ev.filename || window.location.href,
      });
    });

    window.addEventListener('unhandledrejection', (ev: PromiseRejectionEvent) => {
      const reason = ev.reason as unknown;
      const isErr = reason instanceof Error;
      reportClientError({
        message: isErr ? reason.message : `Unhandled rejection: ${String(reason)}`,
        stack: isErr ? reason.stack ?? null : (reason as { stack?: string })?.stack ?? null,
      });
    });
  }

  // errorHandler de Vue: errores lanzados dentro de componentes (render, hooks, watchers…).
  // `info` describe el contexto (p. ej. "render function"); lo usamos como `component`.
  const prev = app.config.errorHandler;
  app.config.errorHandler = (err, instance, info) => {
    const e = err as unknown;
    const isErr = e instanceof Error;
    reportClientError({
      message: isErr ? e.message : String(e),
      stack: isErr ? e.stack ?? null : null,
      component: info || null,
    });
    // No tragamos la visibilidad en dev: re-encadenamos cualquier handler previo y, si no había,
    // lo volcamos a consola (comportamiento por defecto de Vue cuando no hay errorHandler).
    if (prev) prev(err, instance, info);
    else console.error(err);
  };
}

// La vía COLA de la puerta de impresión: encola un documento en el hub y devuelve LO QUE CONTESTÓ
// el runtime — no solo si lo aceptó (hub#1731).
//
// Por qué es un módulo y no cuatro líneas dentro de `main.ts`, que es donde estaba: la respuesta
// del runtime trae el dato que separa «sale tarde» de «no sale nunca» —cuántos equipos están dados
// de alta y reportando para la estación en la que ha caído el trabajo— y el cableado lo tiraba
// (`return body?.ok === true`). Con ese dato perdido, `via:'queue'` se leía igual que impreso y el
// TPV cobraba en silencio en un hub sin ninguna impresora. `main.ts` no tiene tests, así que la
// única línea que cruza la respuesta era también la única que nada podía cazar si se rompía: aquí
// sí tiene la suya.
import { RUNTIME_URL, runtimeHeaders } from './runtime';
import type { EnqueuePrintJob, QueuedJob } from './print';

/** Lo que se lee del cuerpo antes de fiarse de él: por el cable puede venir cualquier cosa. */
type WireBody = { ok?: unknown; liveHosts?: unknown } | null;

/**
 * Construye la función que la puerta usa para encolar. El `fetch` se inyecta para poder probarla;
 * el shell no pasa nada y usa el global.
 */
export function createEnqueuePrintJob(fetchImpl: typeof fetch = fetch): EnqueuePrintJob {
  return async function enqueuePrintJob(job): Promise<QueuedJob> {
    const res = await fetchImpl(`${RUNTIME_URL}/api/print/jobs`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...runtimeHeaders() },
      body: JSON.stringify({
        jobId: job.jobId,
        role: job.role,
        documentType: job.documentType,
        document: job.document,
        format: job.format ?? 'receipt',
      }),
    });
    // Cualquier cosa que no sea 200 → no encolado, y la puerta cae al navegador: una venta no se
    // cae por un problema de impresión.
    if (!res.ok) return { queued: false };
    const body = (await res.json().catch(() => null)) as WireBody;
    // `liveHosts` solo cuenta si vino como NÚMERO. Un runtime antiguo no manda la clave y un
    // cuerpo que no entendemos tampoco es una respuesta: las dos cosas son `undefined`, que NO es
    // «no hay nadie» (ver `PrintResult.awaitingHost`). Convertirlas en 0 pondría el aviso en todos
    // los tiques de un hub bien montado, y un aviso que sale siempre deja de leerse.
    const liveHosts = typeof body?.liveHosts === 'number' ? body.liveHosts : undefined;
    // 200 con ok:true → encolado (nuevo o duplicado, ambos éxito: la cola es idempotente).
    return { queued: body?.ok === true, liveHosts };
  };
}

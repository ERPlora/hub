// Reporte MANUAL de problemas: el botón «Reportar un problema» del menú de usuario abre un modal con
// un campo de mensaje y postea al MISMO embudo que el reporte automático (lib/error-report):
//   POST /api/error-report  { type:'user_report', message, url }
// El runtime local lo normaliza a un ErrorEvent{source:'frontend', error_code:'user_report'} y lo
// reenvía al Cloud (X-Hub-Token, la máquina nunca toca el navegador). Allí, al ser un error_code
// accionable con severity 'unexpected', ingest_error abre un issue de GitHub → el reporte llega al
// equipo sin tocar el runtime.
//
// Diferencias con el reporte automático (lib/error-report): lo dispara el usuario, lleva su texto,
// NO se throttlea (un envío explícito siempre sale, aunque el texto se repita) y devolvemos el
// resultado (true/false) para poder dar feedback (toast) en la UI. Best-effort: nunca lanza.
//
// El POST va al RUNTIME LOCAL (mismo origen), sin headers de auth. RUNTIME_URL por defecto "" =
// mismo origen (prod: el hub sirve el dist; dev: ruta relativa → proxy de Vite hacia :8787).
import { ref } from 'vue';

const RUNTIME_URL: string = (import.meta.env.VITE_RUNTIME_URL as string | undefined) || '';

/** Estado del modal de reporte (lo abre el ítem del menú de usuario en App.vue). */
export const reportProblemOpen = ref<boolean>(false);

export function openReportProblem(): void {
  reportProblemOpen.value = true;
}

export function closeReportProblem(): void {
  reportProblemOpen.value = false;
}

/**
 * Envía un reporte manual del usuario al runtime local (que lo reenvía al Cloud). Devuelve `true`
 * si el runtime aceptó el POST (2xx). Nunca lanza: un mensaje vacío o un fallo de red devuelven
 * `false` para que la UI muestre el toast de error.
 */
export async function reportUserProblem(message: string): Promise<boolean> {
  const text = (message || '').trim();
  if (!text) return false;

  const body = {
    type: 'user_report',
    message: text,
    url: typeof window !== 'undefined' ? window.location.href : null,
  };

  try {
    const res = await fetch(`${RUNTIME_URL}/api/error-report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.ok;
  } catch {
    // Best-effort: si el runtime no responde (offline), lo tratamos como fallo de envío.
    return false;
  }
}

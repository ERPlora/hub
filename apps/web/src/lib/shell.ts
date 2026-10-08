// Estado transversal del shell (topbar + sidebar), fuera de App.vue para que el AppTopbar
// compartido y el menú lo compartan sin prop-drilling. Reactivo con `ref`.
//
// Incluye:
//  - railCollapsed   → colapsar el menú lateral a "rail" (solo escritorio). El toggle vive en la
//    topbar compartida (AppTopbar), a la derecha del back, dando paridad con el shell de Cloud
//    (icono `panel-left`). El estado vive aquí porque lo tocan AppTopbar (botón) y App.vue
//    (clase `.rail` del split-pane).
//  - assistantOpen   → drawer del asistente (lo abre el botón sparkles de la topbar).
//  - assistantAvailable → ¿se muestra el botón del asistente? (capacidad del hub).
//  - inFlight        → contador de peticiones en vuelo → barra de progreso de la topbar.
//  - notifications   → STUB del contador de la campana (no hay señal de backend todavía).
import { computed, ref, watch } from 'vue';

// ── Rail (menú lateral colapsable) ──────────────────────────────────────────
export const railCollapsed = ref<boolean>(false);

// ── Panel del asistente ─────────────────────────────────────────────────────
// El asistente es un PANEL PERSISTENTE del shell (no un overlay que se cierra al navegar):
// al activarse se queda abierto en TODAS las páginas hasta que el usuario lo cierra. Por ser ref
// de módulo persiste entre rutas; además lo respaldamos en localStorage para sobrevivir al refresco
// (paridad con el Cloud). Clave `erplora.assistant.open`.
const ASSISTANT_OPEN_KEY = 'erplora.assistant.open';

function readAssistantOpen(): boolean {
  try {
    return localStorage.getItem(ASSISTANT_OPEN_KEY) === 'true';
  } catch {
    // localStorage puede no estar disponible (modo privado, SSR…): degrada a cerrado.
    return false;
  }
}

export const assistantOpen = ref<boolean>(readAssistantOpen());

// Persiste cada cambio del estado abierto en localStorage.
watch(assistantOpen, (open) => {
  try {
    localStorage.setItem(ASSISTANT_OPEN_KEY, open ? 'true' : 'false');
  } catch {
    // Ignorar fallos de escritura (cuota/modo privado): el estado en memoria sigue siendo válido.
  }
});

export function toggleAssistant(): void {
  assistantOpen.value = !assistantOpen.value;
}
export function closeAssistant(): void {
  assistantOpen.value = false;
}

// ── What the assistant was opened FOR ──────────────────────────────────────
// A screen opening the assistant says **what about**, never **what to say** (hub#373). It used to
// hand it a paragraph it had written itself out of a list kept beside the query, so the chat could
// describe a hub the checklist did not. The assistant reads `hub.setup.status` on its own; all that
// travels from the screen is the intent.
export interface AssistantIntent {
  /** What the chat opens on. Today the configuration checklist is the only topic. */
  topic: 'setup';
  /** `key` of the `hub.setup.status` item the user asked about; `null` = the whole checklist. */
  itemKey: string | null;
}

export const assistantIntent = ref<AssistantIntent | null>(null);

/** Opens the assistant on the hub's configuration, optionally loaded on one item of the checklist. */
export function openAssistantForSetup(itemKey: string | null = null): void {
  assistantIntent.value = { topic: 'setup', itemKey };
  assistantOpen.value = true;
}

/**
 * Closes the panel and drops what it was opened for (hub#2538). The panel and its setup mode belong
 * to the person who opened them: a hand-over or a sign-out must not leave the next person inside
 * the previous one's configuration chat.
 */
export function forgetAssistantPanel(): void {
  assistantIntent.value = null;
  assistantOpen.value = false;
}


// Capacidad del asistente: en ERPlora el asistente es una capacidad CORE del Hub (proxy al Cloud,
// ADR-0033), así que por defecto está disponible mientras haya sesión. Si en el futuro se quiere
// gatear por tier/config (`GET /api/v1/hub/device/assistant/config/`), basta con resolverlo aquí.
const _assistantAvailable = ref<boolean>(true);
export const assistantAvailable = computed<boolean>(() => _assistantAvailable.value);
export function setAssistantAvailable(v: boolean): void {
  _assistantAvailable.value = v;
}

// ── Barra de progreso (peticiones en vuelo) ─────────────────────────────────
// Contador incrementado/decrementado por lib/runtime y lib/cloud al envolver fetch (ver
// trackRequest). La topbar muestra la barra mientras inFlight > 0.
const _inFlight = ref<number>(0);
export const inFlight = computed<number>(() => _inFlight.value);
export const isLoading = computed<boolean>(() => _inFlight.value > 0);

/** Marca el inicio de una petición de red (para la barra de progreso). Emparejar con endRequest. */
export function beginRequest(): void {
  _inFlight.value++;
}
/** Marca el fin de una petición de red. */
export function endRequest(): void {
  _inFlight.value = Math.max(0, _inFlight.value - 1);
}

/** Envuelve una promesa de red para que cuente como "petición en vuelo" en la barra de progreso. */
export async function trackRequest<T>(p: Promise<T>): Promise<T> {
  beginRequest();
  try {
    return await p;
  } finally {
    endRequest();
  }
}

// ── Notificaciones ──────────────────────────────────────────────────────────
// Ya NO es un stub: la campana tiene señales reales de backend, y desde hub#987 son **dos**, así
// que el contador es la SUMA por fuente y no un número que el último en escribir pisa.
//
//   - `deadLetters` (hub#660) — un evento que murió y necesita a un admin.
//   - `printing`    (hub#987) — una estación con trabajo esperando y nadie drenándola.
//   - `modules`     (hub#1678) — what the installed modules declare in their `bell` block (an
//                   appointment to confirm…), summed by `lib/bell-counters.ts`.
//   - `moduleUpdates` (hub#1172) — installed apps with a newer version the owner can apply,
//                   counted by `lib/module-update-notice.ts`.
//
// Por fuente y no un total que cada watcher recalcula: los dos pollers corren a su ritmo y sin
// saber el uno del otro, así que el que refrescara segundo borraría al primero. Un hub con un
// evento muerto Y una caja apagada enseñaría «1» y escondería una de las dos.
//
// Son ESTADO derivado, no eventos con acuse: se curan solos al arreglar la causa y por eso no
// llevan leído/descartado (ADR-0067 — un ítem que no se puede descartar, en un feed hecho para
// descartar, enseña a ignorar la campana).
export type NotificationSource = 'deadLetters' | 'printing' | 'modules' | 'moduleUpdates';

const _notificationCounts = ref<Record<NotificationSource, number>>({
  deadLetters: 0,
  printing: 0,
  modules: 0,
  moduleUpdates: 0,
});

/** Lo que pinta el badge: el total de todas las fuentes. */
export const notificationCount = computed<number>(() =>
  Object.values(_notificationCounts.value).reduce((a, b) => a + b, 0),
);

/** Cuántas avisa una fuente concreta, para que el popover pinte su fila. */
export function notificationCountOf(source: NotificationSource): number {
  return _notificationCounts.value[source] ?? 0;
}

/**
 * Fija lo que aporta UNA fuente. El defecto es `deadLetters` porque era la única cuando esto
 * era un contador suelto, así que la llamada que ya existía sigue diciendo lo mismo.
 */
export function setNotificationCount(n: number, source: NotificationSource = 'deadLetters'): void {
  _notificationCounts.value = {
    ..._notificationCounts.value,
    [source]: Math.max(0, n),
  };
}

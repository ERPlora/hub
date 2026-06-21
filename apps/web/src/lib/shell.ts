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

// ── Notificaciones (STUB) ───────────────────────────────────────────────────
// TODO(stub): NO hay señal de backend de notificaciones todavía. Este contador es un PLACEHOLDER
// (arranca en 0 = sin badge). Cuando exista el endpoint/WS de notificaciones, alimentar este ref
// desde ahí (o reemplazarlo por un store dedicado). La campana de la topbar lee `notificationCount`.
const _notificationCount = ref<number>(0);
export const notificationCount = computed<number>(() => _notificationCount.value);
/** STUB: fija el contador de notificaciones (placeholder hasta que haya backend). */
export function setNotificationCount(n: number): void {
  _notificationCount.value = Math.max(0, n);
}

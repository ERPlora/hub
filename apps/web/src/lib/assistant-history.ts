// Historial del AED con alcance de SESIÓN (ADR-0149): el dueño del historial es el
// CLIENTE; el Cloud es un bridge sin estado de contenido (solo metering/proxy).
//
// sessionStorage (no localStorage): sobrevive un reload dentro de la misma pestaña/sesión
// y muere al cerrarla; además `logout()` (lib/session) lo vacía explícitamente. En cada
// turno el drawer envía el array COMPLETO al runtime (lib/assistant), que lo reenvía
// entero al Cloud — tras un reload el historial se restaura de aquí, nunca del Cloud.
import { ref } from 'vue';
import type { ChatMessage } from './assistant';

const SS_KEY = 'erplora.assistant.history';

function read(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(SS_KEY);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

/** Hilo vivo del chat (compartido por el drawer; el streaming muta el último mensaje in-place). */
export const assistantMessages = ref<ChatMessage[]>(read());

/** Persiste el estado acumulado (se llama al enviar y al cerrar cada stream, no por token). */
export function saveAssistantHistory(): void {
  try {
    sessionStorage.setItem(SS_KEY, JSON.stringify(assistantMessages.value));
  } catch {
    /* noop — quota/modo privado: el chat sigue en memoria */
  }
}

/** Vacía el historial (logout / fin de sesión). */
export function clearAssistantHistory(): void {
  assistantMessages.value = [];
  try {
    sessionStorage.removeItem(SS_KEY);
  } catch {
    /* noop */
  }
}

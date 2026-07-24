// @vitest-environment happy-dom
// Contrato del historial del AED (ADR-0149): el dueño del historial es el CLIENTE,
// con alcance de SESIÓN — el Cloud es un bridge sin estado de contenido.
//   - Los mensajes viven en el web app (sessionStorage): sobreviven un reload en la
//     misma pestaña/sesión…
//   - …y MUEREN al cerrar la sesión (logout los vacía).
//   - El streaming muta el último mensaje in-place (token a token); `save` persiste
//     el estado acumulado, no cada token.
import { describe, it, expect, beforeEach, vi } from 'vitest';

const SS_KEY = 'erplora.assistant.history';

// logout() importa dinámicamente cloud/entitlement (revocación server-side + reset del
// entitlement). Aquí solo interesa el contrato del historial: se mockean para no tocar red.
vi.mock('./cloud', () => ({
  runtimeLogout: vi.fn(),
  clearTokens: vi.fn(),
  getAccessToken: vi.fn(() => null),
}));
vi.mock('./entitlement', () => ({ resetEntitlement: vi.fn() }));
vi.mock('./user-profile', () => ({ resetUserProfile: vi.fn() }));
vi.mock('./theme', () => ({ resetUserThemePreferences: vi.fn() }));

async function freshStore() {
  // Simula un reload: módulo nuevo → re-lee sessionStorage en el import.
  vi.resetModules();
  return await import('./assistant-history');
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

describe('assistant-history (store de sesión del AED)', () => {
  it('empieza vacío cuando no hay nada persistido', async () => {
    const store = await freshStore();
    expect(store.assistantMessages.value).toEqual([]);
  });

  it('save persiste los mensajes en sessionStorage', async () => {
    const store = await freshStore();
    store.assistantMessages.value.push({ role: 'user', content: 'hola' });
    store.saveAssistantHistory();
    expect(JSON.parse(sessionStorage.getItem(SS_KEY)!)).toEqual([{ role: 'user', content: 'hola' }]);
  });

  it('un reload restaura el historial desde sessionStorage (no desde el Cloud)', async () => {
    const store = await freshStore();
    store.assistantMessages.value.push({ role: 'user', content: 'hola' });
    store.assistantMessages.value.push({ role: 'assistant', content: 'qué tal' });
    store.saveAssistantHistory();

    const reloaded = await freshStore();
    expect(reloaded.assistantMessages.value).toEqual([
      { role: 'user', content: 'hola' },
      { role: 'assistant', content: 'qué tal' },
    ]);
  });

  it('save captura las mutaciones in-place del streaming (token a token)', async () => {
    const store = await freshStore();
    const live = { role: 'assistant' as const, content: '' };
    store.assistantMessages.value.push(live);
    live.content += 'ho';
    live.content += 'la';
    store.saveAssistantHistory();
    expect(JSON.parse(sessionStorage.getItem(SS_KEY)!)).toEqual([{ role: 'assistant', content: 'hola' }]);
  });

  it('clear vacía el ref y borra la clave de sessionStorage', async () => {
    const store = await freshStore();
    store.assistantMessages.value.push({ role: 'user', content: 'hola' });
    store.saveAssistantHistory();

    store.clearAssistantHistory();
    expect(store.assistantMessages.value).toEqual([]);
    expect(sessionStorage.getItem(SS_KEY)).toBeNull();
  });

  it('storage roto (JSON inválido) degrada a historial vacío, sin lanzar', async () => {
    sessionStorage.setItem(SS_KEY, '{no-json');
    const store = await freshStore();
    expect(store.assistantMessages.value).toEqual([]);
  });

  it('logout() vacía el historial (muere con la sesión)', async () => {
    const store = await freshStore();
    store.assistantMessages.value.push({ role: 'user', content: 'secreto' });
    store.saveAssistantHistory();

    const session = await import('./session');
    session.logout();
    // El clear va por import dinámico dentro de logout() → esperar el microtask.
    await vi.waitFor(() => {
      expect(sessionStorage.getItem(SS_KEY)).toBeNull();
    });
  });
});

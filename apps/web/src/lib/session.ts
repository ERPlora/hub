// Sesión del shell (Vue-native, reemplaza el AuthProvider de React). Estado reactivo con `ref`
// + persistencia en localStorage (misma clave que el shell anterior). La lógica de login real
// contra el Cloud (cloud.ts) se cablea en `login()`. El estado de NEGOCIO vive en el runtime Rust.
import { computed, ref } from 'vue';

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string | null;
}

const LS_KEY = 'erplora.session';

function read(): SessionUser | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

const _user = ref<SessionUser | null>(read());

export const user = computed(() => _user.value);
export const isAuthed = computed(() => _user.value != null);

export function setUser(u: SessionUser | null): void {
  _user.value = u;
  try {
    if (u) localStorage.setItem(LS_KEY, JSON.stringify(u));
    else localStorage.removeItem(LS_KEY);
  } catch {
    /* noop */
  }
}

export function logout(): void {
  setUser(null);
  // Olvida el entitlement resuelto: el próximo login lo recalcula para el hub activo.
  void import('./entitlement').then((m) => m.resetEntitlement());
}

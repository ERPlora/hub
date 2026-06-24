// Sesión del shell (Vue-native, reemplaza el AuthProvider de React). Estado reactivo con `ref`
// + persistencia en localStorage (misma clave que el shell anterior). La lógica de login real
// contra el Cloud (cloud.ts) se cablea en `login()`. El estado de NEGOCIO vive en el runtime Rust.
import { computed, ref } from 'vue';

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  avatarUrl?: string | null;
  /**
   * Rol LOCAL del usuario en el hub, tal cual lo devuelve el runtime al hacer login
   * (`/api/auth/{pin,cloud}` → `user.role`). Es la MISMA fuente que usa el gate del backend; el
   * frontend solo lo refleja para mostrar/ocultar UI (la autoridad sigue siendo el runtime, que
   * revalida owner/admin en cada endpoint de gestión de keys). Opcional: las sesiones legacy /
   * el fallback demo no lo traen.
   */
  role?: string | null;
}

const LS_KEY = 'erplora.session';
// Token opaco de la **sesión server-side del runtime** (`X-Hub-Session`). Lo emite el runtime al
// hacer login (PIN o JWT cloud → `/api/auth/{pin,cloud}`) y el frontend lo manda en cada query/
// command. Es la autoridad de permisos LOCAL (ARQUITECTURA.md §2.9); el JWT cloud es solo el
// adaptador de login. Distinto del JWT del usuario (ese vive en cloud.ts para hablar con el Cloud).
const HUB_SESSION_KEY = 'erplora.hub_session';

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

/**
 * ¿El usuario actual gestiona usuarios/keys (owner o admin)? Espejo EXACTO del gate del backend
 * (`is_admin_role` en `crates/server/src/auth.rs`: owner/admin, insensible a mayúsculas). Solo para
 * mostrar/ocultar UI admin (pestaña «API keys»); el runtime revalida el rol en cada endpoint.
 */
export const isAdmin = computed(() => {
  const role = _user.value?.role?.toLowerCase();
  return role === 'owner' || role === 'admin';
});

export function setUser(u: SessionUser | null): void {
  _user.value = u;
  try {
    if (u) localStorage.setItem(LS_KEY, JSON.stringify(u));
    else localStorage.removeItem(LS_KEY);
  } catch {
    /* noop */
  }
}

/** Token de la sesión server-side del runtime (`X-Hub-Session`), o null si no hay sesión local. */
export function getHubSession(): string | null {
  try {
    return localStorage.getItem(HUB_SESSION_KEY);
  } catch {
    return null;
  }
}

/** Guarda (o borra) el token de sesión del runtime emitido por `/api/auth/{pin,cloud}`. */
export function setHubSession(token: string | null): void {
  try {
    if (token) localStorage.setItem(HUB_SESSION_KEY, token);
    else localStorage.removeItem(HUB_SESSION_KEY);
  } catch {
    /* noop */
  }
}

export function logout(): void {
  // Revoca la sesión server-side del runtime ANTES de borrar el token local (best-effort).
  const token = getHubSession();
  if (token) void import('./cloud').then((m) => m.runtimeLogout(token));
  setUser(null);
  setHubSession(null);
  // Olvida el entitlement resuelto: el próximo login lo recalcula para el hub activo.
  void import('./entitlement').then((m) => m.resetEntitlement());
}

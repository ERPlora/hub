// Sesión del shell (Vue-native, reemplaza el AuthProvider de React). Estado reactivo con `ref`
// + persistencia en localStorage (misma clave que el shell anterior). La lógica de login real
// contra el Cloud (cloud.ts) se cablea en `login()`. El estado de NEGOCIO vive en el runtime Rust.
import { computed, ref } from 'vue';

export interface SessionUser {
  id: string;
  cloudUserId?: string | null;
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
  /** Permisos efectivos del rol, resueltos por el runtime. Solo gobiernan visibilidad de UI. */
  permissions?: string[];
}

const LS_KEY = 'erplora.session';
// Token opaco de la **sesión server-side del runtime** (`X-Hub-Session`). Lo emite el runtime al
// hacer login (PIN o JWT cloud → `/api/auth/{pin,cloud}`) y el frontend lo manda en cada query/
// command. Es la autoridad de permisos LOCAL (ARQUITECTURA.md §2.9); el JWT cloud es solo el
// adaptador de login. Distinto del JWT del usuario (ese vive en cloud.ts para hablar con el Cloud).
const HUB_SESSION_KEY = 'erplora.hub_session';
// **Con qué se probó la identidad** de esa misma sesión (`hub_session.credential_kind`, hub#658).
// Vive AQUÍ y no en `SessionUser` a propósito: es una propiedad de la SESIÓN, no de la persona, y
// `applyProfile` reconstruye el usuario entero cada vez que se lee `/api/profile` — un campo
// aparcado ahí se borraría solo al primer refresco y la puerta a erplora.com desaparecería a los
// segundos de aparecer (hub#1400).
const HUB_SESSION_CREDENTIAL_KEY = 'erplora.hub_session_credential';

function read(): SessionUser | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

const _user = ref<SessionUser | null>(read());

function readCredentialKind(): string {
  try {
    return localStorage.getItem(HUB_SESSION_CREDENTIAL_KEY) ?? '';
  } catch {
    return '';
  }
}

// Reactivo, no una lectura de `localStorage` cuando alguien pregunta: `canOpenManagement` es un
// `computed` sobre esto, y un getter plano lo dejaría congelado en lo que fuera cierto al cargar el
// módulo — en un arranque en frío, antes de que nadie haya entrado.
const _hubSessionCredential = ref<string>(readCredentialKind());

/** El login **cloud**: email y contraseña contra el SaaS (`identity::CREDENTIAL_CLOUD`). */
export const CREDENTIAL_CLOUD = 'cloud';

/**
 * ¿La sesión activa se abrió tecleando email y contraseña?
 *
 * El cerrojo de hub#1400: solo a esa sesión se le entrega una del SaaS en el navegador. Un PIN es
 * credencial de **turno** —corta y tecleada delante de gente— y ADR-0226 ya dice que la credencial
 * del usuario local no es nunca administrativa.
 *
 * **Falla cerrado**: si la sesión no dice cómo se abrió (una anterior a este despliegue), la
 * respuesta es «no». «No consta» y «fue una contraseña» son respuestas distintas, y confundirlas
 * abriría la puerta justo a las sesiones que este cerrojo existe para dejar fuera. Se cura solo
 * cuando esa sesión caduca. La autoridad sigue siendo el runtime, que revalida en `/api/auth/handoff`.
 */
export const openedWithCloudLogin = computed(() => _hubSessionCredential.value === CREDENTIAL_CLOUD);

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

/**
 * El comodín que el shell inyecta a las sesiones owner/admin (`lib/runtime.ts`).
 *
 * Una sola definición del símbolo, para que «¿esta sesión puede X?» se responda en un solo sitio
 * y no en N copias que ninguna sabe de las otras (hub#506). El runtime del backend concede `*`
 * a los mismos roles que `is_admin_role` acepta; el frontend solo lo refleja para pintar UI.
 */
export const ALL_PERMISSIONS = '*';

/**
 * La regla del comodín, desacoplada de la sesión reactiva.
 *
 * Existe por separado para que las funciones puras (p. ej. `mayAdminister`, usada en tests con
 * permisos concretos) compartan exactamente la misma regla que las que leen la sesión global.
 * Antes eran copias independientes en `management-link.ts`, `app-update.ts`, `blueprint-hero.ts`
 * y `runtime.ts` — ninguna sabía de las otras.
 */
export function permissionsInclude(
  granted: readonly string[] | undefined,
  permission: string,
): boolean {
  return !!granted?.some((p) => p === ALL_PERMISSIONS || p === permission);
}

/**
 * ¿La sesión actual tiene `permission`, contando el comodín?
 *
 * Es un FILTRO de UI, no un gate: el runtime revalida el permiso real en cada endpoint.
 */
export function hasPermission(permission: string): boolean {
  return permissionsInclude(_user.value?.permissions, permission);
}

export function setUser(u: SessionUser | null): void {
  _user.value = u;
  try {
    if (u) {
      // Un object URL (`blob:`) solo vive durante esta carga. Se usa en el estado reactivo, pero
      // no se persiste como si fuera una URL válida para la próxima sesión.
      const persisted = {
        ...u,
        avatarUrl: u.avatarUrl?.startsWith('blob:') ? null : u.avatarUrl,
      };
      localStorage.setItem(LS_KEY, JSON.stringify(persisted));
    }
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

/**
 * Guarda (o borra) el token de sesión del runtime emitido por `/api/auth/{pin,cloud,badge,courier}`.
 *
 * `credentialKind` es lo que ese login contestó en `credential_kind` (hub#1400). Es opcional para
 * que un camino que se olvide de pasarlo deje la sesión **cerrada** en vez de abierta: omitirlo no
 * es «fue una contraseña», es «no consta».
 */
export function setHubSession(token: string | null, credentialKind?: string | null): void {
  const kind = token ? (credentialKind ?? '') : '';
  _hubSessionCredential.value = kind;
  try {
    if (token) localStorage.setItem(HUB_SESSION_KEY, token);
    else localStorage.removeItem(HUB_SESSION_KEY);
    if (kind) localStorage.setItem(HUB_SESSION_CREDENTIAL_KEY, kind);
    else localStorage.removeItem(HUB_SESSION_CREDENTIAL_KEY);
  } catch {
    /* noop */
  }
  // Pide la cookie con la que el NAVEGADOR pide las fotos (hub#791). Va aquí, y no en cada pantalla
  // de login, porque los cinco caminos que abren sesión —pinpad, login cloud, invitación, courier y
  // cambio de usuario— ya pasan todos por aquí; cablearlo en cada uno significa que el sexto que se
  // escriba entregue un TPV con las baldosas en blanco y nada que apunte al motivo.
  //
  // Suelto y tragándose el fallo, igual que los apagados de `shutDown`: entrar no puede fallar
  // porque no se haya podido traer una credencial de fotos. Sin cookie se pierden las fotos —y la
  // baldosa ya cae a sus iniciales (sales#104)—, no la sesión.
  if (token) {
    const runtime = import('./runtime');
    void runtime
      .then((m) => m.ensureMediaCookie())
      .catch(() => {
        /* noop: ni el chunk que no llega ni la puerta que rechaza cancelan un login */
      });
    // Re-seeds the ACTIVE module set the SDK's `queryOptional` short-circuit reads (hub#1211). The
    // first seed runs when `main.ts` builds the client — on a cold boot that is BEFORE there is a
    // session, so it asks nothing; and login is a route change, not a reload, so without this the
    // set would stay "not known" for the whole session and the fix would be inert for real users.
    // An independent chain on purpose: this failing must not cost the photos, nor the other way.
    void runtime
      .then((m) => m.refreshActiveModuleIds())
      .catch(() => {
        /* noop: without the set the SDK keeps asking the transport, exactly as before hub#1211 */
      });
  }
}

/**
 * Apaga un subsistema al cerrar sesión, **sin esperarlo y sin dejar el rechazo suelto**.
 *
 * Cerrar sesión no puede quedarse colgado de que cargue un chunk, así que estos `import()` van
 * sueltos a propósito. Lo que no puede quedar suelto es su RECHAZO: un chunk que no llega (red
 * caída a mitad de un deploy; en los tests, el entorno desmontado antes de que resuelva) dejaba una
 * promesa rechazada sin dueño. No rompía nada visible —ningún test fallaba— pero `vitest run`
 * terminaba con código 1 por un `EnvironmentTeardownError` que no era de nadie.
 *
 * Se traga con comentario porque aquí NO hay remedio: si el módulo no carga, tampoco hay a quién
 * decírselo, y cada apagado es idempotente y protegido por su propia guarda de sesión (el sondeo de
 * dead-letters, por ejemplo, ya no hace nada sin `isAuthed`).
 */
function shutDown<T>(load: Promise<T>, apply: (m: T) => void): void {
  void load.then(apply).catch(() => {
    /* noop: ver la doc de arriba */
  });
}

export function logout(): void {
  // Revoca la sesión server-side del runtime ANTES de borrar el token local (best-effort).
  const token = getHubSession();
  if (token) shutDown(import('./cloud'), (m) => m.runtimeLogout(token));
  setUser(null);
  setHubSession(null);
  shutDown(import('./cloud'), (m) => m.clearTokens());
  shutDown(import('./user-profile'), (m) => m.resetUserProfile());
  shutDown(import('./theme'), (m) => m.resetUserThemePreferences());
  shutDown(import('../i18n'), (m) => m.resetUserLocale());
  // Olvida el entitlement resuelto: el próximo login lo recalcula para el hub activo.
  shutDown(import('./entitlement'), (m) => m.resetEntitlement());
  // El historial del AED muere con la sesión (ADR-0149): el Cloud ya no guarda copia.
  shutDown(import('./assistant-history'), (m) => m.clearAssistantHistory());
  // La campana de dead-letters deja de sondear y se limpia (hub#660): sin sesión no hay cola que
  // mirar, y el badge no debe sobrevivir al logout.
  shutDown(import('./dead-letter'), (m) => m.stopDeadLetterWatch());
}

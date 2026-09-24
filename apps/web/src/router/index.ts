import { createRouter, createWebHistory } from '@ionic/vue-router';
import type { RouteLocationNormalized, RouteLocationRaw, RouteRecordRaw } from 'vue-router';
import { courierBootPending, takeShellCourierCode } from '../lib/courier';
import { isAuthed, logout } from '../lib/session';
import { isModuleBlocked, isModuleEntitled, needsActivation } from '../lib/entitlement';
import { apiDocsEnabled } from '../lib/api-docs';
import { machineRegistrationRequired } from '../lib/runtime';
import { reportClientError } from '../lib/error-report';
import { toastError } from '../lib/toast';
import { i18n } from '../i18n';
import { showViewLoadFailure } from './view-load-failure-notice';
import { installSystemBackButton } from './back-closes-overlay';
import { browserRecoveryStorage, clearViewLoadRecovery, recoverFromViewLoadError } from './view-load-recovery';

// Rutas del Hub (port de HubShell.tsx). Cada vista es un SFC Vue cargado de forma diferida.
// `/m/:moduleId` monta el Web Component (Lit) del módulo en runtime (ModuleView).
export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginPage.vue') },
  // Callback del OAuth de Google del SaaS (ADR-0157 §8): el SaaS redirige aquí con un `?code=` de
  // un solo uso; LoginPage lo canjea (`session-exchange`) y finaliza el login. Reusa LoginPage
  // (mismo flujo de finalización); no lleva `meta.auth` (aún no hay sesión) y el gate de registro
  // de máquina lo deja pasar igual que a `/login`.
  { path: '/auth/google/callback', name: 'google-callback', component: () => import('../views/LoginPage.vue') },
  // The active tab of the secondary tabbar lives in the HASH (#permissions), not in the path:
  // the base route does NOT change → Ionic does not treat a tab switch as navigating to a
  // secondary page (the tabbar is not unmounted and no back button appears). Deep link: /settings#permissions.
  { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardPage.vue'), meta: { auth: true } },
  { path: '/employees/new', name: 'employee-new', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/employees/:id', name: 'employee-edit', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/employees', name: 'employees', component: () => import('../views/EmployeesPage.vue'), meta: { auth: true } },
  { path: '/files', name: 'files', component: () => import('../views/FilesPage.vue'), meta: { auth: true } },
  // Perfil PERSONAL del usuario activo. No forma parte de /settings: los ajustes pertenecen al
  // Hub/negocio actual, mientras que esta pantalla solo refleja identidad y preferencias propias.
  { path: '/profile', name: 'profile', component: () => import('../views/ProfilePage.vue'), meta: { auth: true } },
  { path: '/billing', name: 'billing', component: () => import('../views/BillingPage.vue'), meta: { auth: true } },
  { path: '/apps', name: 'apps', component: () => import('../views/AppsPage.vue'), meta: { auth: true } },
  // Compat: la tienda se llamaba "Marketplace"; los enlaces/bookmarks viejos siguen funcionando.
  { path: '/marketplace', redirect: '/apps' },
  { path: '/system', name: 'system', component: () => import('../views/SystemPage.vue'), meta: { auth: true } },
  // Hub export/import (ADR-0113): they live TOGETHER in the Data tab of Ajustes
  // (/settings#data, decided 2026-07-12 — they used to be the /export and /import pages).
  // El gate admin REAL es del runtime (require_admin_session, como PUT /api/settings).
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsPage.vue'), meta: { auth: true } },
  // Documentación de la API pública (ADR-0057 §4): vista Vue interna que renderiza Swagger sobre el
  // spec del runtime. Visible a cualquier usuario logueado; la entrada de menú/página la habilita
  // el toggle de Ajustes (apiDocsEnabled). Acceso por URL directa también gateado abajo.
  { path: '/api-docs', name: 'api-docs', component: () => import('../views/ApiDocsPage.vue'), meta: { auth: true } },
  // `:navId?` = pestaña del tabbar secundario (entrada de `navigation[]` del manifest);
  // sin él, ModuleView abre la primera. Deep-link: /m/inventory/products.
  { path: '/m/:moduleId/:navId?', name: 'module', component: () => import('../views/ModuleView.vue'), meta: { auth: true } },
  // Pantalla de activación: hay sesión pero el hub no tiene un entitlement válido (§2.10).
  { path: '/activation', name: 'activation', component: () => import('../views/ActivationPage.vue'), meta: { auth: true } },
  // The RETIRED routes keep their destination, one by one. They used to live off the catch-all
  // below while it led to Home; now that it answers 404 (hub#1723), the explicit redirect is the
  // only thing that keeps three addresses that used to work from breaking. `/export` and
  // `/import` are the pages ADR-0113/0116 moved INTO Settings → Data, so that is where they go —
  // not Home, which was merely where the catch-all dropped them.
  { path: '/export', redirect: '/settings#data' },
  { path: '/import', redirect: '/settings#data' },
  // And setting up lives on Home today (core widget + Data tab); retired on 12/07.
  { path: '/first-run', redirect: '/dashboard' },
  // Catch-all: an address this hub does NOT have SAYS so (hub#1723). It used to redirect to
  // /dashboard, and a redirect is silent by definition — it rewrites the address bar, so it
  // destroys on the way in the evidence that the link was wrong: whoever pasted `/tpv` or `/sales`
  // saw Home with its menu and believed they were where they had asked for. It is a `component`
  // and not a `redirect` precisely so the requested address STAYS in the bar and the typo can be
  // read back.
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFoundPage.vue'),
    // Behind a session, like the rest of the shell: a stranger with a broken link keeps seeing the
    // login screen and not the hub's chrome, exactly as today.
    meta: { auth: true },
  },
];

// DO NOT MOVE THIS BELOW `createWebHistory()` — it is the whole fix for hub#755.
//
// The SaaS hands the shell its one-time courier in the fragment (`/?shell=1#courier=…`). The
// history built on the next line snapshots `window.location` as it is RIGHT NOW and replays that
// snapshot as the initial navigation, so a fragment still present here is a credential the router
// will faithfully write back into the address bar — which is exactly what QA read back on Android
// seconds after `forget_hub`. Worse, an unauthenticated boot then carries it into
// `/login?redirect=…%23courier%3D…`, and a query string, unlike a fragment, is sent to the server.
//
// Scrubbing here is the earliest moment that exists: `main.ts` imports this module, and ES imports
// are evaluated before the importing module's body, so nothing written in `main.ts` can run sooner.
// Idempotent, so `main.ts` still gets the code it needs for the exchange.
takeShellCourierCode();

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

// hub#1906 — Android's Back button closes the sheet/modal/menu on top before it leaves the screen.
// It takes the button itself and never cancels a navigation: see `installSystemBackButton`.
void installSystemBackButton();

/**
 * Auth-gate: rutas con `meta.auth` requieren sesión; si no, a `/login`. (Vue-router nativo.)
 *
 * **Es `async` por una razón (hub#858).** `main.ts` instala el router al evaluar el módulo, así que
 * la navegación inicial arranca ANTES de que el canje del courier del shell (dos viajes de red)
 * pueda terminar. Este gate contestaba entonces «sin sesión → /login» y nadie volvía a navegar: el
 * courier abría la sesión un instante después y el usuario acababa viendo un formulario de login
 * dentro de un shell ya autenticado —el doble login del alta—. Esperar a que el canje **se
 * resuelva** (con éxito o no) es lo que convierte el salto SaaS→hub en un solo inicio de sesión.
 *
 * Exportado para que el contrato se pueda probar sin montar la app (`auth-gate.test.ts`).
 */
export async function authGate(to: RouteLocationNormalized): Promise<true | RouteLocationRaw> {
  // Un courier en vuelo: no se decide nada hasta que exista (o se descarte) la sesión que trae.
  // `null` es el caso normal —navegador corriente, y toda navegación posterior a la primera—, así
  // que esto no añade espera a nadie más.
  await courierBootPending();
  // Compat legacy: las tabs antes iban en query (?tab=) y ahora van en el HASH (#permisos).
  // Redirige el query viejo al hash para no romper bookmarks/enlaces antiguos.
  const legacyTab = to.query.tab;
  if (typeof legacyTab === 'string' && legacyTab && !to.hash) {
    return { path: to.path, query: {}, hash: `#${legacyTab}` };
  }
  // Bootstrap obligatorio: una instalación real sin UUID+credencial Cloud no puede resucitar una
  // sesión local persistida ni entrar por URL directa. Demo llega con este flag a false.
  if (machineRegistrationRequired.value) {
    if (isAuthed.value) logout();
    // El callback de Google (ADR-0157 §8) se trata como el login: debe poder canjear su `?code=`
    // aunque el hub aún no esté registrado (Hub Cloud llega provisionado; el gate no aplica).
    if (to.name !== 'login' && to.name !== 'google-callback') {
      return { name: 'login', query: { redirect: to.fullPath } };
    }
  }
  if (to.meta.auth && !isAuthed.value) {
    return { name: 'login', query: { redirect: to.fullPath } };
  }
  if (to.name === 'login' && isAuthed.value) {
    return { path: '/' };
  }
  // Entitlement-gate (§2.10): sin entitlement válido, el negocio se redirige a /activation.
  if (isAuthed.value && needsActivation.value && to.meta.auth && to.name !== 'activation') {
    return { name: 'activation' };
  }
  // Si ya hay entitlement válido, no tiene sentido quedarse en /activation.
  if (to.name === 'activation' && !needsActivation.value) {
    return { path: '/' };
  }
  // (Retirado) El desvío a /first-run para hubs sin módulos: la puesta en marcha vive AHORA en
  // core — pestaña Datos de Ajustes (import/export, ADR-0113/0116) + el widget del dashboard.
  // Un hub vacío entra directo al dashboard y configura desde ahí si lo necesita.
  // Un módulo concreto solo se monta si el hub tiene derecho (acceso por URL directa).
  if (to.name === 'module' && !isModuleEntitled(String(to.params.moduleId))) {
    // hub#1175: `!isModuleEntitled` used to lump TWO different reasons under the same silent
    // bounce. A module the hybrid revalidation names BLOCKED (`isModuleBlocked`, ADR-0114 §6) is
    // still installed and holds data — it only stopped being paid, or the marketplace retired it
    // (hub#1175: `invoice_series`, which never even required payment) — and `ModuleView` ALREADY
    // knows how to paint that case: the `blocked-card` explains why, the same notice a module
    // blocked for non-payment gets. Letting it MOUNT is letting that screen exist, not a new
    // permission: the dispatcher still refuses its queries/commands with 402 exactly as before.
    if (isModuleBlocked(String(to.params.moduleId))) {
      return true;
    }
    // The other half: an id the entitlement never named at all (a typo, a stale bookmark, a
    // module this hub never installed). There is no screen to mount for that — but the bounce is
    // no longer silent.
    const [{ toastInfo }, { i18n }] = await Promise.all([import('../lib/toast'), import('../i18n')]);
    void toastInfo(i18n.global.t('moduleView.notAvailableToast'));
    return { name: 'dashboard' };
  }
  // La doc de la API solo es navegable con el toggle de Ajustes activo (también por URL directa).
  if (to.name === 'api-docs' && !apiDocsEnabled.value) {
    return { name: 'dashboard' };
  }
  return true;
}

router.beforeEach(authGate);

/**
 * hub#1518 — a screen whose code never arrives must not leave the hub blank.
 *
 * Every view is loaded on demand, so opening a screen is a network fetch that can die (the till
 * hops wifi→4G, a chunk went stale after a deploy, the CI runner's network blinks). On the FIRST
 * navigation that failure is fatal and mute: `main.ts` mounts inside `router.isReady().then(...)`,
 * so nothing ever mounts — a white page with no message and no way out.
 *
 * The ladder, and why retrying the `import()` in place cannot work, live in
 * `./view-load-recovery`; the last-rung message in `./view-load-failure-notice`.
 *
 * hub#1524 — the same white page has a second cause: the screen's own code throwing. That one gets
 * no ladder (a reload lands on the identical code) but it does get the message, because a person
 * staring at nothing is the defect, not the reason behind it.
 */
router.onError((error, to, from) => {
  // An empty `matched` is START_LOCATION: the document has not painted any route yet, which is the
  // only case where aborting the navigation leaves the person looking at nothing.
  const isInitial = from.matched.length === 0;
  const outcome = recoverFromViewLoadError(
    error,
    { toPath: to.fullPath, isInitial },
    // A DOCUMENT reload, not `location.assign(to.fullPath)`: on the first navigation the tab is
    // already AT `to` (the router replays `window.location`), and assigning the URL a document
    // already has, differing at most in its fragment, is a fragment navigation per the HTML spec —
    // nothing reloads. The e2e that found this lands on `/settings#data`: measured in Chromium,
    // `assign('/settings#data')` = 1 document load (still blank), `reload()` = 2.
    { storage: browserRecoveryStorage(), reload: () => window.location.reload() },
  );
  // Reloaded once already (or the mark cannot be stored, which would loop): say it in the DOM,
  // because there is no Vue, no Ionic and no toast to say it with.
  if (outcome === 'exhausted') showViewLoadFailure();
  // App already open: it keeps the screen — and whatever was half-typed on it — and hears why.
  if (outcome === 'notify') void toastError(i18n.global.t('viewLoad.failedToast'));
  // Registering ANY error listener switches off vue-router's own `console.error`. Anything we did
  // not recognise as a missing file is a bug in the view itself and has to stay exactly as loud.
  if (outcome === 'ignored') {
    console.error(error);
    // hub#1524 — and on the FIRST navigation that bug leaves the very same white page hub#1518
    // was about: nothing is mounted, so the console is the only place it was ever said, and the
    // console is not where the person at the till is looking. Same wall of text, its OWN words
    // (`kind: 'code'`): the connection is fine and blaming it would send them to reboot a router.
    //
    // No recovery rung here on purpose. A reload of a code failure comes back to the identical
    // code, so retrying it automatically is a boot loop with a shop waiting behind it; the only
    // retry offered is the button, which a person presses knowing what they are doing.
    if (isInitial) showViewLoadFailure({ kind: 'code' });
    // hub#1590 — and with the app ALREADY open the very same bug was mute: the router aborts, the
    // screen simply does not change, and the console is not where the person at the till is
    // looking. A tap that does nothing reads as a dead button, so they tap it again.
    //
    // A toast and not the wall of text, because here nothing is blank: covering a live till would
    // lose sight of the order being taken. Its OWN copy, never `failedToast` — that one says the
    // connection dropped, which here is a lie that sends them to reboot a working router.
    else void toastError(i18n.global.t('viewLoad.brokenToast'));
  }
  // A navigation that fails without a trace is a failure nobody sees: all four rungs report it.
  // `reportClientError` posts with `keepalive`, so it survives the reload of the first rung.
  reportClientError({
    message: `router.onError[${outcome}] ${error instanceof Error ? error.message : String(error)}`,
    stack: error instanceof Error ? error.stack : null,
    component: 'router',
  });
});

// A navigation that lands forgets the mark, so a network hiccup later on can still recover.
router.afterEach(() => clearViewLoadRecovery(browserRecoveryStorage()));

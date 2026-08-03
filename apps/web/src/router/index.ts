import { createRouter, createWebHistory } from '@ionic/vue-router';
import type { RouteRecordRaw } from 'vue-router';
import { isAuthed, logout } from '../lib/session';
import { isModuleEntitled, needsActivation } from '../lib/entitlement';
import { apiDocsEnabled } from '../lib/api-docs';
import { machineRegistrationRequired } from '../lib/runtime';

// Rutas del Hub (port de HubShell.tsx). Cada vista es un SFC Vue cargado de forma diferida.
// `/m/:moduleId` monta el Web Component (Lit) del módulo en runtime (ModuleView).
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginPage.vue') },
  // Callback público del login con Google (#945): el Cloud redirige aquí con ?code=.
  // Debe ir ANTES del catch-all (que si no traga la ruta → /dashboard → /login).
  // Sin meta.auth: el bootstrap de sesión ocurre DENTRO de la vista.
  { path: '/auth/google/callback', name: 'google-callback', component: () => import('../views/GoogleCallbackPage.vue') },
  // La pestaña activa del tabbar secundario va en el HASH (#permisos) en vez de en el path:
  // así la ruta base NO cambia → Ionic no trata el cambio de pestaña como navegación a una
  // página secundaria (no se desmonta el tabbar ni aparece el botón back). Deep-link: /settings#permisos.
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
  // Export/Import del hub (ADR-0113): viven JUNTOS en la pestaña Datos de Ajustes
  // (/settings#datos, decisión del humano 2026-07-12 — antes eran las páginas /export y /import).
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
  // Catch-all: cualquier ruta desconocida (incl. las retiradas /export y /import → ahora en
  // Ajustes → Datos, ADR-0116, y la retirada /first-run) cae al inicio en vez de dejar el
  // outlet en blanco.
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
];

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

// Auth-gate: rutas con meta.auth requieren sesión; si no, a /login. (Vue-router nativo, sin React.)
router.beforeEach((to) => {
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
    if (to.name !== 'login') {
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
    return { name: 'dashboard' };
  }
  // La doc de la API solo es navegable con el toggle de Ajustes activo (también por URL directa).
  if (to.name === 'api-docs' && !apiDocsEnabled.value) {
    return { name: 'dashboard' };
  }
  return true;
});

import { createRouter, createWebHistory } from '@ionic/vue-router';
import type { RouteRecordRaw } from 'vue-router';
import { isAuthed } from '../lib/session';
import { isModuleEntitled, needsActivation } from '../lib/entitlement';
import { apiDocsEnabled } from '../lib/api-docs';
import { ensureInstalledModules, needsFirstRun } from '../lib/nav';

// Rutas del Hub (port de HubShell.tsx). Cada vista es un SFC Vue cargado de forma diferida.
// `/m/:moduleId` monta el Web Component (Lit) del módulo en runtime (ModuleView).
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginPage.vue') },
  { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardPage.vue'), meta: { auth: true } },
  { path: '/employees', name: 'employees', component: () => import('../views/EmployeesPage.vue'), meta: { auth: true } },
  { path: '/employees/new', name: 'employee-new', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/employees/:id', name: 'employee-edit', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/files', name: 'files', component: () => import('../views/FilesPage.vue'), meta: { auth: true } },
  { path: '/billing', name: 'billing', component: () => import('../views/BillingPage.vue'), meta: { auth: true } },
  { path: '/apps', name: 'apps', component: () => import('../views/AppsPage.vue'), meta: { auth: true } },
  // Compat: la tienda se llamaba "Marketplace"; los enlaces/bookmarks viejos siguen funcionando.
  { path: '/marketplace', redirect: '/apps' },
  { path: '/system', name: 'system', component: () => import('../views/SystemPage.vue'), meta: { auth: true } },
  // Export/Import del hub (ADR-0113): viven JUNTOS en la pestaña Datos de Ajustes
  // (/settings?tab=data, decisión del humano 2026-07-12 — antes eran las páginas /export y
  // /import). El gate admin REAL es del runtime (require_admin_session, como PUT /api/settings).
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
  // Primer arranque: el hub se despliega vacío (ADR-0087) y sin esto aterriza en un dashboard en
  // blanco. Empuja a importar una plantilla (Ajustes → Datos, ADR-0113) o al marketplace.
  { path: '/first-run', name: 'first-run', component: () => import('../views/FirstRunPage.vue'), meta: { auth: true } },
  // Catch-all: cualquier ruta desconocida (incl. las retiradas /export y /import → ahora en
  // Ajustes → Datos, ADR-0116) cae al inicio en vez de dejar el outlet en blanco.
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
];

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

// Auth-gate: rutas con meta.auth requieren sesión; si no, a /login. (Vue-router nativo, sin React.)
router.beforeEach(async (to) => {
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
  // Primer arranque: un hub sin módulos aterrizaría en un dashboard vacío. Hay que ESPERAR a saber
  // qué hay instalado (`/api/modules`), o decidiríamos sin la respuesta. Apps y ajustes
  // quedan accesibles: la pantalla empuja, no encierra — y el hub vacío es precisamente el que
  // necesita el import (pestaña Datos de Ajustes: restaurar un backup / plantilla, ADR-0113).
  if (isAuthed.value && to.meta.auth) {
    await ensureInstalledModules();
    const escapes = ['first-run', 'apps', 'settings'];
    if (needsFirstRun.value && !escapes.includes(String(to.name))) {
      return { name: 'first-run' };
    }
  }
  // Con módulos instalados, la pantalla de primer arranque ya no pinta nada.
  if (to.name === 'first-run' && !needsFirstRun.value) {
    return { path: '/' };
  }
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

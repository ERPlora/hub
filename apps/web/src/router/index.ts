import { createRouter, createWebHistory } from '@ionic/vue-router';
import type { RouteRecordRaw } from 'vue-router';
import { isAuthed } from '../lib/session';
import { isModuleEntitled, needsActivation } from '../lib/entitlement';

// Rutas del Hub (port de HubShell.tsx). Cada vista es un SFC Vue cargado de forma diferida.
// `/m/:moduleId` monta el Web Component (Lit) del módulo en runtime (ModuleView).
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  { path: '/login', name: 'login', component: () => import('../views/LoginPage.vue') },
  { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardPage.vue'), meta: { auth: true } },
  { path: '/employees', name: 'employees', component: () => import('../views/EmployeesPage.vue'), meta: { auth: true } },
  { path: '/employees/new', name: 'employee-new', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/employees/:id', name: 'employee-edit', component: () => import('../views/EmployeeFormPage.vue'), meta: { auth: true } },
  { path: '/billing', name: 'billing', component: () => import('../views/BillingPage.vue'), meta: { auth: true } },
  { path: '/marketplace', name: 'marketplace', component: () => import('../views/MarketplacePage.vue'), meta: { auth: true } },
  { path: '/system', name: 'system', component: () => import('../views/SystemPage.vue'), meta: { auth: true } },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsPage.vue'), meta: { auth: true } },
  { path: '/m/:moduleId', name: 'module', component: () => import('../views/ModuleView.vue'), meta: { auth: true } },
  // Pantalla de activación: hay sesión pero el hub no tiene un entitlement válido (§2.10).
  { path: '/activation', name: 'activation', component: () => import('../views/ActivationPage.vue'), meta: { auth: true } },
];

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

// Auth-gate: rutas con meta.auth requieren sesión; si no, a /login. (Vue-router nativo, sin React.)
router.beforeEach((to) => {
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
  // Un módulo concreto solo se monta si el hub tiene derecho (acceso por URL directa).
  if (to.name === 'module' && !isModuleEntitled(String(to.params.moduleId))) {
    return { name: 'dashboard' };
  }
  return true;
});

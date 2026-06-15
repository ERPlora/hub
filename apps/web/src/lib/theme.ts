// Tema del shell (modo claro/oscuro). Estado reactivo + persistencia en localStorage, aplicado
// a <html> con la clase Ionic `ion-palette-dark`. Centraliza lo que antes estaba duplicado en
// LoginPage.vue (toggle simple) y SettingsPage.vue (select system/light/dark). El toggle de tema
// vive ahora en la topbar (AppTopbar.vue, paridad con el shell de Cloud).
//
// Modos:
//  - 'system' → sigue `prefers-color-scheme` (y reacciona en vivo a sus cambios).
//  - 'light' / 'dark' → fuerzan el modo, ignorando el sistema.
import { computed, ref } from 'vue';

export type ThemeMode = 'system' | 'light' | 'dark';

const LS_KEY = 'erplora.theme';

function prefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readMode(): ThemeMode {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw === 'system' || raw === 'light' || raw === 'dark') return raw;
  } catch {
    /* noop */
  }
  return 'system';
}

const _mode = ref<ThemeMode>(readMode());

/** Modo de tema seleccionado por el usuario ('system' | 'light' | 'dark'). */
export const themeMode = computed<ThemeMode>(() => _mode.value);

/** ¿Está el shell pintando en oscuro AHORA mismo (resolviendo 'system')? */
export const isDark = computed<boolean>(() =>
  _mode.value === 'dark' || (_mode.value === 'system' && prefersDark()),
);

/** Aplica el modo efectivo al <html> (clase Ionic). Sin eval; manipulación directa del DOM. */
function applyMode(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  const dark = mode === 'dark' || (mode === 'system' && prefersDark());
  document.documentElement.classList.toggle('ion-palette-dark', dark);
}

/** Fija el modo, lo persiste y lo aplica al documento. */
export function setThemeMode(mode: ThemeMode): void {
  _mode.value = mode;
  try {
    localStorage.setItem(LS_KEY, mode);
  } catch {
    /* noop */
  }
  applyMode(mode);
}

/** Alterna claro↔oscuro (el toggle de la topbar). Resuelve 'system' al opuesto del estado real. */
export function toggleTheme(): void {
  setThemeMode(isDark.value ? 'light' : 'dark');
}

/**
 * Arranca el tema en el boot: aplica el modo guardado y, en modo 'system', se suscribe a los
 * cambios de `prefers-color-scheme` para reflejarlos en vivo. Llamar una vez en main.ts.
 */
export function bootTheme(): void {
  applyMode(_mode.value);
  if (typeof window !== 'undefined') {
    window
      .matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', () => {
        if (_mode.value === 'system') applyMode('system');
      });
  }
}

// Tema del shell: modo claro/oscuro + PALETA de marca (ADR-0138). El modo se aplica a <html> con la clase Ionic
// `ion-palette-dark` y la paleta con el atributo `data-ok-palette` (OutfitKit palettes.css,
// mismo contrato que el Cloud). El toggle de modo vive en la topbar (AppTopbar.vue); el
// selector de paleta en /settings (ok-theme-picker).
//
// Modos:
//  - 'system' → sigue `prefers-color-scheme` (y reacciona en vivo a sus cambios).
//  - 'light' / 'dark' → fuerzan el modo, ignorando el sistema.
//
// Paleta — DOS capas (decisión de Ioan, 2026-07-16):
//  - hub_settings.theme_palette   → la GLOBAL del hub (la fija un admin; llega vía
//    hub-settings.ts en el boot y en cada PUT).
//  - `hub_user_pref` → override POR USUARIO y Hub; '' = sin override (seguir a la global).
import { computed, ref } from 'vue';

export type ThemeMode = 'system' | 'light' | 'dark';

/** Paletas válidas — espejo 1:1 de `@erplora/outfitkit/palettes.css` + el default. */
export const THEME_PALETTES = [
  'erplora',
  'terracotta',
  'corporate',
  'minimal',
  'forest',
  'ocean',
  'violet',
] as const;

export type ThemePalette = (typeof THEME_PALETTES)[number];

function prefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

const _mode = ref<ThemeMode>('system');

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

/** Fija el modo en memoria. La persistencia personal vive en `/api/profile`. */
export function setThemeMode(mode: ThemeMode): void {
  _mode.value = mode;
  applyMode(mode);
}

/** Alterna claro↔oscuro (el toggle de la topbar). Resuelve 'system' al opuesto del estado real. */
export function toggleTheme(): void {
  setThemeMode(isDark.value ? 'light' : 'dark');
  void import('./user-profile').then(({ currentUserProfile, updateUserPreferences }) => {
    const preferences = currentUserProfile.value?.preferences;
    if (!preferences) return;
    void updateUserPreferences({ ...preferences, theme_mode: _mode.value });
  });
}

// ── Paleta (data-ok-palette) ────────────────────────────────────────────────────────────

function isPalette(v: unknown): v is ThemePalette {
  return typeof v === 'string' && (THEME_PALETTES as readonly string[]).includes(v);
}

/** Override personal del usuario ('' = sin override, sigue a la global del hub). */
const _localPalette = ref<ThemePalette | ''>('');
/** Paleta GLOBAL del hub (hub_settings). La sincroniza hub-settings.ts al resolver. */
const _hubPalette = ref<ThemePalette>('erplora');

/** Paleta EFECTIVA que pinta el shell (override local → global del hub → erplora). */
export const themePalette = computed<ThemePalette>(() => _localPalette.value || _hubPalette.value);

/** ¿Tiene el usuario un override personal (no sigue a la global del hub)? */
export const hasLocalPalette = computed<boolean>(() => _localPalette.value !== '');

/** Aplica la paleta efectiva al <html> — mismo contrato que applyPalette() de OutfitKit:
 *  'erplora' (default) QUITA el atributo; cualquier otra lo pone. */
function applyPalette(): void {
  if (typeof document === 'undefined') return;
  const p = themePalette.value;
  const root = document.documentElement;
  if (p === 'erplora') root.removeAttribute('data-ok-palette');
  else root.setAttribute('data-ok-palette', p);
}

/** Fija (o quita, con '') el override personal en memoria. */
export function setLocalPalette(palette: ThemePalette | ''): void {
  _localPalette.value = isPalette(palette) ? palette : '';
  applyPalette();
}

/** Aplica la fila del usuario. `null` = heredar del Hub (o sistema para el modo). */
export function applyUserThemePreferences(
  mode: ThemeMode | null,
  palette: ThemePalette | null,
  hubPalette?: string,
): void {
  if (hubPalette) setHubPalette(hubPalette);
  setThemeMode(mode ?? 'system');
  setLocalPalette(palette ?? '');
}

/** Limpia el estado al cerrar sesión para que no se filtre al siguiente usuario. */
export function resetUserThemePreferences(): void {
  applyUserThemePreferences(null, null);
}

/** Sincroniza la paleta GLOBAL del hub (llamada por hub-settings.ts). Un valor desconocido
 *  degrada al default sin romper (defensa contra settings de una versión futura). */
export function setHubPalette(palette: string): void {
  _hubPalette.value = isPalette(palette) ? palette : 'erplora';
  applyPalette();
}

/**
 * Arranca el tema en el boot: aplica el modo y la paleta guardados y, en modo 'system', se
 * suscribe a los cambios de `prefers-color-scheme` para reflejarlos en vivo. Llamar una vez
 * en main.ts. (La paleta global llega después, cuando hub-settings resuelve el GET.)
 */
export function bootTheme(): void {
  // Borra la antigua autoridad global por navegador: podía mezclar preferencias de usuarios.
  try {
    localStorage.removeItem('erplora.theme');
    localStorage.removeItem('erplora.palette');
  } catch {
    /* noop */
  }
  applyMode(_mode.value);
  applyPalette();
  if (typeof window !== 'undefined') {
    window
      .matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', () => {
        if (_mode.value === 'system') applyMode('system');
      });
  }
}

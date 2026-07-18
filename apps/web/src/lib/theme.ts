// Tema del shell: modo claro/oscuro + PALETA de marca (ADR-0138). Estado reactivo +
// persistencia en localStorage; el modo se aplica a <html> con la clase Ionic
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
//  - localStorage `erplora.palette` → override POR USUARIO en este navegador; '' = sin
//    override (seguir a la global). Con override, gana el override.
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

const LS_KEY = 'erplora.theme';
const LS_PALETTE_KEY = 'erplora.palette';

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

// ── Paleta (data-ok-palette) ────────────────────────────────────────────────────────────

function isPalette(v: unknown): v is ThemePalette {
  return typeof v === 'string' && (THEME_PALETTES as readonly string[]).includes(v);
}

function readLocalPalette(): ThemePalette | '' {
  try {
    const raw = localStorage.getItem(LS_PALETTE_KEY);
    if (isPalette(raw)) return raw;
  } catch {
    /* noop */
  }
  return '';
}

/** Override local del usuario ('' = sin override, sigue a la global del hub). */
const _localPalette = ref<ThemePalette | ''>(readLocalPalette());
/** Paleta GLOBAL del hub (hub_settings). La sincroniza hub-settings.ts al resolver. */
const _hubPalette = ref<ThemePalette>('erplora');

/** Paleta EFECTIVA que pinta el shell (override local → global del hub → erplora). */
export const themePalette = computed<ThemePalette>(() => _localPalette.value || _hubPalette.value);

/** ¿Tiene este navegador un override local (no sigue a la global del hub)? */
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

/** Fija (o quita, con '') el override LOCAL del usuario, lo persiste y lo aplica. */
export function setLocalPalette(palette: ThemePalette | ''): void {
  _localPalette.value = isPalette(palette) ? palette : '';
  try {
    if (_localPalette.value) localStorage.setItem(LS_PALETTE_KEY, _localPalette.value);
    else localStorage.removeItem(LS_PALETTE_KEY);
  } catch {
    /* noop */
  }
  applyPalette();
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

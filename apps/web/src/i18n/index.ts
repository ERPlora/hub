// i18n del shell (vue-i18n, Composition API). Cubre el chrome (nav, topbar, footer del sidebar,
// asistente, archivos) — los textos de cada vista se migran por pantalla.
//
// AÑADIR UN IDIOMA = crear UN fichero, nada más: copia `./locales/es.ts` a `./locales/<código>.ts`
// (p.ej. `fr.ts`), traduce los valores y pon su nombre en `_meta.name` ('Français'). El glob de
// abajo lo descubre solo: aparece en el selector de Ajustes y queda disponible en caliente. No se
// edita este fichero ni ningún otro para sumar idiomas.
import { createI18n } from 'vue-i18n';
// `es` es la PLANTILLA de tipo del catálogo (esquema canónico). No rompe el "añadir fichero =
// funciona": los locales se descubren por glob igual; `es` solo aporta el tipo de los mensajes.
import esSchema from './locales/es';

type ShellMessages = typeof esSchema;

// Carga TODOS los locales de ./locales/*.ts en build (Vite import.meta.glob, eager).
const localeModules = import.meta.glob<{ default: ShellMessages }>('./locales/*.ts', {
  eager: true,
});

const messages: Record<string, ShellMessages> = {};
for (const [path, mod] of Object.entries(localeModules)) {
  const code = path.match(/\/([^/]+)\.ts$/)?.[1];
  if (code) messages[code] = mod.default;
}

// Código de idioma (dinámico: cualquiera que tenga fichero en ./locales/).
export type Locale = string;

// Idioma por defecto/fallback: el producto nace en España. Si no existiera su fichero, cae al
// primero disponible (defensivo para que nunca arranque sin idioma).
const DEFAULT: Locale = messages.es ? 'es' : (Object.keys(messages)[0] ?? 'es');

/** Idiomas disponibles (código + nombre para el selector), ordenados por nombre. */
export const availableLocales: { code: string; name: string }[] = Object.entries(messages)
  .map(([code, m]) => ({
    code,
    name: (m as { _meta?: { name?: string } })._meta?.name ?? code,
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

let personalLocale: Locale | null = null;

function detectLocale(): Locale {
  // El override personal del usuario (si lo puso) manda en el primer render. Si no, arranca en el
  // DEFAULT (español); el idioma DEFAULT del HUB se reconcilia luego en el boot vía bootHubLanguage()
  // cuando el runtime ya respondió (/api/hub/context). El idioma del navegador NO se usa como
  // fallback: el Hub está localizado en ES y mostrar otro idioma por defecto rompe la UX.
  return DEFAULT;
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: DEFAULT,
  messages,
});

/**
 * The key module Web Components read to know which language they are in (ADR-0055).
 *
 * A module WC is a FOREIGN custom element with its own bundle: it cannot call into the shell's
 * vue-i18n. The SDK (`ErploraClient.locale`) gives it a SYNCHRONOUS bridge that reads this key,
 * falling back to `'es'`. That it is `localStorage` and not a variable in memory is deliberate:
 * the module reads it in its `connectedCallback`, before anybody can hand it anything.
 */
export const MODULE_LOCALE_KEY = 'erplora.locale';

function reflectDocumentLocale(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale;
}

/**
 * Publishes the EFFECTIVE language: applies it to the shell and mirrors it for the modules
 * (hub#790).
 *
 * This is where the defect lived, and it was one line on each side pointing in opposite
 * directions: the SDK read `erplora.locale` and `applyUserLocale` did `removeItem` on that very
 * key. NOBODY ever wrote it. A user on English had the whole shell in English and the till in
 * Spanish, always — the module was reading the SDK's fallback.
 *
 * The key is a derived MIRROR, not the preference: the authority is still `/api/profile`. That is
 * why it is rewritten on every change and removed on none — `localStorage` outlives the session
 * and every user of that till shares it, so an absent key is read as `'es'` by every module, which
 * is exactly how a hub whose own language is English ended up with Spanish modules.
 *
 * One path for the three doors (`setLocale`, `applyUserLocale`, `bootHubLanguage`): three copies
 * of this is how the two that existed drifted apart.
 */
function publishLocale(locale: Locale): void {
  i18n.global.locale.value = locale;
  reflectDocumentLocale(locale);
  try {
    localStorage.setItem(MODULE_LOCALE_KEY, locale);
  } catch {
    /* storage refused: the module falls back, but the shell stays in its language. */
  }
  // ADR-0055: mounted WCs do not re-read `localStorage` by themselves — the event repaints them.
  try {
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale } }));
  } catch {
    /* noop */
  }
}

// hub#2143: what the device showed last, read BEFORE the line below overwrites it with the boot
// default. See `lastDeviceLocale`.
const deviceLocaleBeforeBoot: Locale | null = (() => {
  try {
    return localStorage.getItem(MODULE_LOCALE_KEY);
  } catch {
    return null;
  }
})();

// At boot: the bridge has to exist BEFORE the first module mounts. A WC that connects on the
// first render reads the key at that instant, and if it is not there it stays on its fallback
// until something changes it — which may never happen.
publishLocale(i18n.global.locale.value);

/**
 * The language this device showed last time, when it has a translation (hub#2143). Only for what
 * is painted before the hub answers — the «cannot connect» notice —: with no context there is no
 * hub language, and the boot default would greet an English-speaking business in Spanish. Once
 * the hub answers, `bootHubLanguage` decides as always.
 */
export function lastDeviceLocale(): Locale | null {
  return deviceLocaleBeforeBoot && messages[deviceLocaleBeforeBoot] ? deviceLocaleBeforeBoot : null;
}

/** Changes the shell language on the fly. The personal preference is persisted in `/api/profile`. */
export function setLocale(locale: Locale): void {
  if (!messages[locale]) return; // a language with no file → no-op (defensive)
  personalLocale = locale;
  publishLocale(locale);
}

/** Idioma activo actual. Para usar FUERA de componentes (p.ej. al llamar al runtime con
 *  `?locale=` — ADR-0055). En componentes Vue usa `useI18n().locale`. */
export function getLocale(): Locale {
  return i18n.global.locale.value;
}

/** ¿El usuario tiene un override de idioma PERSONAL? (true = ignora el default del hub). */
export function hasUserLocaleOverride(): boolean {
  return personalLocale != null;
}

/** Aplica el idioma personal, o el default del Hub cuando no existe override. */
export function applyUserLocale(locale: Locale | null, hubDefault?: Locale | null): void {
  personalLocale = locale && messages[locale] ? locale : null;
  const effective = personalLocale ?? (hubDefault && messages[hubDefault] ? hubDefault : DEFAULT);
  publishLocale(effective);
}

export function resetUserLocale(hubDefault?: Locale | null): void {
  applyUserLocale(null, hubDefault);
}

/**
 * Reconciliación idioma DEFAULT-del-hub ↔ override-del-usuario (decisión del humano):
 *   locale efectivo = override del usuario (`hub_user_pref`) ?? language del hub ?? 'es'.
 *
 * Aplica el idioma DEFAULT del hub (de /api/hub/context o /api/settings) en caliente SOLO si el
 * usuario NO tiene override personal. No fabrica una preferencia: sigue siendo el "default del
 * hub". El selector de Perfil persiste la elección mediante `/api/profile`.
 *
 * Idempotente y no destructivo: idioma desconocido / igual al activo → no-op.
 */
export function bootHubLanguage(hubDefault: string | null | undefined): void {
  if (hasUserLocaleOverride()) return; // el override personal manda
  if (!hubDefault || !messages[hubDefault]) return; // sin default válido del hub → deja 'es'
  if (i18n.global.locale.value === hubDefault) return;
  publishLocale(hubDefault);
}

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

function reflectDocumentLocale(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale;
}

reflectDocumentLocale(i18n.global.locale.value);

/** Cambia el idioma del shell en caliente. La persistencia personal vive en `/api/profile`. */
export function setLocale(locale: Locale): void {
  if (!messages[locale]) return; // idioma sin fichero → no-op (defensivo)
  personalLocale = locale;
  i18n.global.locale.value = locale;
  reflectDocumentLocale(locale);
  // ADR-0055: notifica el cambio de idioma a los Web Components de módulo montados (que leen
  // `globalThis.erplora.locale` y resuelven `erplora.t()`) y a quien re-fetche la navegación.
  try {
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale } }));
  } catch {
    /* noop */
  }
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
  i18n.global.locale.value = effective;
  reflectDocumentLocale(effective);
  try {
    localStorage.removeItem('erplora.locale');
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale: effective } }));
  } catch {
    /* noop */
  }
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
  i18n.global.locale.value = hubDefault;
  reflectDocumentLocale(hubDefault);
  // Notifica el cambio a los Web Components de módulo montados (ADR-0055), igual que setLocale.
  try {
    window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale: hubDefault } }));
  } catch {
    /* noop */
  }
}

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

const LS_KEY = 'erplora.locale';
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

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved && messages[saved]) return saved;
  } catch {
    /* noop */
  }
  // El producto arranca en español. Solo el ajuste explícito del usuario (SettingsPage →
  // setLocale) cambia el idioma; el idioma del navegador NO se usa como fallback porque el
  // Hub está localizado en ES y mostrar otro idioma por defecto rompe la UX.
  return DEFAULT;
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: DEFAULT,
  messages,
});

/** Cambia el idioma del shell en caliente y lo persiste para el siguiente arranque. */
export function setLocale(locale: Locale): void {
  if (!messages[locale]) return; // idioma sin fichero → no-op (defensivo)
  i18n.global.locale.value = locale;
  try {
    localStorage.setItem(LS_KEY, locale);
  } catch {
    /* noop */
  }
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

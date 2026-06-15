// i18n del shell (vue-i18n, Composition API). Por ahora solo el chrome (nav, topbar, footer del
// sidebar). El locale inicial = persistido en localStorage → idioma del navegador → 'es'
// (el producto nace en España). La selección de idioma del Hub (SettingsPage) puede llamar a
// `setLocale()` para cambiarlo en caliente; queda persistido para el siguiente arranque.
import { createI18n } from 'vue-i18n';
import es from './locales/es';
import en from './locales/en';

export type Locale = 'es' | 'en';

const LS_KEY = 'erplora.locale';

function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved === 'es' || saved === 'en') return saved;
  } catch {
    /* noop */
  }
  const nav = typeof navigator !== 'undefined' ? navigator.language.toLowerCase() : 'es';
  return nav.startsWith('en') ? 'en' : 'es';
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'es',
  messages: { es, en },
});

/** Cambia el idioma del shell en caliente y lo persiste para el siguiente arranque. */
export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale;
  try {
    localStorage.setItem(LS_KEY, locale);
  } catch {
    /* noop */
  }
}

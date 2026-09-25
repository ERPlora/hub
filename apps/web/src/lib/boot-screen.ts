// hub#2143 — the two faces of `#app` before the shell mounts.
//
// The served document paints a spinner inside `#app` (hub#2073). When the hub does not answer, the
// notice replaces it; retrying puts the SAME spinner back — captured from the document, not copied
// here, so the two cannot drift. The notice is its own small Vue app because the shell is not
// mounted yet (and must not be: it would open with no hub behind it). Ionic's config (`mode: 'ios'`)
// is already global by then — `main.ts` installs `IonicVue` when it creates the shell app.
import { createApp, type App as VueApp } from 'vue';

import BootUnreachable from '../components/BootUnreachable.vue';
import { MODULE_LOCALE_KEY, i18n } from '../i18n';

export interface BootScreen {
  showUnreachable(retry: () => void): void;
  showProgress(): void;
}

/**
 * The language this device showed last (`erplora.locale`, rewritten on every change), when it has a
 * translation. With no answer from the hub there is no hub language, and the shell's boot default
 * (Spanish) would greet an English-speaking business in a language it never chose.
 */
function lastDeviceLocale(): string | null {
  try {
    const stored = localStorage.getItem(MODULE_LOCALE_KEY);
    return stored && i18n.global.availableLocales.includes(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function createBootScreen(el: HTMLElement): BootScreen {
  const progressMarkup = el.innerHTML;
  let notice: VueApp | null = null;
  // The shell's locale before the notice borrowed one; given back when the notice goes, because the
  // hub's own language is `bootHubLanguage`'s call once the context answers, not the notice's.
  let shellLocale: string | null = null;

  const unmountNotice = (): void => {
    notice?.unmount();
    notice = null;
    if (shellLocale !== null) {
      i18n.global.locale.value = shellLocale;
      shellLocale = null;
    }
  };

  return {
    showUnreachable(retry) {
      unmountNotice();
      const deviceLocale = lastDeviceLocale();
      if (deviceLocale) {
        shellLocale = i18n.global.locale.value;
        i18n.global.locale.value = deviceLocale;
      }
      notice = createApp(BootUnreachable, { onRetry: retry }).use(i18n);
      notice.mount(el);
    },
    showProgress() {
      unmountNotice();
      el.innerHTML = progressMarkup;
    },
  };
}

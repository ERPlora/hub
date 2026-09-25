// hub#2143 — the two faces of `#app` before the shell mounts.
//
// The served document paints a spinner inside `#app` (hub#2073). When the hub does not answer, the
// notice replaces it; retrying puts the SAME spinner back — captured from the document, not copied
// here, so the two cannot drift. The notice is its own small Vue app because the shell is not
// mounted yet (and must not be: it would open with no hub behind it). Ionic's config (`mode: 'ios'`)
// is already global by then — `main.ts` installs `IonicVue` when it creates the shell app.
import { createApp, type App as VueApp } from 'vue';

import BootUnreachable from '../components/BootUnreachable.vue';
import { i18n } from '../i18n';

export interface BootScreen {
  showUnreachable(retry: () => void): void;
  showProgress(): void;
}

export function createBootScreen(el: HTMLElement): BootScreen {
  const progressMarkup = el.innerHTML;
  let notice: VueApp | null = null;

  const unmountNotice = (): void => {
    notice?.unmount();
    notice = null;
  };

  return {
    showUnreachable(retry) {
      unmountNotice();
      notice = createApp(BootUnreachable, { onRetry: retry }).use(i18n);
      notice.mount(el);
    },
    showProgress() {
      unmountNotice();
      el.innerHTML = progressMarkup;
    },
  };
}

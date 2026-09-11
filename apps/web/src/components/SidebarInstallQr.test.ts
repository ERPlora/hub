// @vitest-environment happy-dom
// hub#1715 — the QR that carries this hub to a phone, and the guard that keeps it there.
//
// Before this, the only way to open the hub on a phone was to type the address by hand, letter by
// letter, standing at the counter. That is friction at the exact moment somebody is deciding
// whether the product is worth it.
//
// Two halves, and the second is the one that matters in six months:
//   · it PAINTS, unconditionally, carrying the hub's public address;
//   · nothing can gate it away. Ioan's words were «tiene que aparecer siempre», so the absence of a
//     condition is itself under test — otherwise the first person who needs the sidebar shorter
//     puts a `v-if` on it and nobody connects that to this issue.
import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import SidebarInstallQr from './SidebarInstallQr.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// The icon registry bakes its SVGs at BUILD time (`~icons/ion/*?raw`, unplugin-icons), and those
// virtual modules do not exist under vitest. Doubling the leaf is the house pattern
// (`SidebarAppUpdate.test.ts`); the NAME still travels, and `icons.test.ts` is what proves the real
// registry knows it.
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en, es } });

// Resolved from the project root, not from `import.meta.url`: under `happy-dom` that URL is an
// `http:` one (the fake document's origin), and `fileURLToPath` rejects it. The source-reading
// guards below are the point of this suite, so they must not depend on the DOM the mount half needs.
const HERE = join(process.cwd(), 'src', 'components');

const componentSource = (): string => readFileSync(join(HERE, 'SidebarInstallQr.vue'), 'utf8');

const appSource = (): string => readFileSync(join(HERE, '..', 'App.vue'), 'utf8');

function mountQr() {
  return mount(SidebarInstallQr, { global: { plugins: [i18n] } });
}

describe('the sidebar carries this hub to a phone', () => {
  it('paints a QR with no props, no session and no setup', () => {
    // No props: there is nothing a caller could fail to pass, so there is no way to mount it blank.
    const qr = mountQr().find('ok-qr');
    expect(qr.exists()).toBe(true);
  });

  it('encodes the hub address, not the screen the shell happens to be on', () => {
    // happy-dom serves `http://localhost:3000` by default: a loopback host WITH a port, which is
    // exactly the development case `installQrUrl` has to keep whole.
    const value = mountQr().find('ok-qr').attributes('value');
    expect(value).toBe(`http://${window.location.host}/`);
    expect(value).not.toContain('shell=1');
  });

  it('says what to do with it, from the catalogue and never hardcoded', () => {
    const text = mountQr().text();
    expect(text.length).toBeGreaterThan(0);
    // A missing key renders as the key itself. That is the failure this catches: a sentence that
    // looks wired, reads as `installQr.something` on screen, and passes a `toContain` on nothing.
    expect(text).not.toMatch(/installQr\./);
  });
});

describe('nothing can gate the QR away (hub#1715, «tiene que aparecer siempre»)', () => {
  /**
   * The «always» is asserted as the ABSENCE of a condition, on the template rather than on a list
   * of forbidden words. A word list looks stricter and is worse: it trips on `explains` for
   * containing `plan`, so the next person to touch the file deletes the guard instead of the gate.
   *
   * A `v-if` here could only ever mean one of four things, and every one of them puts the hub back
   * to «type the address by hand» for somebody:
   *  · role / permission → the person setting a phone up is usually on the till, not an admin;
   *  · plan / tier       → getting the product onto a phone is not an upsell;
   *  · module            → the shell owns this; no module does;
   *  · dismissed         → «don't show again» is how a permanent affordance becomes a dead one.
   *
   * So: no condition at all. The rail (a narrow desktop panel the user collapses on purpose) is
   * handled in CSS precisely so it does not need one.
   */
  it('the component renders unconditionally: no v-if, no v-show, anywhere in its template', () => {
    const template = componentSource().match(/<template>([\s\S]*?)<\/template>/)?.[1] ?? '';
    expect(template).not.toBe('');
    expect(template).not.toMatch(/\sv-if[=\s>]|\sv-show[=\s>]/);
  });

  it('keeps no memory of having been closed: there is nothing to close', () => {
    const source = componentSource();
    for (const term of ['localStorage', 'sessionStorage', 'dismiss', 'Dismiss']) {
      expect(source).not.toContain(term);
    }
  });

  it('the shell mounts it in the sidebar footer, with no condition on the tag', () => {
    const app = appSource();
    expect(app).toContain('<SidebarInstallQr');

    // Checked on the TAG, not the file: App.vue is full of legitimate `v-if`s belonging to the
    // other entries in that same footer (the update offer, the plan link).
    const tag = app.match(/<SidebarInstallQr[^>]*?\/?>/)?.[0] ?? '';
    expect(tag).not.toMatch(/v-if|v-show/);

    // The footer, on purpose: it is the one part of the sidebar that never scrolls away.
    const footer = app.slice(app.indexOf('<ion-footer'), app.indexOf('</ion-footer>'));
    expect(footer).toContain('<SidebarInstallQr');
  });

  it('does not re-open the install prompt hub#685 closed', () => {
    // hub#685 banned the INTERRUPTION, not installability. A passive code in a panel asks nothing;
    // capturing the browser's own offer to re-serve it ourselves would be the banned thing again.
    const source = componentSource();
    for (const banned of ['beforeinstallprompt', 'PwaInstallModal', 'installModalOpen', 'maybeShowInstallModal']) {
      expect(source).not.toContain(banned);
    }
  });
});


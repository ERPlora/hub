// The apps' tasks in «Finish setting up your business» speak the language of the person looking,
// like the rest of the list (hub#2356).
//
// What it pins: the checklist has two sources. The shell translates the core items with its own
// i18n, which follows the language of the viewer's PROFILE; the items an app adds come already
// translated by the runtime (`hub.setup.status`, from the module's `locales/<lang>.json#setup`).
// The runtime picked that language from the HUB setting, so a person with the app in English on a
// hub left in Spanish read «Finish setting up your business» with «Tu numeración de facturas»
// under it.
//
// Why this is a bench spec: the defect is the MEETING of the two halves — the shell's language on
// one side, the real runtime's answer on the other — and only a real browser talking to a real
// runtime paints both in the same list. The hub is left in its default language and the browser
// in Spanish on purpose, so that the only thing asking for English is the profile.
import { cpSync, rmSync } from 'node:fs';
import { join } from 'node:path';

import { expect, request as pwRequest, test } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';
const MODULES_DIR = process.env.HUB_E2E_MODULES_DIR ?? '';
const FIXTURES = join(import.meta.dirname, 'fixtures', 'modules');
const MODULE_ID = 'e2e_setup_locale';
const ITEM = `setup-item-${MODULE_ID}.setup`;

const COPY = {
  en: {
    card: 'Finish setting up your business',
    title: 'Your invoice numbering',
    description: 'Choose how your invoices are numbered.',
  },
  es: {
    card: 'Termina de configurar tu negocio',
    title: 'Tu numeración de facturas',
    description: 'Elige cómo se numeran tus facturas.',
  },
} as const;

type Session = Awaited<ReturnType<typeof loginByPin>>;
let session: Session;

async function call(method: 'POST' | 'PUT' | 'GET', path: string, data?: unknown): Promise<unknown> {
  const api = await pwRequest.newContext();
  const res = await api.fetch(`${RUNTIME}${path}`, {
    method,
    headers: { 'X-Hub-Session': session.token },
    data,
  });
  expect(res.ok(), `${method} ${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json().catch(() => null);
  await api.dispose();
  return body;
}

/** Saves the viewer's own language, exactly as the Profile screen does (`PUT /api/profile`). */
async function setProfileLanguage(language: string | null): Promise<void> {
  const profile = (await call('GET', '/api/profile')) as {
    first_name: string;
    last_name: string;
    email: string;
  };
  await call('PUT', '/api/profile', {
    first_name: profile.first_name,
    last_name: profile.last_name,
    email: profile.email,
    preferences: { language, theme_mode: null, theme_palette: null },
  });
}

test.use({ locale: 'es-ES' });

test.beforeAll(async () => {
  expect(MODULES_DIR, 'playwright.config.ts exports the bench modules folder').not.toBe('');
  session = await loginByPin();
  cpSync(join(FIXTURES, MODULE_ID), join(MODULES_DIR, MODULE_ID), { recursive: true });
  await call('POST', '/api/modules/install', { dir: join(MODULES_DIR, MODULE_ID) });
  // A session's permissions are the ones its role had when it signed in: sign in again so it
  // carries the one the app just granted to admins (without it the item is not offered at all).
  session = await loginByPin();
});

test.afterAll(async () => {
  // The rest of the suite asserts on a freshly created hub: leave it as it was found.
  await setProfileLanguage(null);
  await call('POST', `/api/modules/${MODULE_ID}/uninstall`);
  rmSync(join(MODULES_DIR, MODULE_ID), { recursive: true, force: true });
});

test.describe('The app tasks of the checklist follow the profile language (hub#2356)', () => {
  test.describe.configure({ mode: 'serial' });

  for (const lang of ['en', 'es'] as const) {
    for (const viewport of VIEWPORTS) {
      test(`${lang} · ${viewport.width}×${viewport.height}: the whole list in the viewer's language`, async ({
        page,
      }) => {
        await setProfileLanguage(lang);
        await page.setViewportSize(viewport);
        await withSession(page, session);
        await page.goto('/');

        const card = page.getByTestId('setup-card');
        await expect(card).toBeVisible();
        // The core half (the shell's own i18n) …
        await expect(card).toContainText(COPY[lang].card);
        // A fresh hub still misses its business identity, so the short view leads with that ⛔
        // item alone; the person opens the rest, as they would.
        await page.getByTestId('setup-toggle').click();
        // … and the app half (the runtime's translation), in the SAME language.
        const item = page.getByTestId(ITEM);
        await expect(item).toBeVisible();
        await expect(item.locator('.setup-row-title')).toHaveText(COPY[lang].title);
        await expect(item.locator('.setup-row-desc')).toHaveText(COPY[lang].description);

        // Screen-first evidence for the review, not a baseline: the row must be readable at each width.
        await item.scrollIntoViewIfNeeded();
        await page.screenshot({
          path: test.info().outputPath(`checklist-${lang}-${viewport.width}.png`),
        });
      });
    }
  }
});

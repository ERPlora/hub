// flow: BASE-F64 (the language asked of the assistant)
// The language the person asks the assistant for applies as «My profile»'s selector does: once its card is confirmed,
// the open app speaks it, «My apps» included, without reloading, and it still does after reloading. In both
// directions. The card says the language alone, by its name, and the appearance the person has stays theirs. At the
// end the owner of `a` gets back the preferences they had, since other specs sign in as them.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { askForACard, card, decide, openPanelAtTheDesk, shots } from './assistant-panel';
import { A, api, login, shown } from './helpers';
import { panelSpec } from './provider-helpers';

panelSpec();

type Preferences = { language: '' | 'es' | 'en'; theme_mode: string; palette: string; ui_scale: number };

/** An appearance of the person's own, none of it the business's. */
const APPEARANCE = { theme_mode: 'dark', palette: 'forest', ui_scale: 90 };

const KEY = 'FIX-HUB-BASE-ASSISTANT-LANGUAGE-APPLIES';

const WORDS = {
  en: { run: 'Run this action?', asked: 'Change in My profile: Language: Español', myApps: 'My apps', verifactu: 'Set up VeriFactu' },
  es: { run: '¿Ejecutar esta acción?', asked: 'Cambiar en Mi perfil: Idioma: English', myApps: 'Mis apps', verifactu: 'Configura VeriFactu' },
} as const;

async function speaking(context: BrowserContext, language: 'en' | 'es'): Promise<void> {
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
}

/** The Home in `language`: the shell's own words and the server's (the setup checklist, a live read). */
async function inLanguage(page: Page, language: 'en' | 'es'): Promise<void> {
  await expect(page.locator('html')).toHaveAttribute('lang', language);
  await expect(shown(page).getByTestId('home-my-apps').locator('h2')).toHaveText(WORDS[language].myApps);
  const verifactu = shown(page).locator('[data-testid="setup-row"][data-key="verifactu.sending_route"]');
  await expect(verifactu).toContainText(WORDS[language].verifactu);
}

/** Asks the assistant, speaking `from`, for the app in `to`, and says yes to its card; the Home's health row, which
 *  the server writes in the session's language, is asked again. */
async function askedFor(page: Page, from: 'en' | 'es', to: 'en' | 'es'): Promise<void> {
  await askForACard(page, `E2E-ASK base__profile__preferences_set ${JSON.stringify({ language: to })}`);
  await expect(card(page)).toContainText(WORDS[from].run);
  await expect(card(page).getByText(WORDS[from].asked, { exact: true })).toBeVisible();
  await shots(page, `${KEY}-CARD-${from.toUpperCase()}`);
  const health = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/home/health');
  await decide(page, 'submit');
  expect((await health).status()).toBe(200);
}

async function kept(context: BrowserContext): Promise<Preferences> {
  const answer = await api<Preferences>(context, A, 'GET', '/me/profile');
  expect(answer.status, JSON.stringify(answer.data)).toBe(200);
  const { language, theme_mode, palette, ui_scale } = answer.data;
  return { language, theme_mode, palette, ui_scale };
}

test('BASE-F64 — the language asked of the assistant applies at once and after reloading, in both directions', async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  const before = await kept(context);
  try {
    expect((await api(context, A, 'POST', '/me/preferences', APPEARANCE)).status).toBe(200);
    expect(await kept(context)).toEqual({ ...APPEARANCE, language: before.language });
    await speaking(context, 'es');
    await openPanelAtTheDesk(page);
    await inLanguage(page, 'es');
    await page.evaluate(() => {
      document.documentElement.dataset.sameDocument = 'yes';
    });

    await askedFor(page, 'es', 'en');
    await inLanguage(page, 'en');
    expect(await kept(context)).toEqual({ ...APPEARANCE, language: 'en' });
    await expect(page.locator('html')).toHaveAttribute('data-same-document', 'yes');
    await shots(page, `${KEY}-EN`);
    await page.reload();
    await inLanguage(page, 'en');

    await openPanelAtTheDesk(page);
    await askedFor(page, 'en', 'es');
    await inLanguage(page, 'es');
    expect(await kept(context)).toEqual({ ...APPEARANCE, language: 'es' });
    await shots(page, `${KEY}-ES`);
    await page.reload();
    await inLanguage(page, 'es');
  } finally {
    expect((await api(context, A, 'POST', '/me/preferences', before)).status).toBe(200);
    await context.close();
  }
});

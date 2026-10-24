// The till's «Speak» key (FIX-SALE-POS-NO-SPEAK-KEY; apps/sale/WORKBOOK.md «Vender», PLAN §30 point 4), end to end
// with its real dependencies, as base-assistant.spec.ts sets them up: the Hub of this stack, its SaaS's gateway
// (`/internal/speech/transcribe`, `/internal/assistant/*`) and, behind it, the e2e's provider (assistant-provider.ts,
// started here). The browser's fake microphone records, erplora.com transcribes it (`DICTATION`), the words wait in
// the assistant's box with its panel open and nothing is asked until the person sends: `DICTATION` asks for a write,
// which stops on its card. Offline, the key stays greyed and a tap says why. The SaaS must be seeded with this
// provider and run with `ASSISTANT_SERVICE_PROVIDER=e2e-local` (README «El asistente»).
// flow: SALE-F01
// flow: BASE-F94
import { execSync } from 'node:child_process';

import { expect, type Locator, type Page, test } from '@playwright/test';

import { DICTATION, type Provider, startProvider } from './assistant-provider';
import { A, EMPLOYEE, login, REPO_DIR, shot, untilStill } from './helpers';
import { STACK } from './stack';

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.afterAll(async () => {
  await provider?.close();
});

test.beforeEach(() => {
  // This month's messages of the business `a`: none, so a run never spends the plan's allowance.
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
});

// The browser's fake microphone: a worker-wide launch option, so for the whole file.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

const key = (page: Page): Locator => page.locator('[data-testid="pos-speak"]');
const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const asked = (): number => provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;
const transcribed = (): number => provider.seen.filter((seen) => seen.path === '/v1/audio/transcriptions').length;

async function till(page: Page): Promise<void> {
  await page.goto(`${A}/sale/pos`);
  await expect(key(page)).toBeVisible();
}

/** Speaks into the key: a first tap records, a second one stops; the words land in the box of the open panel. */
async function speak(page: Page): Promise<void> {
  await expect(key(page)).toHaveText('Speak');
  await key(page).click();
  await expect(key(page)).toHaveAttribute('aria-pressed', 'true');
  await expect(key(page)).toHaveText('Stop');
  await expect(page.locator('[data-testid="pos-speak-status"]')).toHaveText('Listening…');
  await page.waitForTimeout(1200);
  await key(page).click();
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toHaveValue(DICTATION);
}

/** Closes the panel and empties its box, so the next size dictates into an empty box. */
async function reset(page: Page): Promise<void> {
  await box(page).fill('');
  await panel(page).locator('[data-testid="assistant-close"]').click();
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
}

test('SALE-F01 / BASE-F94 — «Speak» dictates into the assistant: the words wait in its box with the panel open, and only «Send» asks, as the cashier', async ({ page }) => {
  await login(page, A, '/sale/pos', EMPLOYEE);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await till(page);
    const [questions, dictations] = [asked(), transcribed()];
    await speak(page);
    // erplora.com transcribed it; nothing was asked: the person sees what was understood first.
    expect(transcribed()).toBe(dictations + 1);
    expect(asked()).toBe(questions);
    await expect(answers(page)).toHaveCount(0);
    await expect(key(page)).toHaveText('Speak');
    await untilStill(page);
    await page.screenshot({ path: shot(`FIX-SALE-POS-NO-SPEAK-KEY-${vp.label}`) });
    if (vp.label !== '1440') await reset(page);
  }

  // The cashier sends it: erplora.com answers. `DICTATION` asks for a write the cashier may not make, and the
  // assistant, acting as the cashier, does not make it and says so.
  const questions = asked();
  await panel(page).locator('[data-testid="assistant-send"]').click();
  await expect(answers(page)).toHaveCount(1, { timeout: 30_000 });
  await expect(panel(page).locator('[data-testid="assistant-receipt"]').last()).toContainText('Not done, not allowed: Create in Demo');
  expect(asked()).toBeGreaterThan(questions);
  await expect(card(page)).toBeHidden();
});

test('SALE-F01 / BASE-F94 — a write dictated by whoever may make it stops on its card; «Cancel» leaves it undone', async ({ page }) => {
  await login(page, A, '/sale/pos');
  await page.setViewportSize({ width: 1440, height: 900 });
  await till(page);
  await speak(page);
  await expect(answers(page)).toHaveCount(0);
  await panel(page).locator('[data-testid="assistant-send"]').click();
  await expect(card(page)).toBeVisible({ timeout: 30_000 });
  await card(page).locator('[data-testid="assistant-confirm-cancel"]').click();
  await expect(card(page)).toBeHidden();
  await expect(answers(page)).toHaveCount(1, { timeout: 30_000 });
});

test('SALE-F01 / BASE-F94 — offline, «Speak» stays greyed and a tap says why instead of recording; back online it records', async ({ page }) => {
  await login(page, A, '/sale/pos', EMPLOYEE);
  await till(page);
  // The cashier's session, with the panel closed, for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  const dictations = transcribed();
  await page.context().setOffline(true);
  await expect(key(page)).toHaveAttribute('aria-disabled', 'true');
  // A person can tap a greyed key (it explains itself); Playwright does not tap what is `aria-disabled` unless forced.
  await key(page).click({ force: true });
  await expect(page.locator('ion-toast').filter({ hasText: 'No connection: talking to the assistant needs the internet.' })).toBeVisible();
  await expect(key(page)).toHaveAttribute('aria-pressed', 'false');

  await page.context().setOffline(false);
  await expect(key(page)).toHaveAttribute('aria-disabled', 'false');
  await speak(page);
  expect(transcribed()).toBe(dictations + 1);
});

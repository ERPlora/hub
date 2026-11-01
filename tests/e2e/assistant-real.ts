// The browser and stack side of the assistant's QA with the REAL model, shared by qa/assistant-battery.spec.ts (the
// battery of the QA plan) and qa/assistant-probes.spec.ts (layer 2: the probes): the commands of the stack's Hub and
// SaaS (keys never in their output), the once-per-run seed of the real providers and the documentation index, and the
// assistant's panel as a person uses it (open it, ask, decide the card, read the answer). What can be proved without a
// browser lives in assistant-battery.ts and assistant-probes.ts, with their Vitest tests.
import { execFileSync } from 'node:child_process';

import { expect, type Locator, type Page, type Response } from '@playwright/test';

import { cleanupCommand, type Meta, observe, redact, seedCommand } from './assistant-battery';
import { A, compactBar, HUB_DIR, REPO_DIR, shown } from './helpers';
import { STACK } from './stack';

/** The checkout of the stack's SaaS (`E2E_SAAS_DIR`). */
export const SAAS_DIR = process.env.E2E_SAAS_DIR ?? '';
/** The keys of the real providers: taken out of every output, report and state written. */
export const SECRETS = [process.env.QA_QWEN_API_KEY ?? '', process.env.QA_OPENAI_API_KEY ?? ''];
/** A real model may think for a while: one turn, card included. */
export const TURN_MS = 240_000;

/** A command of the stack's Hub or SaaS; its output without any key. */
export function run(file: string, args: string[], cwd: string, env: NodeJS.ProcessEnv): string {
  try {
    return execFileSync(file, args, { cwd, env, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64 * 1024 * 1024 });
  } catch (error) {
    const failed = error as { stdout?: string; stderr?: string; message: string };
    throw new Error(redact(`${file} ${args[0] ?? ''} … failed in ${cwd}: ${failed.stderr || failed.stdout || failed.message}`.slice(0, 4000), SECRETS));
  }
}

/** One statement on the stack's SaaS database. */
export function saasSql(sql: string): string {
  return execFileSync('docker', ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'hub', '-d', STACK.saasDatabase, '-At', '-c', sql], {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** This month's messages of `a` emptied: a run never stops on the plan's allowance. */
export function emptyMonth(): void {
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

/**
 * Once per run: the Hub's apps registered in the SaaS (`register_apps`: their documentation), the real providers set
 * through the SaaS's own operations (`SEED_PY`), the documentation indexed (`index_docs`, idempotent) and the chunks
 * counted per source. Returns what the report says of them.
 */
export function seedRealProviders(): Omit<Meta, 'run'> {
  expect(SAAS_DIR, 'E2E_SAAS_DIR: the checkout of the stack\'s SaaS (tests/e2e/README.md)').not.toBe('');
  run('uv', ['run', 'python', 'manage.py', 'register_apps'], HUB_DIR, { ...process.env, SHARED_DB_NAME: STACK.saasDatabase });
  const seed = seedCommand(process.env, STACK.saasDatabase);
  const seeded = run(seed.file, seed.args, SAAS_DIR, seed.env).trim().split('\n').at(-1) ?? '{}';
  const models = JSON.parse(seeded) as { model: string; fallback: string; service: string };
  run('uv', ['run', 'python', 'manage.py', 'index_docs'], SAAS_DIR, {
    ...process.env,
    DB_NAME: STACK.saasDatabase,
    ASSISTANT_SERVICE_PROVIDER: 'openai',
  });
  const chunks = Object.fromEntries(
    saasSql('select source, count(*) from assistant_docchunk group by source order by source')
      .split('\n')
      .filter(Boolean)
      .map((line) => {
        const [source, count] = line.split('|');
        return [source, Number(count)];
      }),
  );
  return { ...models, chunks };
}

/**
 * Takes out of the stack's SaaS what a run left there: the real keys (labelled `qa`) and the accounts `emails`. Each
 * spec calls it in its `afterAll`, so it runs whether the run passed or failed; without `E2E_SAAS_DIR` nothing could
 * have been seeded. It refuses the shared SaaS database, as the seed does.
 */
export function cleanUpRealProviders(emails: string[]): void {
  if (!SAAS_DIR) return;
  const command = cleanupCommand(process.env, STACK.saasDatabase, emails);
  run(command.file, command.args, SAAS_DIR, command.env);
}

// ── The panel (as base-assistant.spec.ts reads it) ──

export const panel = (page: Page): Locator => page.locator('[data-testid="assistant-panel"]');
const box = (page: Page): Locator => panel(page).locator('[data-testid="assistant-input"] textarea');
const answers = (page: Page): Locator => panel(page).locator('[data-testid="assistant-answer"]');
const card = (page: Page): Locator => page.locator('ion-modal[data-testid="assistant-confirm"]');
const send = (page: Page): Locator => panel(page).locator('[data-testid="assistant-send"]');
export const foot = (page: Page): Locator => panel(page).locator('[data-testid="assistant-usage"]');
const opener = (page: Page): Locator =>
  shown(page).locator(compactBar(page) ? '[data-testid="topbar-chrome-more"]' : '[data-testid="assistant-button"]');

/** The Hub's home with the assistant's panel open and its box ready. */
export async function openPanel(page: Page): Promise<void> {
  await page.goto(`${A}/`);
  await expect(opener(page)).toBeVisible();
  // The panel stays open across a reload (its state is the tab's): the sparkles would close it.
  if ((await panel(page).getAttribute('data-open')) !== 'true') {
    await opener(page).click();
    if (compactBar(page)) await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  }
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(box(page)).toBeVisible();
}

/**
 * Asks `question` and follows the turn to its end: a card is confirmed (typing its word when it asks one) or cancelled
 * as `decide` says; returns every streamed answer of `/api/assistant/turn` and what was decided. `label` names the
 * question in a timeout.
 */
export async function converse(
  page: Page,
  question: string,
  decide: 'confirm' | 'cancel',
  label: string,
): Promise<{ bodies: string[]; decided: 'confirmed' | 'cancelled' | 'none' }> {
  const bodies: string[] = [];
  const reading: Promise<void>[] = [];
  const heard = (response: Response) => {
    if (!response.url().endsWith('/api/assistant/turn')) return;
    reading.push(response.text().then((text) => void bodies.push(text), () => undefined));
  };
  page.on('response', heard);
  let decided: 'confirmed' | 'cancelled' | 'none' = 'none';
  try {
    const before = await answers(page).count();
    await box(page).fill(question);
    await box(page).press('Enter');
    await expect(answers(page)).toHaveCount(before + 1, { timeout: TURN_MS });
    const deadline = Date.now() + TURN_MS;
    let idleSince = 0;
    while (Date.now() < deadline) {
      if (await card(page).isVisible()) {
        idleSince = 0;
        await Promise.all(reading);
        const button = decide === 'confirm' ? 'submit' : 'cancel';
        const typing = card(page).locator('[data-testid="assistant-confirm-input"] input');
        if (button === 'submit' && (await typing.isVisible())) await typing.fill(observe(bodies).cards.at(-1)?.confirmWord ?? '');
        await card(page).locator(`[data-testid="assistant-confirm-${button}"]`).click();
        await expect(card(page)).toBeHidden();
        decided = button === 'submit' ? 'confirmed' : 'cancelled';
        continue;
      }
      if (await send(page).isVisible()) {
        // Idle for 2 s with no card: the turn has ended (a follow-up round shows «Stop» again at once).
        if (!idleSince) idleSince = Date.now();
        else if (Date.now() - idleSince >= 2_000) break;
      } else {
        idleSince = 0;
      }
      await page.waitForTimeout(250);
    }
    expect(Date.now() < deadline, `${label}: the turn did not end within ${TURN_MS} ms`).toBe(true);
    await Promise.all(reading);
  } finally {
    page.off('response', heard);
  }
  return { bodies, decided };
}

/** Every answer of the assistant in the panel, as a person reads it. */
export async function answerOf(page: Page): Promise<string> {
  return (await panel(page).locator('[data-testid="assistant-bubble-assistant"]').allInnerTexts()).join('\n\n').trim();
}

/** The notices the panel shows under the answers (`claimed_change`…). */
export async function noticesOf(page: Page): Promise<string[]> {
  const ids = await panel(page)
    .locator('[data-testid^="assistant-notice-"]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-testid') ?? ''));
  return ids.map((id) => id.replace('assistant-notice-', ''));
}

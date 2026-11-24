// The Hub's assistant end to end with its real dependencies: the Hub of this stack, its SaaS's
// gateway (`/internal/assistant/*`, `/internal/speech/transcribe`) and, behind it, the e2e's provider
// (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no mock between the
// browser and the provider, no real provider, no real key. The SaaS must be seeded with that provider (README of this
// folder, «El asistente»): `assistant_seed.py gateway http://127.0.0.1:<E2E_AI_PROVIDER_PORT>/v1`.
// The month's messages of the business `a` are set on the SaaS's database before each test (`spend`), so a run never
// spends the plan's allowance and the 80 % and the spent month can be seen.
import {  } from 'node:child_process';

import { expect, test } from '@playwright/test';

import {
  answers,
  ask,
  askForACard,
  box,
  card,
  confirmationReady,
  confirmationSettled,
  confirmedWithTheWord,
  freshPage,
  home,
  lastAnswer,
  lastAnswerAtEachSize,
  openPanel,
  openPanelAtTheDesk,
  panel,
  panelAtTheDesk,
  shots,
} from './assistant-panel';
import { CLAIM_ANSWER, DICTATION, GREETING, LINK_ANSWER } from './assistant-provider';
import { saasSql } from './assistant-real';
import { A, api, capture, login, shot, shown, THREE_SIZES as VIEWPORTS, untilStill, upgradeLandsInside } from './helpers';
import {  } from './stack';
import { chats, panelSpec, spend } from './provider-helpers';
import { pressAssistant, topbarMore, topbarMoreMenu } from './topbar';

const provider = panelSpec();

// The browser's fake microphone, for the dictation test: a worker-wide launch option, so for the whole file.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

test('the sparkles open the panel on the right (on a phone, from «⋮»): docked from 768 px, over the screen on a phone; Escape, × and the veil close it; it stays open across screens and reloads', async ({ page }) => {
  await login(page, A, '/');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await home(page);
    if (vp.width < 768) {
      // The sparkles and «My apps» folded into «⋮», so the title stays centred; the bell stays on the bar.
      await expect(shown(page).locator('[data-testid="assistant-button"]')).toHaveCount(0);
      await expect(shown(page).locator('[data-testid="action-bell"]')).toBeVisible();
      await topbarMore(page).click();
      await expect(topbarMoreMenu(page).locator('[data-testid="assistant-button"]')).toHaveText('Assistant');
      await expect(topbarMoreMenu(page).locator('ion-button')).toHaveCount(2);
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-9-BASE-G110-more-${vp.label}`) });
      await page.keyboard.press('Escape');
      await expect(topbarMoreMenu(page)).toHaveCount(0);
    }
    await openPanel(page);
    await expect(panel(page)).toContainText('Ask me about your sales, your stock or anything about your business.');
    await expect(panel(page).locator('[data-testid="assistant-shortcut"]').first()).toHaveText('What is left to set up?');
    // Measured once it has slid in.
    await untilStill(page);
    const aside = await panel(page).boundingBox();
    const pane = await page.locator('ion-app > ion-split-pane').boundingBox();
    expect(Math.round(aside!.x + aside!.width)).toBe(vp.width);
    if (vp.width < 768) {
      // Over the screen, all of it on a phone, with the veil behind.
      expect(Math.round(aside!.width)).toBe(vp.width);
      await expect(page.locator('[data-testid="assistant-veil"]')).toBeVisible();
    } else {
      // Docked: the screen leaves it its width and keeps working beside it.
      expect(aside!.width).toBeGreaterThanOrEqual(360);
      expect(aside!.width).toBeLessThanOrEqual(420);
      expect(Math.round(pane!.x + pane!.width)).toBe(Math.round(aside!.x));
      await expect(page.locator('[data-testid="assistant-veil"]')).toHaveCount(0);
    }
    await capture(page, `APP-BASE-9-BASE-G110-${vp.label}`);
    // A phone of 420 px or less is all panel (the veil is under it): its ×; wider, Escape wherever the focus is.
    if (vp.width <= 420) await panel(page).locator('[data-testid="assistant-close"]').click();
    else await page.keyboard.press('Escape');
    await expect(panel(page)).toHaveAttribute('data-open', 'false');
    await untilStill(page);
    const after = await page.locator('ion-app > ion-split-pane').boundingBox();
    expect(Math.round(after!.width)).toBe(vp.width);
  }
  // Between a phone and a tablet, 420 px of panel over a veil that closes it.
  await page.setViewportSize({ width: 600, height: 900 });
  await openPanel(page);
  await untilStill(page);
  expect(Math.round((await panel(page).boundingBox())!.width)).toBe(420);
  await page.locator('[data-testid="assistant-veil"]').click({ position: { x: 20, y: 400 } });
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
  await page.setViewportSize({ width: 1440, height: 900 });
  // Open, it stays so on another screen and after reloading; the × closes it, and the sparkles again.
  await openPanel(page);
  await page.goto(`${A}/settings`);
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await page.reload();
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await panel(page).locator('[data-testid="assistant-close"]').click();
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
  await page.reload();
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
});

test('hub-e2e-capture — capture() keeps the panel open after a turn at 390, 834 and 1440: on a phone it is all the screen, its border from top to bottom', async ({ page }) => {
  // At 390 the open panel's first and last 8 rows are the same (white with its left border), which capture() must not
  // mistake for a page not yet painted at its size.
  const KEY = 'FIX-HUB-E2E-CAPTURE-REFUSES-ASSISTANT-PANEL-ON-PHONE';
  await login(page, A, '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await home(page);
  await openPanel(page);
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await lastAnswerAtEachSize(page, KEY);
});

// hub#742, hub#1121: on a phone the panel opens from «⋮», and while Ionic dismisses that menu its focus trap
// pulls the keyboard back into it: the Enter written in the box reached a row of the menu (it opened the bell's list)
// and «Hola» stayed in the box. The panel opens once the menu has gone. The menu's way out is slowed, so a run never gets
// past that moment by luck (a loaded machine did), and the question is written as soon as the box is there, with no
// wait for the menu, as a person does.
test('hub-e2e-open-panel — on a phone the panel takes a question with Enter as soon as it has opened from «⋮»', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await home(page);
  const devtools = await page.context().newCDPSession(page);
  await devtools.send('Animation.enable');
  await devtools.send('Animation.setPlaybackRate', { playbackRate: 0.05 });
  await pressAssistant(page);
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  // Nothing of the menu caught the keys: no menu is left on screen.
  await expect(page.locator('ion-popover:not(.overlay-hidden)')).toHaveCount(0);
});

test('«Ask the assistant» on the setup card opens it on the setup; a shortcut asks at once', async ({ page }) => {
  await login(page, A, '/');
  await page.setViewportSize({ width: 1440, height: 900 });
  await home(page);
  await shown(page).locator('[data-testid="setup-review"]').click();
  await expect(panel(page)).toHaveAttribute('data-open', 'true');
  await expect(panel(page)).toContainText("Review your business's setup. Choose an option or write your question.");
  await shots(page, 'BASE-G121');
  const turn = page.waitForRequest((request) => request.url().endsWith('/api/assistant/turn'));
  await panel(page).locator('[data-testid="assistant-shortcut"]').first().click();
  const sent = (await turn).postDataJSON() as { setup: boolean; messages: { role: string; content: string }[] };
  expect(sent.setup).toBe(true);
  expect(sent.messages.at(-1)).toEqual({ role: 'user', content: 'What is left to set up?' });
  await expect(lastAnswer(page)).toContainText(GREETING.en);
  // The setup's instructions went to the model with the checklist read again by the Hub.
  const instructions = JSON.stringify(provider().seen.filter((s) => s.path === '/v1/chat/completions').at(-1)?.body);
  expect(instructions).toContain('checklist');
});

test('a question and its answer: written as it comes, with its format; «Stop» keeps what came; «Go to Settings» opens it and closes the panel', async ({ page }) => {
  await panelAtTheDesk(page);
  await ask(page, 'Hola');
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toHaveText('Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await shots(page, 'BASE-G111');

  // «Stop» half-way: what was written stays, the bubble says it stopped.
  await ask(page, 'E2E-SLOW', { settle: false });
  await expect(lastAnswer(page)).toContainText('This answer is long');
  await panel(page).locator('[data-testid="assistant-stop"]').click();
  await expect(lastAnswer(page)).toContainText('Stopped.');
  await expect(panel(page).locator('[data-testid="assistant-send"]')).toBeVisible();

  await ask(page, 'E2E-FORMAT ¿Cómo van las ventas?');
  const answer = lastAnswer(page);
  await expect(answer.locator('h3, h4, h5, h6').first()).toHaveText('Today’s sales');
  await expect(answer.locator('strong').first()).toHaveText('€120');
  await expect(answer.locator('li')).toHaveCount(2);
  await expect(answer.locator('table tbody tr')).toHaveCount(2);
  await expect(answer.locator('a[href="/settings#business"]')).toHaveText('Settings');
  const go = panel(page).locator('[data-testid="assistant-go"]');
  await expect(go).toHaveText(['Go to Settings']);
  await shots(page, 'BASE-G113', async () => {
    // The table scrolls inside its own box: the panel never scrolls sideways.
    const sideways = await panel(page).locator('[data-testid="assistant-thread"]').evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(sideways).toBeLessThanOrEqual(0);
    await answer.scrollIntoViewIfNeeded();
  });
  await shots(page, 'BASE-G114', () => go.scrollIntoViewIfNeeded());
  await go.click();
  await expect(page).toHaveURL(`${A}/settings#business`);
  await expect(panel(page)).toHaveAttribute('data-open', 'false');
});

test('an answer that says it changed something nothing changed is flagged, outside the answer', async ({ page }) => {
  await panelAtTheDesk(page);
  await ask(page, 'E2E-CLAIM crea la mesa 9');
  await expect(lastAnswer(page)).toHaveText(CLAIM_ANSWER.en);
  await expect(panel(page).locator('[data-testid="assistant-notice-claimed_change"]')).toContainText(
    'The assistant said it made a change, but no action was run. Nothing was changed.',
  );
  await shots(page, 'BASE-G117');
});

test('an answer with a web address that nothing of the turn looked up is flagged, outside the answer', async ({ page }) => {
  await panelAtTheDesk(page);
  await ask(page, 'E2E-LINK ¿sube el IVA de la comida para llevar?');
  await expect(lastAnswer(page)).toHaveText(LINK_ANSWER.en);
  await expect(panel(page).locator('[data-testid="assistant-notice-unread_link"]')).toContainText(
    'This answer shows a web address the assistant did not really look up. Do not trust it.',
  );
  await shots(page, 'BASE-G153');
});

test('the conversation stays in the tab across reloads, «New conversation» empties it, and signing out forgets it', async ({ page }) => {
  await panelAtTheDesk(page);
  await ask(page, 'Hola');
  await page.reload();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveText(['Hola']);
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await shots(page, 'BASE-G120');
  await page.setViewportSize({ width: 1440, height: 900 });
  await panel(page).locator('[data-testid="assistant-new"]').click();
  await expect(panel(page).locator('[data-testid="assistant-empty"]')).toBeVisible();
  await ask(page, 'Hola otra vez');
  await panel(page).locator('[data-testid="assistant-close"]').click();
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
  await page.locator('ion-popover [data-testid="user-menu-logout"]').click();
  await page.waitForURL((url) => !url.href.startsWith(A));
  await login(page, A, '/', undefined, { fresh: true });
  await openPanel(page);
  await expect(panel(page).locator('[data-testid="assistant-empty"]')).toBeVisible();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveCount(0);
});

test('from 80 % the foot says what is left and each answer moves it; a spent month says so in the answer and in the foot, with «Upgrade plan» to the owner and who to ask to an employee', async ({ page, browser }) => {
  await login(page, A, '/');
  spend(25);
  await openPanelAtTheDesk(page);
  const foot = panel(page).locator('[data-testid="assistant-usage"]');
  await expect(foot).toHaveText(/^You have 5 of 30 messages left this month\. They renew on \S+ 1\.$/);
  await shots(page, 'BASE-G122');
  await page.setViewportSize({ width: 1440, height: 900 });
  // An answer spends one: the foot counts it at once, with no reload.
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
  await expect(foot).toHaveText(/^You have 4 of 30 messages left this month\. They renew on \S+ 1\.$/);
  spend(30);
  await ask(page, 'Hola');
  const failure = panel(page).locator('[data-testid="assistant-failure"]').last();
  await expect(failure).toContainText(/You have used all the assistant's messages of this month \(30 of 30\)\. They renew on \S+ 1\./);
  await expect(failure.locator('[data-testid="assistant-upgrade"]')).toHaveText(/Upgrade plan/);
  // The foot says the same as the answer, and «Upgrade plan» only once.
  await expect(foot).toHaveText(/^You have used all 30 messages of this month\. They renew on \S+ 1\.$/);
  await expect(panel(page).locator('[data-testid="assistant-upgrade"]')).toHaveCount(1);
  await shots(page, 'BASE-G122-spent');
  await page.setViewportSize({ width: 1440, height: 900 });
  // With no session of erplora.com in this browser, the answer's «Upgrade plan» still lands inside it (BASE-F11, hub#723).
  await upgradeLandsInside(page, failure.locator('[data-testid="assistant-upgrade"]'));

  const employee = await freshPage(browser);
  await employee.setViewportSize({ width: 1440, height: 900 });
  await home(employee);
  await openPanel(employee);
  await ask(employee, 'Hola');
  const theirs = panel(employee).locator('[data-testid="assistant-failure"]').last();
  await expect(theirs).toContainText("Ask the business's owner to upgrade the plan.");
  await expect(theirs.locator('[data-testid="assistant-upgrade"]')).toHaveCount(0);
  await employee.context().close();
});

test('with a plan without the assistant the foot says so, and its «Upgrade plan» lands inside erplora.com (BASE-F11)', async ({ page }) => {
  // The plan `a` has on erplora.com, or Free without a subscription (`effective_plan`).
  const plan =
    "coalesce((select s.plan_id from hubs_subscription s join hubs_hub h on h.id = s.hub_id where h.slug = 'a'), (select id from hubs_plan where slug = 'free'))";
  const allowance = saasSql(`select assistant_messages_per_month from hubs_plan where id = ${plan}`);
  saasSql(`update hubs_plan set assistant_messages_per_month = 0 where id = ${plan}`);
  try {
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    await home(page);
    await openPanel(page);
    const foot = panel(page).locator('[data-testid="assistant-no-plan"]');
    await expect(foot).toContainText('Your plan does not include the assistant.');
    await shots(page, 'BASE-G122-no-plan');
    await page.setViewportSize({ width: 1440, height: 900 });
    await upgradeLandsInside(page, foot.locator('[data-testid="assistant-no-plan-upgrade"]'));
  } finally {
    saasSql(`update hubs_plan set assistant_messages_per_month = ${allowance} where id = ${plan}`);
  }
});

test('«Report a problem» sends the answer with its question and a reason', async ({ page }) => {
  await panelAtTheDesk(page);
  await ask(page, 'Hola');
  await panel(page).locator('[data-testid="assistant-report"]').last().click();
  const dialog = page.locator('ion-modal[data-testid="assistant-report-dialog"]');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Report this answer');
  await dialog.locator('[data-testid="assistant-report-reason-harmful"]').click();
  await dialog.locator('[data-testid="assistant-report-comment"] textarea').fill('No es lo que pregunté');
  await shots(page, 'BASE-G123', () => expect(dialog).toBeVisible());
  await page.setViewportSize({ width: 1440, height: 900 });
  const sent = page.waitForResponse((response) => response.url().endsWith('/api/assistant/report'));
  await dialog.locator('[data-testid="assistant-report-dialog-submit"]').click();
  const answered = await sent;
  expect(answered.status()).toBe(200);
  // flow: BASE-F105 (hub#870) — the «Hola» turn brought no pages of the web: the Hub closes it saying so
  // (`done.web`) and the chat sends it with the report, so erplora.com's support reads the answer even with its search on.
  expect(answered.request().postDataJSON()).toMatchObject({ reason: 'harmful', question: 'Hola', web: false });
  await expect(page.getByTestId('toast').filter({ hasText: 'Thank you, we have received your report.' }).first()).toBeVisible();
  await expect(dialog).toBeHidden();
});

test('without connection the foot says so; a cut or a service down says so in the answer, with «Try again»', async ({ page, context }) => {
  await panelAtTheDesk(page);
  await context.setOffline(true);
  await expect(panel(page).locator('[data-testid="assistant-offline"]')).toHaveText('No connection: you can write, and send when it is back.');
  await box(page).fill('Hola');
  await expect(panel(page).locator('[data-testid="assistant-send"] button')).toBeDisabled();
  await context.setOffline(false);
  await expect(panel(page).locator('[data-testid="assistant-offline"]')).toHaveCount(0);

  // The provider down: erplora.com says the assistant is not available; «Try again» asks the same again.
  await ask(page, 'E2E-DOWN');
  const failure = panel(page).locator('[data-testid="assistant-failure"]').last();
  await expect(failure).toContainText('The assistant is not available right now.');
  await expect(failure.locator('[data-testid="assistant-retry"]')).toBeVisible();
  await shots(page, 'BASE-G124');

  // The connection cut half-way: the Hub could not be reached.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/api/assistant/turn', (route) => route.abort('internetdisconnected'));
  await ask(page, 'Hola');
  await expect(panel(page).locator('[data-testid="assistant-failure"]').last()).toContainText('The assistant could not be reached.');
  await page.unroute('**/api/assistant/turn');
  await panel(page).locator('[data-testid="assistant-retry"]').last().click();
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
});

test.describe('dictation and files', () => {
  test('a file goes with the question; one it cannot read is refused; a dictation lands in the box and is not sent', async ({ page }) => {
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    await home(page);
    await openPanel(page);
    const input = panel(page).locator('[data-testid="assistant-attach-input"]');
    await input.setInputFiles([
      { name: 'notas.md', mimeType: '', buffer: Buffer.from('# Carta\n\nCafé 1,50 €') },
      { name: 'foto.heic', mimeType: 'image/heic', buffer: Buffer.from('x') },
    ]);
    await expect(panel(page).locator('[data-testid="assistant-file"]')).toHaveText(['notas.md']);
    await expect(panel(page).locator('[data-testid="assistant-composer-problem"]')).toHaveText(
      'foto.heic cannot be attached: images, PDF, Word, Excel, text or CSV.',
    );
    await ask(page, '¿Qué dice este archivo?');
    await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toContainText('notas.md');
    const asked = JSON.stringify(provider().seen.filter((s) => s.path === '/v1/chat/completions').at(-1)?.body);
    expect(asked).toContain('Café 1,50 €');

    // Dictation: the browser's fake microphone; erplora.com transcribes it with the e2e provider.
    const mic = panel(page).locator('[data-testid="assistant-mic"]');
    await mic.click();
    await expect(mic).toHaveAttribute('aria-pressed', 'true');
    await page.waitForTimeout(1200);
    const before = await answers(page).count();
    await mic.click();
    await expect(box(page)).toHaveValue(DICTATION);
    expect(await answers(page).count()).toBe(before);
    await shots(page, 'BASE-G112');
  });
});

test.describe('a copy of a business attached in the panel', () => {
  test('is offered by the attach button, loads with its card and the yes, and erplora.com only hears its name (BASE-F94)', async ({ page }) => {
    await login(page, A, '/');
    await page.setViewportSize({ width: 1440, height: 900 });
    // A copy of this business as Settings › Data › Export gives it.
    const copy = await api<{ content_base64: string }>(page.context(), A, 'GET', '/settings/data/export?name=Copia%20E2E&language=en&purpose=template');
    expect(copy.status).toBe(200);
    const name = 'copia-e2e.blueprint.zip';
    await home(page);
    await openPanel(page);
    const input = panel(page).locator('[data-testid="assistant-attach-input"]');
    expect((await input.getAttribute('accept'))?.split(',')).toEqual(expect.arrayContaining(['.zip', 'application/zip']));
    const larger = Buffer.alloc(20 * 1024 * 1024 + 1);
    await input.setInputFiles({ name: 'enorme.blueprint.zip', mimeType: 'application/zip', buffer: larger });
    await expect(panel(page).locator('[data-testid="assistant-composer-problem"]')).toHaveText(
      'The file could not be read: the file is larger than 20 MB.',
    );
    await input.setInputFiles({ name, mimeType: 'application/zip', buffer: Buffer.from(copy.data.content_base64, 'base64') });
    await expect(panel(page).locator('[data-testid="assistant-file"]')).toHaveText([name]);
    await shots(page, 'BASE-F94-copy-attached');

    await page.setViewportSize({ width: 1440, height: 900 });
    // Sent alone, and asked for in the next message: the panel still has the file it attached.
    await ask(page, '');
    await expect(panel(page).locator('[data-testid="assistant-bubble-user"]').last()).toContainText(name);
    await askForACard(page, `E2E-ASK base__blueprint__import {"file_base64":"${name}"}`);
    await expect(card(page)).toContainText(name);
    await shots(page, 'BASE-F94-copy-card', () => confirmationReady(page), () => confirmationSettled(page));
    await page.setViewportSize({ width: 1440, height: 900 });
    await confirmedWithTheWord(page);
    const sent = JSON.stringify(chats(provider()).map((seen) => seen.body));
    expect(sent).toContain(name);
    expect(sent).not.toContain(copy.data.content_base64);
  });
});

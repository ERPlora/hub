// The master QA of the Hub (BASE-G152, the old `qa-hub` contract, base/WORKBOOK.md BASE-F107), the platform's half,
// end to end with its real dependencies: this stack's SaaS (a fresh owner signs up on its screens and creates the
// business through its API, as the panel does) and its assistant gateway with the e2e's provider (assistant-provider.ts),
// no mock in between.
//   - §4, the precondition: a business of the restaurant vertical, created on erplora.com with its business type; the
//     Hub registers it with its vertical, offers that vertical's template first and loads it (its catalogue and tables).
//   - The platform from end to end, in 390, 834 and 1440 and in Spanish and English: Home (Summary and Activity, «My
//     apps», the bell, «Add apps» → Apps: BASE-F05), Apps (its three tabs), Settings (General, Business, Ticket, Data and
//     its sections), Employees (Staff, a person, Roles, API keys, Approvals), System (its five tabs), Files, My profile,
//     the page of an address that does not exist and the assistant, which opens and answers. Each screen loads with no
//     error (no console error, no uncaught one, no server error, no error state on view) and no text in the other
//     language nor a message key left on view (translations.ts, against the hub's own catalogues); captures
//     `APP-BASE-10-BASE-G152-<language>-<screen>-<width>`.
// The chains of the old contract's §5–§8 (the restaurant's and the salon's day, fiscal, printing) are flows of their
// apps with their own specs: base/WORKBOOK.md «Para quien lo mantiene», «La QA maestra del Hub».
// The SaaS of the stack needs its taxonomy (`seed_taxonomy`, as every deploy runs it) and the assistant's provider
// (README of this folder, «El asistente» and «La QA maestra»); the spec says which is missing.
// flow: BASE-G152 BASE-F05
import { execSync } from 'node:child_process';

import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { GREETING, type Provider, startProvider } from './assistant-provider';
import { api, compactBar, type Credentials, horizontalOverflow, HUB_DIR, login, MAIL_DIR, openApps, openBell, psql, REPO_DIR, SAAS, shot, shown, untilStill } from './helpers';
import { readMailCode } from './mail';
import { STACK } from './stack';
import { type Language, loadCatalog, normalText, rawKeys, wrongLanguage } from './translations';

test.use({ actionTimeout: 30_000 });
test.describe.configure({ mode: 'serial' });

const PASSWORD = 'Masa-madre-y-centeno-26';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
type Size = (typeof SIZES)[number];
const LANGUAGES: Language[] = ['es', 'en'];
/** What the SaaS's steps wait (its pushes to this Hub happen after its COMMIT). */
const SAAS_STEP = 30_000;
/** The side menu is pinned from 992 px; below it is a drawer behind the bar's menu button. */
const PINNED_MIN = 992;
/** The vertical of the QA's restaurant chain (§5): the business is created as one. */
const VERTICAL = 'restaurant';

const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
/** The SaaS's database of this stack (README «Varias ejecuciones a la vez»: `saas_e2e_<Hub port + 1>`). */
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

/** The hub's catalogues, `en` and `es`: what a text on screen is checked against. */
const CATALOG = loadCatalog(HUB_DIR);

interface Owner {
  context: BrowserContext;
  page: Page;
  credentials: Credentials;
}

let provider: Provider;
let owner: Owner;
let origin = '';
/** What the business holds as data, not as interface (its name, the template's name and description): never judged. */
const data = new Set<string>();

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, {
    cwd: REPO_DIR,
    encoding: 'utf8',
  }).trim();
}

/** A fresh account signed up on the SaaS's «Create account», its address proven with the mailed code; signed in. */
async function signUp(browser: Browser): Promise<Owner> {
  const credentials = { email: `e2e-qa-master-${Date.now()}@example.com`, password: PASSWORD };
  const context = await browser.newContext({ locale: 'en-US', viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${SAAS}/launch?tab=signup`);
  const form = page.getByTestId('login-form');
  await expect(page.getByTestId('login-submit')).toHaveText('Create account');
  await form.getByTestId('login-email').locator('input').fill(credentials.email);
  await form.getByTestId('login-password').locator('input').fill(credentials.password);
  const since = Date.now() - 50;
  await form.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/verify-email$/);
  const code = await readMailCode({ dir: MAIL_DIR, to: credentials.email, since, timeout: SAAS_STEP });
  await page.getByTestId('code').locator('input').fill(code);
  await page.getByTestId('verify-email-submit').click();
  await expect(page).toHaveURL(/\/launch$/);
  return { context, page, credentials };
}

/** A POST to the SaaS's API as `context`'s account, with the SaaS's CSRF token. */
async function saasPost(context: BrowserContext, path: string, body: unknown) {
  const host = new URL(SAAS).hostname;
  const csrf = (await context.cookies(SAAS)).find((c) => c.name === 'csrftoken' && c.domain === host)?.value;
  if (!csrf) throw new Error(`POST ${path}: no csrftoken of the SaaS (sign in first)`);
  return context.request.post(`${SAAS}/api${path}`, { headers: { 'X-CSRFToken': csrf }, data: body });
}

/** A business type of `vertical` from erplora.com's catalogue (its taxonomy, which every deploy seeds). */
async function businessTypeOf(context: BrowserContext, vertical: string): Promise<string> {
  const res = await context.request.get(`${SAAS}/api/catalog/business-types`);
  expect(res.status(), await res.text()).toBe(200);
  const { business_types: types } = (await res.json()) as { business_types: { code: string; vertical: string }[] };
  const type = types.find((candidate) => candidate.vertical === vertical);
  expect(type, `the SaaS ${SAAS} has no business type of the ${vertical} vertical: run its seed_taxonomy (README «La QA maestra»)`).toBeDefined();
  return type!.code;
}

// ── The screen as a person sees it ──

/**
 * Every text a person reads on the page: the visible text, in shadow roots too, and the names a control shows. Not
 * what the page writes as code (`<code>`, `<kbd>`, `<samp>`, `<pre>`): an identifier, such as an event's name in
 * System › Logs (BASE-F42), is the same in every language.
 */
function visibleTexts(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const texts: string[] = [];
    const shows = (el: Element) => el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
    const code = (el: Element) => el.closest('code, kbd, samp, pre') !== null;
    const visit = (root: Node) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
      for (let node: Node | null = walker.currentNode; node; node = walker.nextNode()) {
        if (node.nodeType === Node.TEXT_NODE) {
          const parent = node.parentElement;
          if (parent && node.textContent?.trim() && shows(parent) && !code(parent)) texts.push(node.textContent);
        } else if (node instanceof Element) {
          if (node.shadowRoot) visit(node.shadowRoot);
          if (!shows(node)) continue;
          for (const name of ['aria-label', 'placeholder', 'title', 'alt']) {
            const value = node.getAttribute(name);
            if (value?.trim()) texts.push(value);
          }
        }
      }
    };
    visit(document.body);
    return texts;
  });
}

interface Watch {
  console: string[];
  warnings: string[];
  errors: string[];
  server: string[];
}

/** What goes wrong on the page while the test walks: console errors, i18n warnings, uncaught errors, 5xx of the hub. */
function watch(page: Page): Watch {
  const seen: Watch = { console: [], warnings: [], errors: [], server: [] };
  page.on('console', (msg) => {
    if (new URL(page.url()).origin !== origin) return;
    if (msg.type() === 'error') seen.console.push(msg.text());
    if (msg.type() === 'warning' && msg.text().includes('[intlify]')) seen.warnings.push(msg.text());
  });
  page.on('pageerror', (error) => seen.errors.push(String(error)));
  page.on('response', (res) => {
    if (res.status() >= 500 && res.url().startsWith(origin)) seen.server.push(`${res.status()} ${res.url()}`);
  });
  return seen;
}

function clean(seen: Watch, where: string): void {
  expect(seen.console, `${where}: console errors`).toEqual([]);
  expect(seen.warnings, `${where}: missing translations`).toEqual([]);
  expect(seen.errors, `${where}: uncaught errors`).toEqual([]);
  expect(seen.server, `${where}: server errors`).toEqual([]);
}

/** The screen in view, settled: nothing loading, no error state, nothing animating, no sideways scroll. */
async function settled(page: Page, where: string): Promise<void> {
  await expect(page.locator('ion-skeleton-text:visible, [data-testid$="-loading"]:visible')).toHaveCount(0);
  await expect(page.locator('[data-testid$="-error"]:visible, [data-testid$="-load-error"]:visible'), `${where}: an error on view`).toHaveCount(0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${where}: no sideways scroll`).toBeLessThanOrEqual(0);
}

/** The screen checked in `language` and captured as `APP-BASE-10-BASE-G152-<language>-<screen>-<width>`. */
async function screen(page: Page, name: string, language: Language, size: Size): Promise<void> {
  const where = `${name} in ${language} at ${size.label}`;
  await settled(page, where);
  const texts = (await visibleTexts(page)).filter((text) => !data.has(normalText(text)));
  expect(wrongLanguage(texts, language, CATALOG), `${where}: texts in the other language`).toEqual([]);
  expect(rawKeys(texts), `${where}: message keys on view`).toEqual([]);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: shot(`APP-BASE-10-BASE-G152-${language}-${name}-${size.label}`) });
}

/** An entry of the side menu, as a person opens it: pinned from 992 px, otherwise from the bar's menu button. */
async function menu(page: Page, id: string, path: RegExp): Promise<void> {
  const width = page.viewportSize()!.width;
  const drawer = page.locator('ion-menu.dash-menu');
  if (width < PINNED_MIN) {
    await shown(page).locator('ion-menu-button').click();
    await expect(drawer).toHaveClass(/show-menu/);
  }
  await drawer.locator(`[data-testid="nav-${id}"]`).click();
  await expect(page).toHaveURL(path);
  if (width < PINNED_MIN) await expect(drawer).not.toHaveClass(/show-menu/);
}

/** A tab of the screen's tabbar (`tab-<id>`). */
async function tab(page: Page, id: string): Promise<void> {
  const button = shown(page).locator(`[data-testid="tab-${id}"]`);
  await button.click();
  await expect(button).toHaveClass(/segment-button-checked/);
}

/** The topbar's way to the assistant: the sparkles, or on a phone «More options» (the sparkles folded with the bell). */
async function openAssistant(page: Page): Promise<Locator> {
  const panel = page.locator('[data-testid="assistant-panel"]');
  if (compactBar(page)) {
    await shown(page).locator('[data-testid="topbar-chrome-more"]').click();
    await page.locator('ion-popover [data-testid="topbar-chrome-more-assistant"]').click();
  } else {
    await shown(page).locator('[data-testid="assistant-button"]').click();
  }
  await expect(panel).toHaveAttribute('data-open', 'true');
  return panel;
}

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
  owner = await signUp(browser);
});

test.afterAll(async () => {
  await provider?.close();
  await owner?.context.close();
});

test('BASE-G152 §4 — a restaurant created on erplora.com, its vertical in the Hub and its template loaded', async () => {
  test.setTimeout(240_000);
  // The business, as the panel creates it: a name, the country and its business type, of the restaurant vertical.
  const businessType = await businessTypeOf(owner.context, VERTICAL);
  const name = `QA ${Date.now().toString(36)}`;
  const created = await saasPost(owner.context, '/hubs/businesses', { name, country: 'ES', business_type: businessType });
  expect(created.status(), await created.text()).toBe(201);
  const business = (await created.json()) as { id: string; slug: string };
  data.add(name);
  // The Hub registered it with the SaaS's id and its vertical, and heard it is ready.
  await expect
    .poll(() => psql(`SELECT status || ' ' || vertical FROM base_hub WHERE id = '${business.id}'`), { timeout: SAAS_STEP })
    .toBe(`ready ${VERTICAL}`);
  origin = STACK.hub(business.slug);
  await login(owner.page, origin, '/', owner.credentials);

  // Its vertical's template comes first among those of its country, and loads: the restaurant's menu and tables.
  const catalogue = await api<{ templates: { key: string; name: string; description: string; vertical: string; country: string }[] }>(
    owner.context,
    origin,
    'GET',
    '/settings/data/blueprints',
  );
  expect(catalogue.status).toBe(200);
  const template = catalogue.data.templates[0];
  expect([template.vertical, template.country]).toEqual([VERTICAL, 'ES']);
  for (const each of catalogue.data.templates) {
    data.add(normalText(each.name));
    data.add(normalText(each.description));
  }
  const loaded = await api<{ status: string; report: { status: string } }>(owner.context, origin, 'POST', '/settings/data/blueprints/import', {
    template: template.key,
  });
  expect(loaded.status, JSON.stringify(loaded.data)).toBe(200);
  expect(loaded.data.report.status).toBe('complete');
  for (const list of ['/inventory/products', '/table/tables']) {
    const rows = await api<{ rows: unknown[] }>(owner.context, origin, 'GET', `${list}?limit=1&offset=0`);
    expect(rows.status, list).toBe(200);
    expect(rows.data.rows.length, `${list} after the template`).toBe(1);
  }
  await owner.page.goto(`${origin}/`);
  await settled(owner.page, 'Home after the template');
  await owner.page.screenshot({ path: shot('APP-BASE-10-BASE-G152-precondition-1440') });
});

for (const language of LANGUAGES) {
  for (const size of SIZES) {
    test(`BASE-G152 BASE-F05 — the platform end to end in ${language} at ${size.label}`, async () => {
      test.setTimeout(300_000);
      expect(origin, 'the business of §4').not.toBe('');
      const { context, page } = owner;
      await context.addCookies([{ name: 'django_language', value: language, domain: new URL(origin).hostname, path: '/' }]);
      await page.setViewportSize({ width: size.width, height: size.height });
      const seen = watch(page);
      const check = (name: string) => screen(page, name, language, size);

      // Home: Summary, then Activity; «My apps» and the bell over it.
      await page.goto(`${origin}/`);
      await expect(shown(page).locator('[data-testid="home-date"]')).toBeVisible();
      await expect(shown(page).locator('[data-testid="setup-card"]')).toHaveAttribute('aria-busy', 'false');
      await check('home');
      await tab(page, 'activity');
      await check('home-activity');
      await tab(page, 'summary');
      const launcher = await openApps(page);
      await check('apps-launcher');
      await launcher.locator('[data-testid="apps-launcher-close"]').click();
      await expect(launcher).toBeHidden();
      await openBell(page);
      await check('bell');
      await page.keyboard.press('Escape');
      await expect(page.locator('ion-popover [data-testid^="hub-bell-"]')).toHaveCount(0);

      // BASE-F05: «Add apps», the last tile of «My apps», leads to Apps.
      await shown(page).locator('[data-testid="home-my-apps-add"]').click();
      await expect(page).toHaveURL(`${origin}/apps`);
      await check('apps');
      await page.screenshot({ path: shot(`APP-BASE-10-BASE-F05-${language}-${size.label}`) });
      await tab(page, 'all');
      await check('apps-all');
      // BASE-F14 (hub#270, PLAN §32): «Paid» is only there when some app is sold apart; in this seed none is, so Apps
      // has «My apps» and «Add apps» and no «Paid».
      await expect(shown(page).locator('[data-testid="tab-mine"]')).toBeVisible();
      await expect(shown(page).locator('[data-testid="tab-paid"]')).toHaveCount(0);

      // Settings, its four tabs and the three sections of Data.
      await menu(page, 'settings', /\/settings/);
      for (const id of ['general', 'business', 'tickets', 'data']) {
        await tab(page, id);
        await check(`settings-${id}`);
      }
      for (const id of ['export', 'reset']) {
        await shown(page).locator(`[data-testid="data-section-${id}"]`).click();
        await expect(page).toHaveURL(new RegExp(`data=${id}#data$`));
        await check(`settings-data-${id}`);
      }

      // Employees: its staff, the owner's own page, then Roles, API keys and Approvals.
      await menu(page, 'employees', /\/employees/);
      const people = shown(page).locator('[data-testid="people-row"], [data-testid="people-card"]');
      await expect(people.first()).toBeVisible();
      // In a table row, the owner's name (their address until they give one) never runs under the «You» pill: it ends
      // in «…». A card, on a phone, breaks it into lines.
      const contained = await shown(page)
        .locator('[data-testid="people-row"] .people-name')
        .evaluateAll((names) =>
          names.every((el) => {
            const style = getComputedStyle(el);
            return el.scrollWidth <= el.clientWidth || (style.overflowX === 'hidden' && style.textOverflow === 'ellipsis');
          }),
        );
      expect(contained, `the owner's name runs out of its box at ${size.label}`).toBe(true);
      await check('employees');
      await people.first().click();
      await expect(page).toHaveURL(/\/employees\/[^/#?]+$/);
      await check('employees-person');
      await page.goBack();
      await expect(page).toHaveURL(/\/employees$/);
      for (const id of ['roles', 'apikeys', 'approvals']) {
        await tab(page, id);
        await check(`employees-${id}`);
      }

      // System, its five tabs.
      await menu(page, 'system', /\/system/);
      for (const id of ['resources', 'plan', 'updates', 'events', 'logs']) {
        await tab(page, id);
        await check(`system-${id}`);
      }

      // Files and My profile.
      await menu(page, 'files', /\/files/);
      await check('files');
      await page.goto(`${origin}/profile`);
      await check('profile');

      // An address that does not exist: the shell's own page, with its way home.
      await page.goto(`${origin}/this-address-does-not-exist`);
      await expect(shown(page).locator('[data-testid="not-found"]')).toBeVisible();
      await check('not-found');
      await shown(page).locator('[data-testid="not-found-home"]').click();
      await expect(page).toHaveURL(`${origin}/`);

      // The assistant opens and answers (the e2e's provider, behind erplora.com's gateway).
      const panel = await openAssistant(page);
      const box = panel.locator('[data-testid="assistant-input"] textarea');
      await expect(box).toBeVisible();
      await box.fill(language === 'es' ? 'Hola' : 'Hello');
      // «Send», as on a phone, where Enter breaks the line.
      await panel.locator('[data-testid="assistant-send"]').click();
      await expect(panel.locator('[data-testid="assistant-bubble-assistant"]').last()).toContainText(GREETING, { timeout: SAAS_STEP });
      await expect(panel.locator('[data-testid="assistant-send"]')).toBeVisible({ timeout: SAAS_STEP });
      data.add(GREETING);
      data.add(language === 'es' ? 'Hola' : 'Hello');
      await check('assistant');
      await panel.locator('[data-testid="assistant-close"]').click();
      await expect(panel).not.toHaveAttribute('data-open', 'true');

      clean(seen, `the platform in ${language} at ${size.label}`);
    });
  }
}

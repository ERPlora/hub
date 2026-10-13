// PoC §8.10, third pass: the PRODUCTION build (`pnpm --filter hub build`, served by WhiteNoise, no
// Vite) under the real production CSP — nonce + 'strict-dynamic' + `require-trusted-types-for
// 'script'` — in a visible Chrome. DEBUG never enforces Trusted Types (`live.csp.debug_policy`), so
// this is the only place the `default` policy of `packages/ui/src/shell/boot/trusted-types.boot.ts`
// meets the icons (`ionicons/icons` data URLs) for real.
//
// It drives a second, production-like Hub (DEBUG=0, daphne as in the Dockerfile) on
// `http://a.localhost:8002` (override with PROD_ORIGIN); the command that starts it is in
// `docs/plans/2026-10-13-fase-1-poc-navegador.md` («Tercera pasada»). The SaaS sends its one-time
// code to the dev Hub's `/auth/callback` (`a.localhost:8000`, pinned by the SaaS's settings), so the
// login runs there; cookies ignore ports and both Hubs share the database and the SECRET_KEY, so the
// session is also valid on :8002. Without that server the spec is skipped, so the dev suite
// (`pnpm --filter hub e2e`) does not depend on it.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import { A, ARTIFACTS, createItem, listReady, login, rowOf, shown, uniqueName } from './helpers';

const PROD = (process.env.PROD_ORIGIN ?? 'http://a.localhost:8002').replace(/\/$/, '');
const OUT = join(ARTIFACTS, 'prod');
const ICONIFY_HOSTS = /iconify|simplesvg\.com|unisvg\.com/i;
const CSP_TEXT = /content security policy|trusted ?type|trustedhtml|trustedscript|refused to/i;

const shotPath = (name: string): string => {
  mkdirSync(OUT, { recursive: true });
  return join(OUT, `${name}.png`);
};
const save = (name: string, data: unknown): void => {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, `${name}.json`), `${JSON.stringify(data, null, 2)}\n`);
};

type TtCall = { policy: string; sink: string; ok: boolean; sample: string; error?: string };
type Watch = {
  cspConsole: string[];
  consoleErrors: string[];
  pageErrors: string[];
  reports: string[];
  iconify: string[];
  iconUrlFetches: string[];
  crossOrigin: string[];
  failed: { url: string; error: string }[];
  abortedStreams: string[];
  badStatus: { url: string; status: number }[];
  violations: (page: Page) => Promise<unknown[]>;
  ttCalls: (page: Page) => Promise<TtCall[]>;
};

/** Listeners for everything that must stay at zero, installed before the first document. Besides the
 *  `securitypolicyviolation` event it wraps `trustedTypes.createPolicy` (transparently: same rules,
 *  same answers) to record every string that reaches a policy, accepted or rejected. */
async function watch(page: Page): Promise<Watch> {
  const origin = new URL(PROD).origin;
  const w: Omit<Watch, 'violations' | 'ttCalls'> = {
    cspConsole: [],
    consoleErrors: [],
    pageErrors: [],
    reports: [],
    iconify: [],
    iconUrlFetches: [],
    crossOrigin: [],
    failed: [],
    abortedStreams: [],
    badStatus: [],
  };
  page.on('console', (msg) => {
    if (CSP_TEXT.test(msg.text())) w.cspConsole.push(msg.text());
    if (msg.type() === 'error') w.consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => w.pageErrors.push(String(err)));
  page.on('request', (req) => {
    const url = req.url();
    if (url.startsWith('data:') || url.startsWith('blob:')) return;
    if (url.includes('/csp-report/')) w.reports.push(req.postData() ?? '');
    if (ICONIFY_HOSTS.test(new URL(url).hostname)) w.iconify.push(url);
    if (url.includes('%3Csvg') || url.includes('<svg')) w.iconUrlFetches.push(url.slice(0, 120));
    if (new URL(url).origin !== origin) w.crossOrigin.push(url);
  });
  page.on('requestfailed', (req) => {
    const error = req.failure()?.errorText ?? 'failed';
    // Leaving a screen (or changing its subscriptions) closes its live stream on purpose.
    if (req.url().includes('/api/live') && error === 'net::ERR_ABORTED') w.abortedStreams.push(req.url().slice(0, 60));
    else w.failed.push({ url: req.url(), error });
  });
  page.on('response', (res) => {
    if (res.status() >= 400) w.badStatus.push({ url: res.url(), status: res.status() });
  });
  await page.addInitScript(() => {
    const g = window as unknown as {
      __csp: unknown[];
      __tt: { policy: string; sink: string; ok: boolean; sample: string; error?: string }[];
      trustedTypes?: { createPolicy: (name: string, rules: Record<string, (s: string, ...a: unknown[]) => string>) => unknown };
    };
    g.__csp = [];
    g.__tt = [];
    document.addEventListener('securitypolicyviolation', (e) =>
      g.__csp.push({ directive: e.violatedDirective, blocked: e.blockedURI, sample: e.sample, source: e.sourceFile, line: e.lineNumber }),
    );
    const tt = g.trustedTypes;
    if (!tt) return;
    const create = tt.createPolicy.bind(tt);
    tt.createPolicy = (name, rules) => {
      const wrapped: Record<string, (s: string, ...a: unknown[]) => string> = {};
      for (const [sink, rule] of Object.entries(rules)) {
        wrapped[sink] = (s: string, ...rest: unknown[]) => {
          try {
            const out = rule(s, ...rest);
            g.__tt.push({ policy: name, sink, ok: true, sample: String(s).slice(0, 90) });
            return out;
          } catch (error) {
            g.__tt.push({ policy: name, sink, ok: false, sample: String(s).slice(0, 300), error: String(error) });
            throw error;
          }
        };
      }
      return create(name, wrapped);
    };
  });
  return {
    ...w,
    violations: (p) => p.evaluate(() => (window as unknown as { __csp?: unknown[] }).__csp ?? []),
    ttCalls: (p) => p.evaluate(() => (window as unknown as { __tt?: TtCall[] }).__tt ?? []),
  };
}

type IconState = { where: string; name: string; host: string; painted: boolean; size: string };

/** Every visible `ion-icon` (light DOM and shadow roots) and whether it painted a sized `<svg>`. */
async function icons(page: Page, where: string): Promise<IconState[]> {
  const found = await page.evaluate(() => {
    const out: { name: string; host: string; painted: boolean; size: string }[] = [];
    const walk = (root: Document | ShadowRoot) => {
      for (const el of root.querySelectorAll('*')) {
        if (el.tagName === 'ION-ICON' && (el as HTMLElement).checkVisibility({ visibilityProperty: true, opacityProperty: false })) {
          const box = el.getBoundingClientRect();
          if (box.width > 0 && box.height > 0) {
            const svg = el.shadowRoot?.querySelector('svg');
            const svgBox = svg?.getBoundingClientRect();
            out.push({
              name: el.getAttribute('name') ?? el.getAttribute('aria-label') ?? '(icon prop)',
              host: ((el.getRootNode() as ShadowRoot).host ?? el.parentElement)?.tagName.toLowerCase() ?? '',
              painted: !!svg && !!svgBox && svgBox.width > 0 && svgBox.height > 0 && svg.childElementCount > 0,
              size: `${Math.round(svgBox?.width ?? 0)}x${Math.round(svgBox?.height ?? 0)}`,
            });
          }
        }
        if (el.shadowRoot) walk(el.shadowRoot);
      }
    };
    walk(document);
    return out;
  });
  return found.map((icon) => ({ where, ...icon }));
}

let context: BrowserContext;

test.beforeAll(async ({ browser }) => {
  const health = new URL('/healthz', PROD);
  health.hostname = '127.0.0.1'; // answered before the Host is validated; Node may not resolve *.localhost
  const up = await fetch(health, { signal: AbortSignal.timeout(2000) }).then(
    (res) => res.ok,
    () => false,
  );
  test.skip(!up, `no production-like Hub on ${PROD}: start it as the PoC doc says («Tercera pasada»)`);
  context = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await context.newPage();
  await login(page, A); // the SaaS's callback is the dev Hub's; the session cookie is a.localhost's
  await page.close();
});

test.afterAll(async () => {
  await context?.close();
});

test('production build: CSP with nonce, strict-dynamic and Trusted Types enforced; zero violations on list, detail, edit, delete alert and new; every icon painted; no request off-origin', async () => {
  const page = await context.newPage();
  const w = await watch(page);
  const item = await createItem(context, PROD, uniqueName('Prod CSP'));

  // The document: production CSP header, built assets (no Vite), every <script> with the nonce.
  const response = await page.goto(`${PROD}/demo/items`);
  expect(response?.status()).toBe(200);
  expect(new URL(page.url()).origin).toBe(new URL(PROD).origin); // the session is valid on the prod Hub
  const header = response?.headers()['content-security-policy'] ?? '';
  const html = (await response?.text()) ?? '';
  const nonce = /'nonce-([A-Za-z0-9_+/=-]+)'/.exec(header)?.[1] ?? '';
  const scriptTags = html.match(/<script\b[^>]*>/g) ?? [];
  const domScriptNonces = await page.evaluate(() => [...document.querySelectorAll('script')].map((s) => s.nonce || '(none)'));
  await listReady(page);
  await page.waitForTimeout(500);
  const all: IconState[] = [...(await icons(page, 'shell+list'))];
  await page.screenshot({ path: shotPath('01-list-1280') });

  // Detail → delete alert (cancel) → edit and save → back on detail.
  await rowOf(page, item.id).click();
  await expect(shown(page).locator('[data-testid=demo-detail-status]')).toBeVisible();
  all.push(...(await icons(page, 'detail')));
  await page.screenshot({ path: shotPath('02-detail-1280') });
  await shown(page).locator('[data-testid=demo-detail-delete]').click();
  await expect(page.locator('ion-alert')).toBeVisible();
  await page.screenshot({ path: shotPath('03-delete-alert-1280') });
  await page.locator('ion-alert button', { hasText: 'Cancel' }).click();
  await expect(page.locator('ion-alert')).toBeHidden();
  await shown(page).locator('[data-testid=demo-detail-edit]').click();
  const nameInput = shown(page).locator('[data-testid=demo-form-name] input');
  await expect(nameInput).toHaveValue(item.name);
  all.push(...(await icons(page, 'edit')));
  await page.screenshot({ path: shotPath('04-edit-1280') });
  const renamed = `${item.name} (edited)`;
  await nameInput.fill(renamed);
  await shown(page).locator('[data-testid=demo-form-save]').click();
  await expect(page).toHaveURL(new RegExp(`/demo/items/${item.id}$`));
  await expect(shown(page).getByText(renamed, { exact: true }).first()).toBeVisible();

  // Back to the list → «New item» → create → back on the list with the new row.
  await shown(page).locator('[data-testid=topbar-back]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await shown(page).locator('[data-testid=demo-items-add]').click();
  await expect(shown(page).locator('[data-testid=demo-form]')).toBeVisible();
  all.push(...(await icons(page, 'new')));
  await page.screenshot({ path: shotPath('05-new-1280') });
  const created = uniqueName('Prod new');
  await shown(page).locator('[data-testid=demo-form-name] input').fill(created);
  await shown(page).locator('[data-testid=demo-form-save]').click();
  await expect(page).toHaveURL(/\/demo\/items$/);
  await expect(shown(page).getByText(created, { exact: true }).first()).toBeVisible();

  // Phone: the menu button and the drawer.
  await page.setViewportSize({ width: 390, height: 844 });
  await listReady(page);
  await shown(page).locator('ion-menu-button').click();
  await expect(page.locator('ion-menu')).toHaveClass(/show-menu/);
  await page.waitForTimeout(400);
  all.push(...(await icons(page, 'phone menu')));
  await page.screenshot({ path: shotPath('06-phone-menu-390') });
  await page.waitForTimeout(1500); // late violations, icons and requests

  const violations = await w.violations(page);
  const ttCalls = await w.ttCalls(page);
  const navigations = await page.evaluate(() => performance.getEntriesByType('navigation').length);
  const empty = all.filter((i) => !i.painted);
  save('walk', {
    origin: PROD,
    header,
    scriptTags,
    domScriptNonces,
    oneDocument: navigations === 1,
    icons: {
      checked: all.length,
      perScreen: Object.fromEntries([...new Set(all.map((i) => i.where))].map((s) => [s, all.filter((i) => i.where === s).length])),
      names: [...new Set(all.map((i) => i.name))],
      sizes: [...new Set(all.map((i) => i.size))],
      empty,
    },
    trustedTypes: {
      calls: ttCalls.length,
      byPolicy: Object.fromEntries([...new Set(ttCalls.map((c) => `${c.policy}.${c.sink}`))].map((k) => [k, ttCalls.filter((c) => `${c.policy}.${c.sink}` === k).length])),
      shapes: [...new Set(ttCalls.map((c) => c.sample.slice(0, 26)))],
      rejected: ttCalls.filter((c) => !c.ok),
    },
    violations,
    cspConsole: w.cspConsole,
    consoleErrors: w.consoleErrors,
    pageErrors: w.pageErrors,
    reports: w.reports,
    iconify: w.iconify,
    iconUrlFetches: w.iconUrlFetches,
    crossOrigin: w.crossOrigin,
    failed: w.failed,
    abortedStreams: w.abortedStreams.length,
    badStatus: w.badStatus,
  });

  // The policy really is production's.
  expect(header).toMatch(/script-src [^;]*'nonce-[A-Za-z0-9_+/=-]+'/);
  expect(header).toContain("'strict-dynamic'");
  expect(header).toContain("require-trusted-types-for 'script'");
  expect(header).toMatch(/trusted-types default/);
  expect(header).not.toContain('5173');
  expect(html).not.toContain('5173');
  expect(html).not.toContain('@vite/client');
  expect(html).toMatch(/<script type="module" src="\/static\/spa\/assets\/main-[^"]+\.js"/);
  expect(scriptTags.length).toBeGreaterThan(0);
  expect(scriptTags.filter((tag) => !tag.includes(`nonce="${nonce}"`))).toEqual([]);
  expect(domScriptNonces.every((n) => n === nonce)).toBe(true);
  expect(navigations).toBe(1);

  // Zero violations, zero Trusted Types rejections, zero errors.
  expect(violations).toEqual([]);
  expect(ttCalls.filter((c) => !c.ok)).toEqual([]);
  expect(w.cspConsole).toEqual([]);
  expect(w.reports).toEqual([]);
  expect(w.pageErrors).toEqual([]);
  expect(w.consoleErrors).toEqual([]);

  // Icons: painted, none fetched, nothing off-origin, nothing failed.
  expect(all.length).toBeGreaterThan(10);
  expect(empty).toEqual([]);
  expect(ttCalls.some((c) => c.policy === 'default' && c.sink === 'createHTML' && c.sample.startsWith('data:image/svg+xml;utf8,<svg'))).toBe(true);
  expect(w.iconify).toEqual([]);
  expect(w.iconUrlFetches).toEqual([]);
  expect(w.crossOrigin).toEqual([]);
  expect(w.failed).toEqual([]);
  expect(w.badStatus).toEqual([]);
  await page.close();
});

test('positive control: Trusted Types is enforced on the production page (an HTML string throws and the listener sees it)', async () => {
  const page = await context.newPage();
  const w = await watch(page);
  // Before any page script, with no `default` policy yet: the bare CSP must refuse the string.
  await page.addInitScript(() => {
    const g = window as unknown as { __probe: unknown };
    try {
      document.createElement('div').innerHTML = '<div>x</div>';
      g.__probe = { threw: false };
    } catch (error) {
      g.__probe = { threw: true, error: String(error) };
    }
  });
  await page.goto(`${PROD}/demo/items`);
  await listReady(page);
  const early = await page.evaluate(() => (window as unknown as { __probe: { threw: boolean; error?: string } }).__probe);

  // After the app booted, with the `default` policy in place: what it lets through and what not.
  const late = await page.evaluate(() => {
    const attempt = (run: () => void): { threw: boolean; error?: string } => {
      try {
        run();
        return { threw: false };
      } catch (error) {
        return { threw: true, error: String(error) };
      }
    };
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="M0 0h1v1z"/></svg>';
    return {
      bodyDiv: attempt(() => {
        document.body.innerHTML = '<div>x</div>';
      }),
      svgMarkup: attempt(() => {
        document.createElement('div').innerHTML = svg;
      }),
      parseSvgDataUrl: attempt(() => {
        new DOMParser().parseFromString(`data:image/svg+xml;utf8,${svg}`, 'text/html');
      }),
      parseDiv: attempt(() => {
        new DOMParser().parseFromString('<div>x</div>', 'text/html');
      }),
      appStillThere: !!document.querySelector('ion-app'),
    };
  });
  await page.waitForTimeout(500);
  const violations = (await w.violations(page)) as { directive: string }[];
  const ttCalls = await w.ttCalls(page);
  await page.screenshot({ path: shotPath('07-positive-control') });
  save('positive-control', { early, late, violations, rejected: ttCalls.filter((c) => !c.ok), cspConsole: w.cspConsole });

  expect(early.threw).toBe(true);
  expect(late.bodyDiv.threw).toBe(true);
  expect(late.appStillThere).toBe(true);
  expect(late.parseDiv.threw).toBe(true);
  expect(late.svgMarkup.threw).toBe(false);
  expect(late.parseSvgDataUrl.threw).toBe(false);
  // The same listeners the walk relies on do catch a Trusted Types violation.
  expect(violations.some((v) => v.directive === 'require-trusted-types-for')).toBe(true);
  expect(ttCalls.filter((c) => !c.ok).map((c) => c.sample)).toEqual(expect.arrayContaining(['<div>x</div>']));
  await page.close();
});

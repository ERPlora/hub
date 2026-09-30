// Regression test for ERPlora/hub#2436 — Settings › Business: the explanation under «Use these
// details for my ERPlora invoice too» was cut off with an ellipsis on a tablet and a narrow desktop
// («…Déjala sin marca»), hiding exactly the part that tells you when NOT to tick it (someone else,
// such as your accounting firm, pays ERPlora).
//
// Why a bench spec: the cut is layout — the label box of a real `ion-checkbox` in a real browser,
// in both Ionic modes. A simulated Ionic has no widths to measure (the lesson of hub#2040), and
// `ui-clip-sweep` does not see it either: an ellipsis does not overflow its box.
import { request as pwRequest } from '@playwright/test';
import { test, expect, type Page } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

const RUNTIME = process.env.HUB_RUNTIME_URL ?? 'http://127.0.0.1:8787';

/** How the explanation starts in each language, to know the bench really painted that language. */
const OPENING: Record<string, string> = { en: 'When you save,', es: 'Al guardar,' };

type Session = Awaited<ReturnType<typeof loginByPin>>;

/**
 * Saves the viewer's own language, exactly as the Profile screen does (`PUT /api/profile`): the
 * shell speaks the PROFILE language, not the browser's. `null` gives the bench back its default.
 */
async function setProfileLanguage(session: Session, language: string | null): Promise<void> {
  const api = await pwRequest.newContext();
  const headers = { 'x-hub-session': session.token };
  const got = await api.get(`${RUNTIME}/api/profile`, { headers });
  expect(got.ok(), `could not read the profile: ${got.status()}`).toBeTruthy();
  const profile = (await got.json()) as { first_name: string; last_name: string; email: string };
  const put = await api.put(`${RUNTIME}/api/profile`, {
    headers,
    data: {
      first_name: profile.first_name,
      last_name: profile.last_name,
      email: profile.email,
      preferences: { language, theme_mode: null, theme_palette: null },
    },
  });
  expect(put.ok(), `could not save the profile language: ${put.status()} ${await put.text()}`).toBeTruthy();
  await api.dispose();
}

let session: Session | null = null;

// Every spec of the run shares ONE bench hub: the language this spec saves goes back.
test.afterEach(async () => {
  if (session) await setProfileLanguage(session, null);
  session = null;
});

/**
 * The shell pins `mode: 'ios'` (main.ts) and Ionic ignores `?ionic:mode=` over it, so `md` is
 * reached by swapping that one literal in the module Vite serves (as `TabbarWholeWords` does).
 */
async function forceMaterialMode(page: Page): Promise<void> {
  await page.route(/\/src\/main\.ts(\?.*)?$/, async (route) => {
    const res = await route.fetch();
    const body = (await res.text()).replace(/mode: (['"])ios\1, swipeBackEnabled/, 'mode: "md", swipeBackEnabled');
    expect(body, 'main.ts still sets the Ionic mode in one literal').toContain('mode: "md", swipeBackEnabled');
    await route.fulfill({ response: res, body });
  });
}

interface ExplanationBox {
  mode: string | null;
  text: string;
  /** Some box between the text and the checkbox hides what does not fit (ellipsis or clip). */
  clippedBy: string | null;
  lines: number;
  right: number;
  itemRight: number;
}

async function measureExplanation(page: Page): Promise<ExplanationBox> {
  return page.evaluate(() => {
    const box = document.querySelector('[data-testid="settings-share-with-erplora"]');
    const p = box?.querySelector('ion-label p');
    const item = box?.closest('ion-item');
    if (!box || !p || !item) throw new Error('the ERPlora-invoice box is not on screen');
    // Walk from the text up to the checkbox, crossing into its shadow DOM through the slot the
    // label is assigned to: any of those boxes can be the one that cuts it.
    const chain: Element[] = [p, p.closest('ion-label') as Element];
    let slot = (p.closest('ion-label') as Element).assignedSlot as Element | null;
    while (slot && slot !== box) {
      chain.push(slot);
      slot = (slot.parentElement ?? ((slot.getRootNode() as ShadowRoot).host as Element | null)) as Element | null;
    }
    let clippedBy: string | null = null;
    for (const el of chain) {
      if (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1) {
        const cs = getComputedStyle(el);
        if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
          clippedBy = `${el.tagName.toLowerCase()}.${el.className || ''} (${el.scrollWidth}x${el.scrollHeight} in ${el.clientWidth}x${el.clientHeight})`;
          break;
        }
      }
    }
    const r = p.getBoundingClientRect();
    const lineHeight = parseFloat(getComputedStyle(p).lineHeight) || 16;
    return {
      mode: document.documentElement.getAttribute('mode'),
      text: (p.textContent ?? '').trim(),
      clippedBy,
      lines: Math.round(r.height / lineHeight),
      right: r.right,
      itemRight: item.getBoundingClientRect().right,
    };
  });
}

for (const locale of ['en', 'es'] as const) {
  test.describe(`${locale}`, () => {
    for (const mode of ['ios', 'md'] as const) {
      test(`${mode}: the explanation of the ERPlora-invoice box is read whole, wrapped, at the three widths (hub#2436)`, async ({
        page,
      }) => {
        if (mode === 'md') await forceMaterialMode(page);
        session = await loginByPin();
        await setProfileLanguage(session, locale);
        await withSession(page, session);
        await page.setViewportSize(VIEWPORTS[0]);
        await page.goto('/settings#business');
        await expect(page.getByTestId('settings-share-with-erplora')).toBeVisible();

        for (const viewport of VIEWPORTS) {
          await page.setViewportSize(viewport);
          await expect(page.getByTestId('settings-share-with-erplora')).toBeVisible();
          const m = await measureExplanation(page);
          const at = `${mode} ${locale} ${viewport.width}x${viewport.height}`;
          expect(m.mode, `the bench really paints ${mode}`).toBe(mode);
          expect(m.text.startsWith(OPENING[locale]), `${at}: the explanation is in ${locale} («${m.text}»)`).toBe(true);
          expect(m.clippedBy, `${at}: the explanation is cut off by ${m.clippedBy}`).toBeNull();
          // ~250 characters never fit in one line of the Business card: seeing it whole means wrapped.
          expect(m.lines, `${at}: the explanation wraps onto several lines`).toBeGreaterThan(1);
          expect(m.right, `${at}: the explanation stays inside its row`).toBeLessThanOrEqual(m.itemRight + 1);
        }
      });
    }
  });
}

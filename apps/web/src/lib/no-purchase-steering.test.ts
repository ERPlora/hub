import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

// ANTI-STEERING (hub#479) — the Hub does NOT sell, and it does not point at selling either.
//
// Google Play's payments policy and Microsoft Store's 10.8.1 have two halves. The first ("if you
// charge inside, use our billing") we meet by design: there is no gateway in the till. The second
// is ANTI-STEERING — linking from inside the app to a payment method outside it. That half opened
// up in the EU (DMA) and the US (Epic v. Google), but PER JURISDICTION and with conditions that
// move; a listing rejected on it is not discovered until submission and blocks the whole release.
//
// Ioan's decision (2026-08-08, hub#479) does not navigate that maze — it removes the ground under
// it: buying and upgrading happen on erplora.com, in a browser, and the app carries NO control that
// leads there. With no link to regulate, the policy has nothing to apply to. That reason does not
// expire with the next policy change, which is exactly why it was chosen over "the EU allows it".
//
// This guard reads the SOURCE (the convention of `PlanLimitsPanel.test.ts`, `system-tabs.test.ts`),
// not a mounted tree, because the defect class is "a NEW button appears one day and nobody links it
// to a store rejection six weeks later". A per-component assertion only covers the buttons we knew
// about; this covers the ones we have not written yet.
//
// ⚠️ This is about the HUB only. The SaaS keeps every one of these pages and its checkout untouched
// — that is where ERPlora sells. What is forbidden is the Hub REACHING them.
const SRC = fileURLToPath(new URL('..', import.meta.url));

/**
 * Cloud addresses that land the user somewhere a payment can be made — verified against the SaaS,
 * by what the page actually renders, not by what the Hub's button is labelled:
 *
 *  - `/dashboard/marketplace/plans/`   → changes plan with proration on the saved card (`hx-post`
 *                                        to `hubs:change_plan`), no checkout page, no leaving.
 *  - `/dashboard/marketplace/modules/` → the module listing, where its subscription is bought.
 *  - `/dashboard/billing/`             → invoices AND the Stripe Connect onboarding banner.
 *
 * The account page and `/app/download/` are deliberately absent: neither can take money, so neither
 * is steering — the account page on the condition that it is asked for as the account surface
 * (hub#1900, below). The update channel (hub#400) rides on `/app/download/` and must keep working.
 */
const PAYMENT_ROUTES = [
  '/dashboard/marketplace/plans',
  '/dashboard/marketplace/modules',
  '/dashboard/billing',
];

/** Every source file the app ships, minus the tests that describe it. */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      out.push(...sourceFiles(path));
      continue;
    }
    if (!/\.(ts|vue)$/.test(entry)) continue;
    if (/\.test\.ts$/.test(entry)) continue;
    out.push(path);
  }
  return out;
}

describe('anti-steering: the Hub carries no route to a page that can take money', () => {
  it('no shipped source builds a Cloud URL that lands on a payment surface', () => {
    const offenders: string[] = [];

    for (const path of sourceFiles(SRC)) {
      const source = readFileSync(path, 'utf8');
      for (const route of PAYMENT_ROUTES) {
        if (!source.includes(route)) continue;
        const line = source.split('\n').findIndex((l) => l.includes(route)) + 1;
        offenders.push(`${path.slice(SRC.length)}:${line} → ${route}`);
      }
    }

    // Named one per line: when this fails, the message IS the list of controls to deal with.
    expect(offenders.join('\n')).toBe('');
  });

  // hub#1897 — the OTHER half of the sweep, and the one that let a door back in.
  //
  // The list above is literal on purpose, and that literalness is also its blind spot: a control
  // that opens `/dashboard/` matches none of the three routes, and yet that panel carries «Billing»
  // and «Marketplace» in its own sidebar — one tap from a payment surface, with the session already
  // open because the Hub hands the browser a one-time pass (pm#196). The QA measured three taps
  // from the till to `/dashboard/billing/invoices/` on the published v1.1.25.
  //
  // So the rule this guard adds is not about ROUTES but about DOORS: every place that leaves for
  // the signed-in SaaS through `saasDoor` has to consult who distributed this copy, because that is
  // who sets the rule (`planUpgradeIsOfferable`, hub#756; `managementIsOfferable`, hub#1897). The
  // browser and a sideloaded install keep every door — nobody governs them.
  // 🪤 The CALL is required, not the bare name: `managementIsOfferable` written in prose that
  // explains the rule satisfies an `includes` and lets the file through. Verified by mutation —
  // renaming the gate in `management-link.ts`, with the loose assertion the mutant SURVIVED
  // because its own comment names the sibling.
  const DISTRIBUTION_GATES = /(?:planUpgradeIsOfferable|managementIsOfferable)\(/;

  /**
   * The person's own account, asked for WITHOUT the panel around it (hub#1900): the SaaS paints it
   * with no sidebar, so «Billing» and «Marketplace» are not one tap away.
   *
   * This is the line Google Play's payments FAQ draws, word for word: an app may send people to
   * "administrative information – like an account management page […] as long as the webpage does
   * not eventually lead to an alternate payment method". The bare account page failed the second
   * half, because it is painted inside the panel. And the door could not simply be taken out of the
   * Play copy either: the app lets people sign up, so Play also requires an in-app path to DELETE
   * that account — and deleting it lives on this page. So the door stays in every copy, and what it
   * asks for is the account alone.
   */
  const ACCOUNT_SURFACE = '/dashboard/profile/?surface=account';

  /** An address of the SaaS panel written in code — every page under it carries the panel's menu. */
  const PANEL_ADDRESS = /(?:[`'"}]|erplora\.com)(\/dashboard\/[^`'"\s]*)/g;

  /**
   * The ways out that are NOT filtered by distribution, each with what it opens: the reason it
   * cannot take money. Being listed is not a pass on its own — the file has to keep reaching that
   * destination, and any panel address it writes has to be the account surface.
   */
  const DOORS_THAT_CANNOT_TAKE_MONEY: Record<string, string> = {
    // The person's own account (hub#1539, hub#1900).
    'views/ProfilePage.vue': ACCOUNT_SURFACE,
    // The installer and the update channel (hub#480, hub#400): `/app/download/`, which turns into
    // the store listing itself once the app is published.
    'views/SystemPage.vue': 'appDownloadUrl(',
    'components/SidebarAppUpdate.vue': 'appUpdateDestination',
  };

  /** The modules that DEFINE the ways out; naming them is not walking through them. */
  const DOORS_THEMSELVES = ['lib/saas-door.ts', 'lib/open-external.ts'];

  /**
   * Every way this app has of opening a page outside the till (hub#1900). The rule used to look at
   * `saasDoor` alone, so a plain `openExternal` of a panel address — the one a shift session takes
   * on «Mi perfil» — was never looked at.
   */
  const WAY_OUT = /\b(?:saasDoor|openExternal|window\.open)\(/;

  it('every way out of the till asks who distributed this copy, or cannot take money', () => {
    const offenders: string[] = [];

    for (const path of sourceFiles(SRC)) {
      const relative = path.slice(SRC.length);
      if (DOORS_THEMSELVES.includes(relative)) continue;

      const source = readFileSync(path, 'utf8');
      if (!WAY_OUT.test(source)) continue;
      if (DISTRIBUTION_GATES.test(source)) continue;

      const line = source.split('\n').findIndex((l) => WAY_OUT.test(l)) + 1;
      const reaches = DOORS_THAT_CANNOT_TAKE_MONEY[relative];
      if (reaches === undefined) {
        offenders.push(`${relative}:${line} → leaves the till without a distribution gate`);
        continue;
      }
      if (!source.includes(reaches)) {
        offenders.push(`${relative}:${line} → no longer reaches ${reaches}, its reason to be ungated`);
      }
      for (const [, address] of source.matchAll(PANEL_ADDRESS)) {
        if (address !== ACCOUNT_SURFACE) {
          offenders.push(`${relative} → ${address} is the panel, and this door has no distribution gate`);
        }
      }
    }

    expect(offenders.join('\n')).toBe('');
  });

  it('keeps the doors that cannot take money — the update channel above all', () => {
    // hub#400: the installed app learns about a new version through `/app/download/<platform>/`,
    // a 302 in the Cloud that becomes the STORE listing once the app is published. Sweeping the
    // purchase links out must not take this with it, or the fleet goes orphaned — the very thing
    // that had to be fixed BEFORE publishing.
    const appUpdate = readFileSync(join(SRC, 'lib/app-update.ts'), 'utf8');
    expect(appUpdate).toContain('/app/download/');
  });
});

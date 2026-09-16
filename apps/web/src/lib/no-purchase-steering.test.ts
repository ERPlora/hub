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
 * `/dashboard/profile/` and `/app/download/` are deliberately absent: neither can take money, so
 * neither is steering. The update channel (hub#400) rides on `/app/download/` and must keep working.
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
  // 🪤 Se exige la LLAMADA, no el nombre suelto: `managementIsOfferable` escrito en una prosa que
  // explica la regla satisface un `includes` y deja pasar el fichero. Comprobado mutando —
  // renombrando la reja de `management-link.ts`, con la aserción floja el mutante SOBREVIVÍA
  // porque su propio comentario nombra a la hermana.
  const DISTRIBUTION_GATES = /(?:planUpgradeIsOfferable|managementIsOfferable)\(/;

  /**
   * The door that is deliberately NOT filtered, and the issue that will decide whether it stays so.
   *
   * `ProfilePage` leaves for `/dashboard/profile/` — the person's own account, which hub#479
   * classified as "cannot take money" and kept. It lands on the same dashboard chrome as the panel
   * above, so the question it raises is real; it is NOT answered here, because the Play copy would
   * otherwise be left with no door to erplora.com at all. Tracked in hub#1900.
   */
  const UNGATED_BY_DECISION = ['views/ProfilePage.vue'];

  /** The module that DEFINES the door; naming it is not walking through it. */
  const DOOR_ITSELF = 'lib/saas-door.ts';

  it('every door out to the signed-in SaaS asks who distributed this copy', () => {
    const offenders: string[] = [];

    for (const path of sourceFiles(SRC)) {
      const relative = path.slice(SRC.length);
      if (relative === DOOR_ITSELF || UNGATED_BY_DECISION.includes(relative)) continue;

      const source = readFileSync(path, 'utf8');
      if (!source.includes('saasDoor(')) continue;
      if (DISTRIBUTION_GATES.test(source)) continue;

      const line = source.split('\n').findIndex((l) => l.includes('saasDoor(')) + 1;
      offenders.push(`${relative}:${line} → leaves for the SaaS without a distribution gate`);
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

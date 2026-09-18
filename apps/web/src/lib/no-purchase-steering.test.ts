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
  // So the rule below is not about ROUTES but about every WAY OUT, and it judges each one by WHERE
  // IT GOES (hub#1900). It used to judge files: a file that named a distribution gate anywhere was
  // let through whole, and only `saasDoor` counted as leaving. The review of hub#1907 measured seven
  // ways past that — `location.assign`, `location.href =`, an `<a href>`, the shell's opener called
  // directly, and three extra exits added to files that already passed — and one of those classes
  // had a live case: the assistant sent the webview itself to a card checkout (hub#1910).

  /**
   * The person's own account, asked for WITHOUT the panel around it (hub#1900): the SaaS paints it
   * with no sidebar, so «Billing» and «Marketplace» are not one tap away.
   *
   * This is the line Google Play's payments FAQ draws, word for word: an app may send people to
   * "administrative information – like an account management page […] as long as the webpage does
   * not eventually lead to an alternate payment method". The bare account page failed the second
   * half, because it is painted inside the panel. And the door could not simply be taken out of the
   * Play copy either: the app lets people sign up, so Play also requires an in-app path to DELETE
   * that account — and deleting it lives on this page.
   */
  const ACCOUNT_SURFACE = '/dashboard/profile/?surface=account';

  // 🪤 The CALL is required, not the bare name: a gate written in prose that explains the rule
  // satisfies an `includes` and lets the file through (measured by mutation in hub#1897).
  const PLAN_GATE = /\bplanUpgradeIsOfferable\(/;
  const MANAGEMENT_GATE = /\bmanagementIsOfferable\(/;

  interface Destination {
    what: string;
    reaches: RegExp;
    /** Present when the destination can take money: the gate that has to decide it (hub#756). */
    gate?: RegExp;
  }

  /**
   * Every place this app is allowed to take a person, and what makes each one allowed. A way out
   * whose destination is none of these is an offender — new doors have to be classified here, in a
   * reviewed line, not slipped in.
   */
  const DESTINATIONS: Destination[] = [
    // Pages that can take money. Offered only where the distribution allows it — the rule is set by
    // whoever hands out the binary (`upgrade-plan-link.ts`), not by the operating system.
    { what: 'the plan page (hub#756)', reaches: /\bupgradePlan(?:Url|Path)\(/, gate: PLAN_GATE },
    { what: "a module's plan (hub#1608)", reaches: /\bmodulePlan(?:Url|Path)\(/, gate: PLAN_GATE },
    { what: 'the management panel (hub#1897)', reaches: /\bmanagement(?:Door|Url|Path)\(/, gate: MANAGEMENT_GATE },
    { what: "the assistant's checkout (hub#1910)", reaches: /\bstartAssistantCheckout\(/, gate: PLAN_GATE },
    // Places that cannot take money.
    { what: "the person's own account, without the panel (hub#1900)", reaches: /(['"`])\/dashboard\/profile\/\?surface=account\1/ },
    { what: 'the app installer and its update channel (hub#400, hub#480)', reaches: /\bappDownloadUrl\(|\bappUpdateDestination\b/ },
    { what: "the SaaS's Google sign-in, which hands straight back to this hub (ADR-0157 §8)", reaches: /\bgoogleLoginUrl\(/ },
    { what: 'another hub, validated as one before leaving (deep links)', reaches: /\brequireHubUrl\(|\bhubDeepLink\(/ },
    { what: 'a file this till just generated (a download)', reaches: /\bURL\.createObjectURL\(/ },
  ];

  /**
   * An address of the SaaS written out by hand. Whatever else a way out reaches, it may not ALSO
   * carry one of these — the account surface is the only panel address a door may spell.
   */
  const RAW_SAAS_ADDRESS = /\/(?:dashboard|pricing|marketplace|billing|checkout|plans)\b|erplora\.com\//;

  /** The modules that DEFINE the ways out; naming them is not walking through them. */
  const DOORS_THEMSELVES = ['lib/saas-door.ts', 'lib/open-external.ts'];

  /** Reaching the shell's opener without `openExternal` skips the one place that checks. */
  const SHELL_OPENER = /\bopen_external_url\b|\bOPEN_EXTERNAL_COMMAND\b|plugin:opener|plugin:shell/;

  type WayOut = { kind: 'call' | 'navigation' | 'assignment' | 'anchor'; at: number; target: string };

  /** The text between a `(` at `open` and its matching `)` — strings skipped, nesting counted. */
  function balanced(source: string, open: number): string {
    let depth = 0;
    for (let i = open; i < source.length && i < open + 600; i++) {
      const c = source[i];
      if (c === "'" || c === '"') {
        const close = source.indexOf(c, i + 1);
        if (close === -1) break;
        i = close;
        continue;
      }
      if (c === '(') depth++;
      if (c === ')' && --depth === 0) return source.slice(open + 1, i);
    }
    return source.slice(open + 1, open + 600);
  }

  /** The right-hand side of an assignment starting at `from`, up to its `;` or end of line. */
  function statement(source: string, from: number): string {
    const end = source.slice(from).search(/;|\n/);
    return source.slice(from, end === -1 ? undefined : from + end);
  }

  /** Every way out written in `source`, with what it hands over. */
  function waysOut(source: string): WayOut[] {
    const found: WayOut[] = [];
    for (const m of source.matchAll(/\b(saasDoor|openExternal|window\.open)\s*\(/g)) {
      found.push({ kind: 'call', at: m.index, target: balanced(source, m.index + m[0].length - 1) });
    }
    for (const m of source.matchAll(/\blocation\.(?:assign|replace)\s*\(/g)) {
      found.push({ kind: 'navigation', at: m.index, target: balanced(source, m.index + m[0].length - 1) });
    }
    // `location.href = …`, `window.location = …`, and an anchor built in code (`a.href = …; a.click()`).
    for (const m of source.matchAll(/(?:\.href|\bwindow\.location|\bdocument\.location)\s*=(?![=>])/g)) {
      const kind = m[0].startsWith('.href') && !/location\.href/.test(source.slice(m.index - 9, m.index + 5)) ? 'assignment' : 'navigation';
      found.push({ kind, at: m.index, target: statement(source, m.index + m[0].length) });
    }
    // `<a href="…">`, `<ion-button :href="…">` — not `back-href`, which is this app's own router.
    for (const m of source.matchAll(/(?<![\w-])(?::|v-bind:)?href=(["'])(.*?)\1/g)) {
      found.push({ kind: 'anchor', at: m.index, target: m[2] });
    }
    return found;
  }

  /** Identifiers used in `expr` outside string literals — the names worth following. */
  function namesIn(expr: string): string[] {
    const names: string[] = [];
    const code = expr.replace(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"/g, "''");
    for (const m of code.matchAll(/(?<![.\w$])[A-Za-z_$][\w$]*/g)) names.push(m[0]);
    return names;
  }

  /**
   * `target` plus the value of every local it names, followed to where each was declared — nearest
   * declaration BEFORE the way out, the way scoping reads it. Appended, never substituted, so a
   * destination written on the way stays visible.
   */
  function resolve(source: string, target: string, at: number): string {
    let seen = target;
    const pending = namesIn(target);
    const followed = new Set<string>();
    while (pending.length > 0 && followed.size < 40) {
      const name = pending.shift() as string;
      if (followed.has(name)) continue;
      followed.add(name);
      const declared = [...source.matchAll(new RegExp(`\\b(?:const|let|var)\\s+${name.replace(/\$/g, '\\$')}\\s*(?::[^=]+)?=`, 'g'))];
      const before = declared.filter((d) => d.index < at);
      const pick = before.length > 0 ? before[before.length - 1] : declared[0];
      if (!pick) continue;
      const value = statement(source, pick.index + pick[0].length);
      seen += ` ⟨${name} = ${value}⟩`;
      pending.push(...namesIn(value));
    }
    return seen;
  }

  /**
   * `text` with its comments blanked out, line breaks kept so line numbers still point right. Prose
   * is not a way out — and a gate named only in prose is not a gate. A `//` right after `:` or a
   * quote is an address (`https://…`), not a comment.
   */
  function withoutComments(text: string): string {
    const blank = (m: string): string => m.replace(/[^\n]/g, ' ');
    return text
      .replace(/\/\*[\s\S]*?\*\//g, blank)
      .replace(/<!--[\s\S]*?-->/g, blank)
      .replace(/(^|[^:'"`\\])\/\/.*$/gm, (m, lead: string) => lead + blank(m.slice(lead.length)));
  }

  /** Why the ways out written in `text` could reach a payment — empty when none can. */
  function stepsTowardsMoney(relative: string, text: string): string[] {
    if (DOORS_THEMSELVES.includes(relative)) return [];
    const source = withoutComments(text);
    const offences: string[] = [];
    const lineOf = (at: number): number => source.slice(0, at).split('\n').length;

    const opener = SHELL_OPENER.exec(source);
    if (opener) {
      offences.push(`${relative}:${lineOf(opener.index)} → calls the shell's opener directly, past openExternal`);
    }

    for (const way of waysOut(source)) {
      const where = `${relative}:${lineOf(way.at)}`;
      const own = way.target.trim();
      // A page of this same app: a relative address, which the webview resolves against the hub.
      const inside = /^['"`]?(?:\/(?!\/)|#)/.test(own) && !RAW_SAAS_ADDRESS.test(own);
      if ((way.kind === 'navigation' || way.kind === 'anchor') && inside) continue;

      const seen = resolve(source, own, way.at);
      const reached = DESTINATIONS.filter((d) => d.reaches.test(seen));
      if (reached.length === 0) {
        offences.push(`${where} → leaves for ${own.slice(0, 70)}, which is no known destination`);
        continue;
      }
      for (const d of reached) {
        if (d.gate && !d.gate.test(source)) {
          offences.push(`${where} → reaches ${d.what} and never asks who distributed this copy`);
        }
      }
      const raw = RAW_SAAS_ADDRESS.exec(seen.split(ACCOUNT_SURFACE).join(''));
      if (raw) offences.push(`${where} → spells a SaaS address by hand (${raw[0]})`);
    }
    return offences;
  }

  it('every way out of the till goes somewhere classified, and the paid ones ask who distributed it', () => {
    const offenders = sourceFiles(SRC).flatMap((path) =>
      stepsTowardsMoney(path.slice(SRC.length), readFileSync(path, 'utf8')),
    );

    expect(offenders.join('\n')).toBe('');
  });

  // The positive control, kept for good: each of these is a way out the review of hub#1907 wrote
  // into the real tree and watched the old rule pass. A rule that stops recognising one of them
  // fails HERE, instead of approving the next real door in silence.
  it.each([
    ['R1 · location.assign to the panel', 'lib/x.ts', "window.location.assign('https://erplora.com/dashboard/');"],
    ['R2 · location.href = the panel', 'lib/x.ts', "window.location.href = 'https://erplora.com/dashboard/';"],
    ['R3 · an <a href> to the panel', 'views/X.vue', '<a href="https://erplora.com/dashboard/" target="_blank">x</a>'],
    ['R4 · the shell opener, called directly', 'lib/x.ts', "await invokeTauri('open_external_url', { url });"],
    [
      'R5 · a second, unfiltered exit in a file that has a gate',
      'App.vue',
      "canOffer.value = planUpgradeIsOfferable(d);\nawait openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'p'));\nwindow.open('https://erplora.com/dashboard/');",
    ],
    ['R6 · a declared door that also opens pricing', 'views/SystemPage.vue', 'await openExternal(appDownloadUrl(p));\nawait openExternal(`${config.cloudApiUrl}/pricing/`);'],
    ['R7 · the panel without its trailing slash', 'views/ProfilePage.vue', "const CLOUD_ACCOUNT_PATH = '/dashboard/profile/?surface=account';\nawait openExternal(`${config.cloudApiUrl}/dashboard`);"],
    ['the account door back on the bare panel page', 'views/ProfilePage.vue', "const CLOUD_ACCOUNT_PATH = '/dashboard/profile/';\nawait openExternal(await saasDoor(CLOUD_ACCOUNT_PATH, plain, 'a'));"],
    ['a checkout nobody gates (hub#1910)', 'components/X.vue', 'const url = await startAssistantCheckout(t);\nif (url) window.location.assign(url);'],
    ['an anchor built in code', 'lib/x.ts', "const a = document.createElement('a');\na.href = 'https://erplora.com/billing/';\na.click();"],
  ])('catches %s', (_name, relative, source) => {
    expect(stepsTowardsMoney(relative, source)).not.toEqual([]);
  });

  // …and its negative half: the doors that ARE fine stay fine, or the rule would be red for ever.
  it.each([
    ['a page of this same hub', 'lib/x.ts', "window.location.assign('/login');"],
    ['the account surface', 'views/ProfilePage.vue', "const CLOUD_ACCOUNT_PATH = '/dashboard/profile/?surface=account';\nconst plain = `${base}${CLOUD_ACCOUNT_PATH}`;\nawait openExternal(ok ? await saasDoor(CLOUD_ACCOUNT_PATH, plain, 'a') : plain);"],
    ['the installer', 'views/SystemPage.vue', 'await openExternal(appDownloadUrl(os.platform));'],
    ['a gated plan door', 'App.vue', "x = planUpgradeIsOfferable(d);\nawait openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'p'));"],
  ])('lets through %s', (_name, relative, source) => {
    expect(stepsTowardsMoney(relative, source)).toEqual([]);
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

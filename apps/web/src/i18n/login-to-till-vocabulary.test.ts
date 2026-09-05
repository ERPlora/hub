// @vitest-environment node
// hub#365 — the words of the login → till path (PLAN step 8, ADR-0254).
//
// The owner walks four screens to reach the till and never chooses any of them: the login, the
// activation gate, the panel and the chrome that follows them everywhere (sidebar + topbar), plus
// the one door the path offers on purpose — the place apps come from. Every word on those screens
// is read by a bar owner or a hairdresser, and today they mix two languages: the business's
// («tu negocio», «tus apps») and the platform's («hub», «Cloud», «módulo», «marketplace»).
//
// This suite is the contract of the FIRST one. It is a copy test, so it asserts the copy: what each
// label says, that the same thing has ONE name across surfaces, and that nothing reaches the reader
// in English only. A translation that never landed is the classic bug here — it does not crash, it
// just shows an English sentence to somebody who does not read English.
import { describe, expect, it } from 'vitest';

import en from './locales/en';
import es from './locales/es';

/**
 * The namespaces the owner crosses on the way in, plus the ones migrated since.
 *
 * hub#365 scoped itself to the PATH (plus the apps door). hub#481 pays the rest of the debt: the
 * screens you CHOOSE were speaking platform too, and one of them —Settings— was holding a sentence
 * on the path hostage (see the pointer below). Growing this list is how a surface gets migrated;
 * writing a second test would let the two drift.
 */
const PATH_NAMESPACES = [
  'login',
  'activation',
  'nav',
  'topbar',
  'sidebar',
  'dashboard',
  'setup',
  'apps',
  // hub#400. It paints in the sidebar, so it is chrome the owner meets everywhere — and it is the
  // namespace most at risk of opening a fourth noun: the thing it updates is the app you install,
  // while «apps» already names the things you add to your business. It says «ERPlora».
  'appUpdate',
  // ── hub#481 ──────────────────────────────────────────────────────────────────────────────────
  // Settings and Profile first, because they are what the login pointer names: until the «Hub» tab
  // had a business name, `login.personalDeviceNote` could not stop saying «Ajustes › Hub».
  'settings',
  'profile',
  // The surfaces the issue lists by name. All of them are read by the owner, none of them is
  // technical documentation.
  'assistant',
  'files',
  'exportPage',
  'importPage',
  'deviceMode',
  'devices',
  'pinPolicy',
] as const;

/**
 * Namespaces deliberately NOT migrated, with the reason. Absence from the list above is a decision
 * here, not an oversight — that is the whole point of writing them down.
 *
 * * **`apiDocs`** — it is the public API reference (ADR-0057 §4), read by an INTEGRATOR, not by the
 *   owner. «Hub» is the correct word there: it is what the API, the manifest and the ADRs call it,
 *   and translating it for a developer would make the docs disagree with the thing they document.
 *   The issue asked for this to be DECIDED rather than changed by inertia — this is the decision.
 * * **`dashboard.widgets`** — «widget» is jargon for a bar owner, but it is the vocabulary of
 *   ADR-0054 and it names things the user can save into presets. Renaming it is a product decision
 *   with a data migration behind it, not a copy change, so it does not ride along here. (It already
 *   passes: «widget» is not a platform noun, it is a UI noun.)
 */
const NOT_MIGRATED_ON_PURPOSE = ['apiDocs'] as const;

/**
 * The platform's nouns. Each one asks the reader to hold a piece of OUR architecture in their head
 * before they can serve a coffee, so none of them belongs on this path. They stay alive everywhere
 * they are true — the API, the database, the ADRs, the SaaS — which is why nothing here renames a
 * key, a route or a field: only what a human reads changes.
 */
const PLATFORM_NOUNS: readonly RegExp[] = [
  /\bhubs?\b/i,
  /\bclouds?\b/i,
  /\bnube\b/i,
  /\bmodules?\b/i,
  /\bm[oó]dulos?\b/i,
  /\bmarketplace\b/i,
  /\bentitlements?\b/i,
  /\borgani[sz]ation(?:s)?\b/i,
  /\borganizaci[oó]n(?:es)?\b/i,
  /\btenants?\b/i,
  /\bsaas\b/i,
];

// hub#481 — the exception is GONE, and its disappearance is the point.
//
// `login.personalDeviceNote` was allowed to say «Ajustes › Hub» because it is a POINTER: it must
// name its target exactly as the target reads on screen, and that tab was still called «Hub».
// Settings has now been migrated with the rest of this list, the tab is «General», and the pointer
// follows it — so there is nothing left to exempt. An exception that outlives its cause is how a
// vocabulary rule rots, so it is deleted rather than kept "just in case".

/**
 * Values that are legitimately identical in both catalogues: proper nouns, protocol words and
 * borrowings Spanish uses unchanged. Anything else that matches its English twin is an untranslated
 * string, not a coincidence.
 */
const SAME_IN_BOTH_LANGUAGES = new Set([
  'login.tabPin',
  'login.emailLabel',
  'login.tabEmail',
  'nav.general',
  'nav.apps',
  'nav.apiDocs',
  'dashboard.widgets',
  'apps.colModule',
  // ── hub#481 ──────────────────────────────────────────────────────────────────────────────────
  // «Apps» is the noun ADR-0254 chose, and Spanish took it unchanged — so every label that is only
  // that word is identical on purpose, not a translation somebody forgot.
  'settings.tabHub',
  'exportPage.modules',
  'exportPage.colModule',
  'exportPage.colInclude',
  'importPage.manifestModules',
  'importPage.modulesTitle',
  'importPage.reportModules',
  'importPage.sectionModule',
  // Proper nouns and words Spanish uses unchanged.
  'settings.countryPortugal',
  'settings.hardware',
  'exportPage.sectionFiscal',
  'importPage.sectionFiscal',
  'importPage.sectionRoles',
  'pinPolicy.idleMinutes',
  // hub#1430 — «PIN» itself: an acronym Spanish uses unchanged, same as the borrowings above. The
  // sentences that surround it («Cambiar PIN», «PIN actual»…) are translated; the three letters are
  // not a word to translate.
  'profile.pinTitle',
  // hub#1400 — the domain name printed on the door to erplora.com. A proper noun, same reason as
  // `settings.hardware` above: there is no Spanish word for a domain, so both catalogues read it
  // identically on purpose. The sentence AROUND it (`topbar.manage`) is translated in full.
  'topbar.manageShort',
  // hub#1154 — a pure format string: two placeholders and a separator, not a single word. There is
  // nothing here to translate, so the two catalogues MUST read the same. This is a different reason
  // from the borrowings above, and it is the only one of its kind: if a second entry ever needs
  // this exemption, check first that it really carries no words rather than widening the rule.
  'settings.timezoneOptionNow',
]);

type Leaf = { key: string; value: string };

/** Every string under `namespace`, keyed by its dotted path. Non-string leaves cannot be read. */
function leaves(catalogue: Record<string, unknown>, namespace: string): Leaf[] {
  const out: Leaf[] = [];
  const walk = (node: unknown, path: string): void => {
    if (typeof node === 'string') {
      out.push({ key: path, value: node });
      return;
    }
    if (node && typeof node === 'object') {
      for (const [k, v] of Object.entries(node)) walk(v, `${path}.${k}`);
    }
  };
  walk((catalogue as Record<string, unknown>)[namespace], namespace);
  return out;
}

const pathLeaves = (catalogue: Record<string, unknown>): Leaf[] =>
  PATH_NAMESPACES.flatMap((ns) => leaves(catalogue, ns));

const offendingNouns = (value: string): string[] =>
  PLATFORM_NOUNS.filter((re) => re.test(value)).map((re) => re.source);

describe('the money door', () => {
  // «Billing»/«Facturación» is the platform's accounting word: it names the ledger the SaaS keeps.
  // What the owner wants to know from inside the till is which plan they are on and what it lets
  // them do — and «plan» is already the hub's own word for it (`billing.managePlan`,
  // `planLimits.currentPlan`, `modulePlan.statusTitle`). This is one label on two surfaces: the
  // sidebar entry and the title of the page it opens (BillingPage reads the same key).
  it('is called «My plan», in the first person of the business', () => {
    expect(en.nav.billing).toBe('My plan');
    expect(es.nav.billing).toBe('Mi plan');
  });

  it('never falls back to the SaaS ledger word', () => {
    expect(es.nav.billing).not.toBe('Facturación');
    expect(en.nav.billing).not.toBe('Billing');
  });
});

describe('the apps door', () => {
  // hub#367 chose the noun — «apps» — for the launcher and for the panel tile. A third word
  // («funciones», «módulos») for the same thing is worse than a mediocre one, so the marketplace
  // says «apps» too, and the tab that leads there uses the tile's exact words.
  it('says «apps» wherever the same thing is named', () => {
    expect(en.topbar.apps).toBe('My apps');
    expect(es.topbar.apps).toBe('Mis apps');
    expect(en.apps.tabMine).toBe('My apps');
    expect(es.apps.tabMine).toBe('Mis apps');
  });

  it('offers more of them with the same words as the panel tile', () => {
    expect(en.apps.tabCatalog).toBe(en.dashboard.appsAdd);
    expect(es.apps.tabCatalog).toBe(es.dashboard.appsAdd);
    expect(en.dashboard.appsAdd).toBe('Add apps');
    expect(es.dashboard.appsAdd).toBe('Añadir apps');
  });

  it('never opens a third vocabulary for it', () => {
    for (const { key, value } of [...pathLeaves(en), ...pathLeaves(es)]) {
      expect(value, `${key} invents a third name for an app`).not.toMatch(/\bfunciones\b/i);
      expect(value, `${key} invents a third name for an app`).not.toMatch(/\bfeatures\b/i);
    }
  });
});

describe('what somebody who cannot install sees', () => {
  // hub#435 (ADR-0248) settled it: a task that is not yours goes away, a WALL stays. There is no
  // filtering to do here — the catalogue is worth browsing to anyone — so the wall stays and it
  // says who can. What changes is that it stops calling them «módulos».
  it('is a wall that names who can, in the path vocabulary', () => {
    expect(en.apps.adminOnly).toContain('administrator');
    expect(es.apps.adminOnly).toContain('administrador');
    expect(en.apps.adminOnly).toMatch(/\bapps\b/);
    expect(es.apps.adminOnly).toMatch(/\bapps\b/);
  });

  it('says what is still theirs to do, so the wall is not read as a refusal of the screen', () => {
    // Without this half the sentence turns into «only an administrator can», which reads as «go
    // away» on a page a cashier is welcome to read. The catalogue is worth browsing to anyone: what
    // is gated is installing, and only that.
    expect(en.apps.adminOnly).toMatch(/\bbrowse\b/);
    expect(es.apps.adminOnly).toMatch(/\bpuedes ver\b/i);
  });
});

describe('the business, never the architecture', () => {
  it('never says a platform noun on the path', () => {
    const offenders = [...pathLeaves(en), ...pathLeaves(es)]
      .flatMap(({ key, value }) => offendingNouns(value).map((noun) => `${key}: ${noun} → ${value}`));
    expect(offenders).toEqual([]);
  });

  // hub#481 — a namespace left out has to be left out ON PURPOSE. Without this, «not migrated yet»
  // and «decided not to migrate» look identical from the outside, and the next person re-litigates
  // a decision that was already made. Adding one to the path means deleting it here first, which is
  // where its reason is written.
  it('keeps the surfaces that legitimately speak platform out of the path', () => {
    for (const ns of NOT_MIGRATED_ON_PURPOSE) {
      expect(PATH_NAMESPACES as readonly string[], `${ns}: read why before adding it`).not.toContain(ns);
      // …and it must still exist: an exclusion pointing at a namespace nobody ships is dead weight.
      expect(en, `${ns} no longer exists — drop the exclusion`).toHaveProperty(ns);
    }
  });

  it('calls the tenant «your business» where it used to say «your hub»', () => {
    expect(en.login.subtitleEmail).toBe('Sign in to your business');
    expect(es.login.subtitleEmail).toBe('Entra en tu negocio');
    expect(en.setup.title).toBe('Finish setting up your business');
    expect(es.setup.title).toBe('Termina de configurar tu negocio');
    expect(en.setup.completeTitle).toBe('Your business is ready');
    expect(es.setup.completeTitle).toBe('Tu negocio está listo');
    expect(en.dashboard.blueprintTitle).toBe('Set up your business');
    expect(es.dashboard.blueprintTitle).toBe('Configura tu negocio');
  });

  it('keeps the blocking strip saying the CONSEQUENCE, in things a till sells', () => {
    // hub#374: the strip exists to say what the runtime will refuse. Dropping «the hub will refuse»
    // must not drop the refusal — it names the two documents a till issues instead.
    expect(es.setup.blocking.body).toContain('ticket');
    expect(es.setup.blocking.body).toContain('factura');
    expect(en.setup.blocking.body).toContain('ticket');
    expect(en.setup.blocking.body).toContain('invoice');
  });

  // hub#481 — a pointer has to name its target exactly as the target reads on screen. The Settings
  // tab that owns this decision is no longer called «Hub», so the pointer names the new one. This
  // assertion is the reason the two can never drift apart again: rename the tab without the
  // pointer, or the pointer without the tab, and it goes red.
  it('points at the tab by the name that tab actually shows', () => {
    expect(es.login.personalDeviceNote).toContain(`Ajustes › ${es.settings.tabHub}`);
    expect(en.login.personalDeviceNote).toContain(`Settings › ${en.settings.tabHub}`);
  });
});

describe('nothing reaches the reader untranslated', () => {
  it('has an `es` for every string on the path', () => {
    const spanish = new Map(pathLeaves(es).map(({ key, value }) => [key, value]));
    const missing = pathLeaves(en)
      .map(({ key }) => key)
      .filter((key) => !spanish.has(key));
    expect(missing).toEqual([]);
  });

  it('has no `es` left in English', () => {
    const spanish = new Map(pathLeaves(es).map(({ key, value }) => [key, value]));
    const untranslated = pathLeaves(en)
      .filter(({ key, value }) => spanish.get(key) === value && !SAME_IN_BOTH_LANGUAGES.has(key))
      .map(({ key, value }) => `${key}: ${value}`);
    expect(untranslated).toEqual([]);
  });

  it('carries no orphan `es` key that no English source declares', () => {
    const english = new Set(pathLeaves(en).map(({ key }) => key));
    const orphans = pathLeaves(es)
      .map(({ key }) => key)
      .filter((key) => !english.has(key));
    expect(orphans).toEqual([]);
  });
});

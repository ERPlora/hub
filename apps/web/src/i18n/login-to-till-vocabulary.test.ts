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
 * The namespaces the owner crosses on the way in. `settings`, `profile`, `system`, `files` and the
 * rest are deliberately absent: they are destinations you choose, not the path, and hub#365 is
 * scoped to the path (plus the apps door, which the issue names).
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
] as const;

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

/**
 * The one sentence on the path that is allowed to say «Hub», with the reason written down. It is a
 * POINTER: it tells the user where the decision lives, and a pointer has to name its target exactly
 * as the target reads on screen. Settings still calls that tab «Hub», and Settings is not on this
 * path — so renaming the pointer here would make it lie. The tab is renamed with the rest of the
 * Settings surface in hub#481; this line follows it there, not from here.
 */
const POINTER_TO_A_SCREEN_NOT_ON_THIS_PATH = 'login.personalDeviceNote';

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
      .filter(({ key }) => key !== POINTER_TO_A_SCREEN_NOT_ON_THIS_PATH)
      .flatMap(({ key, value }) => offendingNouns(value).map((noun) => `${key}: ${noun} → ${value}`));
    expect(offenders).toEqual([]);
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

  it('leaves the one pointer that must name its target as the target reads', () => {
    // Deliberate, and the only one: see POINTER_TO_A_SCREEN_NOT_ON_THIS_PATH.
    expect(es.login.personalDeviceNote).toContain('Ajustes › Hub');
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

// @vitest-environment happy-dom
// The hero card of an empty business (hub#368, PLAN step 10) — the one screen where «start from a
// business like yours» beats «install apps one by one».
//
// What these tests protect:
//   - it only asks the cloud for templates when it could actually offer them (an administrator, a
//     business with no apps): a configured hub must not put the SaaS on the panel's critical path;
//   - one click really is one click — download, inspect and import, with no review screen;
//   - and precisely BECAUSE there is no review screen, that click never asks for the people or the
//     fiscal identity of the business the template came from (ADR-0195 §4/§5);
//   - a click that fails says WHICH kind of failure it was: one that changed nothing, one that may
//     have changed something, and one that got most of the way (best-effort engine);
//   - an app that only needs subscribing is not painted as a breakage (ADR-0060, hub#409);
//   - and the happy ending never claims the business is configured — a template does not bring the
//     owner's tax details, so the checklist below is still not empty.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchBlueprintCatalog = vi.fn();
const downloadBlueprint = vi.fn();
const inspectBlueprint = vi.fn();
const importBlueprint = vi.fn();

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return {
    ...actual,
    fetchBlueprintCatalog: (...a: unknown[]) => fetchBlueprintCatalog(...a),
    downloadBlueprint: (...a: unknown[]) => downloadBlueprint(...a),
    inspectBlueprint: (...a: unknown[]) => inspectBlueprint(...a),
    importBlueprint: (...a: unknown[]) => importBlueprint(...a),
  };
});

const refreshModuleNav = vi.fn();
vi.mock('../lib/nav', () => ({ refreshModuleNav: (...a: unknown[]) => refreshModuleNav(...a) }));

// hub#488 — human names of the apps. Empty by default, which IS the «no name known» case: the
// sentence must then fall back to the id rather than go blank.
const appNames = vi.hoisted(() => new Map<string, string>());
vi.mock('../lib/app-names', async () => {
  const actual = await vi.importActual<typeof import('../lib/app-names')>('../lib/app-names');
  // `appLabel` stays REAL: «a name, or the id, never an invention» is the rule under test.
  return { appLabel: actual.appLabel, loadAppNames: async () => appNames };
});

// A real `ref`: the card reads the permission of ADR-0248 off the session the runtime resolved.
const { session } = vi.hoisted(() => ({ session: { value: null as { permissions?: string[] } | null } }));
// PARTIAL mock: `user` is stubbed, but `permissionsInclude` must stay REAL. Since hub#506 the
// wildcard rule lives in exactly one place and `blueprint-hero.ts` imports it from here — a mock
// that only returns `user` makes it `undefined` and every test in this file dies on the first
// computed. Stubbing it too would be worse: the point of hub#506 is that there is ONE rule, and a
// second copy in a test is how the four copies it deleted got there.
vi.mock('../lib/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/session')>()),
  user: session,
}));
vi.mock('../lib/hub-settings', () => ({ hubSettings: { value: { country_code: 'ES', language: 'es' } } }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import BlueprintHeroCard from './BlueprintHeroCard.vue';
import type { SetupItem, SetupStatus } from '../lib/setup-status';
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: enCatalogue },
});
const i18nEs = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  messages: { es: esCatalogue },
});

function appsItem(state: string): SetupItem {
  return {
    key: 'apps',
    source: 'core',
    moduleId: null,
    state,
    required: true,
    level: 'functional',
    title: 'Your apps',
    description: '',
    icon: 'grid-outline',
    route: '/apps',
    order: 10,
    actions: ['template', 'catalog'],
    actionable: true,
    origin: 'user',
  };
}

function emptyBusiness(state = 'pending'): SetupStatus {
  return {
    items: [appsItem(state)],
    total: 1,
    pending: state === 'pending' ? 1 : 0,
    unavailable: state === 'unavailable' ? 1 : 0,
    blockingPending: 0,
    done: state === 'done' ? 1 : 0,
  };
}

const RESTAURANT = {
  slug: 'restaurant_es',
  name: 'Restaurante',
  description: 'Till and kitchen',
  locale: 'es',
  country: 'ES',
  latest_version: '1.0.0',
  latest_sha256: 'aa',
  size_bytes: 2048,
  downloads: 12,
};

const MANIFEST = {
  schema_version: 1,
  name: 'Restaurante',
  locale: 'es',
  hub: {},
  created_at: '2026-08-08T00:00:00Z',
  modules: [{ id: 'pos', version: '1.0.0', with_data: true }],
  sections: ['hub_users', 'hub_settings', 'fiscal', 'media'],
  sha256: {},
};

function mountCard(
  status: SetupStatus | null = emptyBusiness(),
  messages: typeof i18n | typeof i18nEs = i18n,
) {
  return mount(BlueprintHeroCard, {
    props: { status },
    global: { plugins: [messages], renderStubDefaultSlot: true },
    shallow: true,
  });
}

beforeEach(() => {
  fetchBlueprintCatalog.mockReset().mockResolvedValue([RESTAURANT]);
  downloadBlueprint.mockReset().mockResolvedValue(new Blob(['zip']));
  inspectBlueprint.mockReset().mockResolvedValue({ ok: true, upload_id: 'up-1', manifest: MANIFEST });
  importBlueprint.mockReset().mockResolvedValue({ sections: [], installed_modules: [] });
  refreshModuleNav.mockReset();
  appNames.clear();
  session.value = { permissions: ['hub.administer'] };
});

describe('when the card asks the cloud anything at all', () => {
  it('offers the published templates to an administrator of an empty business', async () => {
    const w = mountCard();
    await flushPromises();

    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
    expect(w.find('[data-testid="hero-card"]').exists()).toBe(true);
    expect(w.findAll('[data-testid="hero-offer"]')).toHaveLength(1);
  });

  it('never asks on a business that already has its apps', async () => {
    const w = mountCard(emptyBusiness('done'));
    await flushPromises();

    // The panel is loaded on every visit: a card that fetched the catalogue anyway would put the
    // SaaS on the critical path of a screen that has nothing to ask it.
    expect(fetchBlueprintCatalog).not.toHaveBeenCalled();
    expect(w.find('[data-testid="hero-card"]').exists()).toBe(false);
  });

  it('never asks before the one query has answered', async () => {
    mountCard(null);
    await flushPromises();

    expect(fetchBlueprintCatalog).not.toHaveBeenCalled();
  });

  it('never asks for a session that cannot administer the business (hub#435)', async () => {
    session.value = { permissions: ['pos.sale.create'] };
    const w = mountCard();
    await flushPromises();

    expect(fetchBlueprintCatalog).not.toHaveBeenCalled();
    expect(w.find('[data-testid="hero-card"]').exists()).toBe(false);
  });

  it('asks once the answer arrives, not only at mount', async () => {
    const w = mountCard(null);
    await flushPromises();
    expect(fetchBlueprintCatalog).not.toHaveBeenCalled();

    await w.setProps({ status: emptyBusiness() });
    await flushPromises();
    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
  });

  it('asks ONCE, however much the answer flaps', async () => {
    const w = mountCard();
    await flushPromises();
    await w.setProps({ status: emptyBusiness('done') });
    await flushPromises();
    await w.setProps({ status: emptyBusiness() });
    await flushPromises();

    // The published catalogue does not change under us in one sitting: asking again on every swing
    // of the checklist would put the SaaS back on the panel's critical path.
    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
  });

  it('stays quiet when the cloud has nothing (or cannot answer): no empty hero', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountCard();
    await flushPromises();
    expect(w.find('[data-testid="hero-card"]').exists()).toBe(false);

    fetchBlueprintCatalog.mockRejectedValue(new Error('no cloud credential'));
    const offline = mountCard();
    await flushPromises();
    expect(offline.find('[data-testid="hero-card"]').exists()).toBe(false);
  });
});

describe('one click', () => {
  async function clickFirstOffer() {
    const w = mountCard();
    await flushPromises();
    await w.find('[data-testid="hero-use"]').trigger('click');
    await flushPromises();
    return w;
  }

  it('downloads, inspects and imports without a single extra screen', async () => {
    await clickFirstOffer();

    expect(downloadBlueprint).toHaveBeenCalledWith('restaurant_es');
    expect(inspectBlueprint).toHaveBeenCalledTimes(1);
    expect(importBlueprint).toHaveBeenCalledTimes(1);
    expect(importBlueprint.mock.calls[0][0]).toBe('up-1');
  });

  it('asks for the apps and their data, and NEVER for identities', async () => {
    await clickFirstOffer();
    const selection = importBlueprint.mock.calls[0][1];

    expect(selection.modules).toEqual(['pos']);
    expect(selection.settings).toBe(true);
    expect(selection.media).toBe(true);
    // The bundle declares both sections and the card still refuses them: there is no review step
    // here where a human could veto somebody else's people or tax certificate.
    expect(selection.users).toBe(false);
    expect(selection.fiscal).toBe(false);
  });

  it('tells the rest of the shell that the set of apps changed', async () => {
    const changed = vi.fn();
    window.addEventListener('erp:modules-changed', changed);
    await clickFirstOffer();
    window.removeEventListener('erp:modules-changed', changed);

    // Without this the panel keeps painting the PRE-import hub: the same contract ImportPanel has.
    expect(refreshModuleNav).toHaveBeenCalled();
    expect(changed).toHaveBeenCalled();
  });

  it('does not run twice while the first one is still going', async () => {
    let release: (v: Blob) => void = () => {};
    downloadBlueprint.mockImplementation(() => new Promise<Blob>((r) => (release = r)));
    const w = mountCard();
    await flushPromises();

    await w.find('[data-testid="hero-use"]').trigger('click');
    await w.find('[data-testid="hero-use"]').trigger('click');
    release(new Blob(['zip']));
    await flushPromises();

    expect(downloadBlueprint).toHaveBeenCalledTimes(1);
  });
});

describe('what the owner is told afterwards', () => {
  async function outcomeOf(w: ReturnType<typeof mountCard>) {
    await flushPromises();
    await w.find('[data-testid="hero-use"]').trigger('click');
    await flushPromises();
    return w;
  }

  it('never says the business is configured — a template does not bring the owner\'s details', async () => {
    const w = await outcomeOf(mountCard());

    const done = w.find('[data-testid="hero-done"]');
    expect(done.exists()).toBe(true);
    expect(done.text()).toBe(enCatalogue.setup.hero.readyBody);
    // The checklist below owns «what is left»; this card must not claim there is nothing left.
    expect(done.text()).not.toMatch(/all set|nothing left|ready to sell/i);
  });

  // 🔴 [hub#535] The card says it brings SAMPLE data — before the click and after it.
  //
  // Barbería and peluquería carry 25-28 appointments with their history, invented customers and
  // their notes. They are sample data on purpose: they show how the agenda works. But they are
  // born «today into the future» the day the template is generated, so by the time somebody
  // imports it they are in the past, and the business opens onto an agenda from July that is not
  // its own (ERPlora/hub#426).
  //
  // We do NOT write a relative-date engine for that: expensive, small problem, and already solved
  // — undoing an import exists and lives in Settings › Data. What was missing is SAYING it.
  it('warns that the template brings sample data BEFORE the click', async () => {
    const w = mountCard();
    await flushPromises();

    expect(w.find('[data-testid="hero-sample"]').text()).toBe(enCatalogue.setup.hero.sampleData);
  });

  it('says where the sample data is removed once it is in', async () => {
    const w = await outcomeOf(mountCard());

    const hint = w.find('[data-testid="hero-sample-undo"]');
    expect(hint.exists()).toBe(true);
    expect(hint.text()).toBe(enCatalogue.setup.hero.sampleDataUndo);
    // It points at the door that already exists; it must not promise a button of its own.
    expect(hint.text()).toMatch(/Settings/);
  });

  it('names the apps that only need subscribing, and does not call them broken', async () => {
    importBlueprint.mockResolvedValue({
      sections: [],
      installed_modules: [{ id: 'invoice', version: '1.0.0', status: 'blocked', blocked_on: ['invoice'] }],
    });
    const w = await outcomeOf(mountCard());

    const blocked = w.find('[data-testid="hero-blocked"]');
    expect(blocked.exists()).toBe(true);
    expect(blocked.text()).toContain('invoice');
    // hub#409: a purchase decision is not a red failure. The failure line must not be up.
    expect(w.find('[data-testid="hero-failed"]').exists()).toBe(false);
  });

  it('says what did not make it when something really broke', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [{ id: 'pos', version: '1.0.0', status: 'failed', error: 'boom' }],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-failed"]').exists()).toBe(true);
    expect(w.find('[data-testid="hero-outcome-title"]').text()).toBe(enCatalogue.setup.hero.partialTitle);
    // «Almost» is not «done»: the happy sentence must not be up next to a failure.
    expect(w.find('[data-testid="hero-done"]').exists()).toBe(false);
  });

  // hub#751 — «something else did not go in» sent a hairdresser to look for a needle. The card
  // already KNOWS which apps broke; naming them is the difference between an unactionable sentence
  // and one she can act on (or repeat to support).
  it('NAMES the apps that did not go in, instead of "something else"', async () => {
    importBlueprint.mockResolvedValue({
      sections: [],
      installed_modules: [
        { id: 'sales', version: '2.12.8', status: 'installed' },
        { id: 'verifactu', version: '1.4.1', status: 'failed', error: 'versión no encontrada: 1.4.1' },
      ],
    });
    const w = await outcomeOf(mountCard());

    const failed = w.find('[data-testid="hero-failed"]');
    expect(failed.exists()).toBe(true);
    expect(failed.text()).toContain('verifactu');
    // …and not the app that DID go in: naming the wrong one is worse than naming none.
    expect(failed.text()).not.toContain('sales');
  });

  // hub#763 — the card SAID «you can see the detail in Settings › Data» and then left the owner to
  // find that screen on their own. The report is persisted now, so the sentence has somewhere to
  // point: the card must carry the door, not just its address.
  it('takes the owner to the report it promised, instead of only naming the screen', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [{ id: 'pos', version: '1.0.0', status: 'failed', error: 'boom' }],
    });
    const w = await outcomeOf(mountCard());

    const link = w.find('[data-testid="hero-see-report"]');
    expect(link.exists()).toBe(true);
    // `router-link` is a PROP of ion-button, not a plain attribute, so `attributes()` returns
    // `undefined` for it and would pass on ANY destination, including none. The stub renders the
    // resolved prop into its markup, which is where the destination can actually be read.
    expect(link.html()).toContain('routerlink="/settings?tab=data"');
  });

  it('an import where NOTHING broke offers no report to read', async () => {
    const w = await outcomeOf(mountCard());

    // Everything landed: sending the owner to a report of a clean run is noise, not help.
    expect(w.find('[data-testid="hero-see-report"]').exists()).toBe(false);
  });

  it('a 98/182 media result is partial and sends the owner to the report', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'media', status: 'Skipped' }],
      media: { selected: true, copied: 98, failed: 182 },
      installed_modules: [],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-failed"]').text()).toContain(enCatalogue.setup.hero.partMedia);
    expect(w.find('[data-testid="hero-see-report"]').exists()).toBe(true);
  });

  // An app that is merely unsubscribed is a purchase decision, not a breakage (ADR-0060, hub#409) —
  // and there IS a report saying which one, so this door stays open for it too.
  it('offers the report when an app is only blocked on the plan', async () => {
    importBlueprint.mockResolvedValue({
      sections: [],
      installed_modules: [{ id: 'invoice', version: '1.0.0', status: 'blocked', blocked_on: ['invoice'] }],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-see-report"]').exists()).toBe(true);
  });

  // hub#488 — this is the FIRST screen of a new business, and the sentence is actionable: it sends
  // the owner to subscribe. `cash_register` is our manifest key, not the name he will find in the
  // marketplace.
  it('names the apps the way the owner will find them, not by their manifest id', async () => {
    appNames.set('cash_register', 'Caja registradora');
    appNames.set('verifactu', 'VeriFactu · AEAT');
    importBlueprint.mockResolvedValue({
      sections: [],
      installed_modules: [
        { id: 'cash_register', version: '1.0.0', status: 'blocked', blocked_on: ['cash_register'] },
        { id: 'verifactu', version: '1.4.1', status: 'failed', error: 'boom' },
      ],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-blocked"]').text()).toContain('Caja registradora');
    expect(w.find('[data-testid="hero-failed"]').text()).toContain('VeriFactu · AEAT');
    // The developer key must not survive next to the name: two names for one app is worse than one.
    expect(w.find('[data-testid="hero-outcome"]').text()).not.toContain('cash_register');
  });

  it('an app with no known name is still named — by its id, never left blank', async () => {
    importBlueprint.mockResolvedValue({
      sections: [],
      installed_modules: [{ id: 'cash_register', version: '1.0.0', status: 'blocked', blocked_on: ['cash_register'] }],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-blocked"]').text()).toContain('cash_register');
  });

  it('raises the same line when every app went in but a PART of the template did not', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [{ id: 'pos', version: '1.0.0', status: 'installed' }],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-failed"]').exists()).toBe(true);
  });

  // hub#899 — «Casi: algo no ha entrado» / «Hay algo MÁS que no ha entrado»: two «somethings» and
  // not one clue, at the minute the owner is checking whether her business is inside. When the
  // failure was an app, hub#751 already named it; when it was a SECTION, `failedApps` was empty and
  // the card fell back to the generic sentence. She could not tell whether she was missing a
  // service, the till or half her catalogue — and therefore could not decide whether to start
  // working or import again.
  it('NAMES the part of the template that did not go in, instead of "something else"', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [{ id: 'pos', version: '1.0.0', status: 'installed' }],
    });
    const w = await outcomeOf(mountCard());

    const failed = w.find('[data-testid="hero-failed"]');
    expect(failed.text()).toContain(enCatalogue.setup.hero.partSettings);
    // Never our manifest key, and never the sentence that says nothing.
    expect(failed.text()).not.toContain('hub_settings');
    expect(failed.text()).not.toBe(enCatalogue.setup.hero.failed);
  });

  it('calls the DATA of an app by the name of the app, not by its id', async () => {
    // `modules/<id>` is the app's catalogue — the services, the tables, the prices. The app itself
    // may be installed and running: «Hairdressing did not go in» would send her to reinstall
    // something that is right there, so the sentence says it is the DATA that is missing.
    appNames.set('hairdressing', 'Peluquería');
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'modules/hairdressing', status: { Failed: 'sql error' } }],
      installed_modules: [{ id: 'hairdressing', version: '1.0.0', status: 'installed' }],
    });
    const w = await outcomeOf(mountCard());

    const failed = w.find('[data-testid="hero-failed"]');
    expect(failed.text()).toContain('Peluquería');
    expect(failed.text()).not.toContain('modules/hairdressing');
  });

  it('says the apps AND the parts when both broke, without dropping either', async () => {
    appNames.set('verifactu', 'VeriFactu · AEAT');
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'media', status: 'Skipped' }],
      media: { selected: true, copied: 0, failed: 3 },
      installed_modules: [{ id: 'verifactu', version: '1.4.1', status: 'failed', error: 'boom' }],
    });
    const w = await outcomeOf(mountCard());

    const failed = w.find('[data-testid="hero-failed"]');
    expect(failed.text()).toContain('VeriFactu · AEAT');
    expect(failed.text()).toContain(enCatalogue.setup.hero.partMedia);
  });

  it('a part this shell does not know is still named, never swallowed', async () => {
    // A runtime newer than the app on this counter. Its key is ugly; a part that failed and nobody
    // ever mentioned is worse, and it is exactly what «something else» was.
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'something_new', status: { Failed: 'boom' } }],
      installed_modules: [],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-failed"]').text()).toContain('something_new');
  });

  it('says it in Spanish too — the language the till is used in', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [],
    });
    const w = await outcomeOf(mountCard(emptyBusiness(), i18nEs));

    expect(w.find('[data-testid="hero-failed"]').text()).toContain(esCatalogue.setup.hero.partSettings);
  });

  it('a template that could not even be opened changed NOTHING, and says so', async () => {
    downloadBlueprint.mockRejectedValue(new Error('checksum mismatch'));
    const w = await outcomeOf(mountCard());

    const failure = w.find('[data-testid="hero-outcome"]');
    expect(failure.text()).toContain(enCatalogue.setup.hero.notStartedBody);
    // Nothing was applied, so nothing may be claimed about the business: the import never ran, and
    // there is nothing for the rest of the shell to re-read either.
    expect(importBlueprint).not.toHaveBeenCalled();
    expect(refreshModuleNav).not.toHaveBeenCalled();
  });

  it('an import that broke does NOT claim the business was left untouched', async () => {
    importBlueprint.mockRejectedValue(new Error('runtime restarting'));
    const w = await outcomeOf(mountCard());

    const failure = w.find('[data-testid="hero-outcome"]');
    expect(failure.text()).toContain(enCatalogue.setup.hero.interruptedBody);
    expect(failure.text()).not.toContain(enCatalogue.setup.hero.notStartedBody);
  });

  it('stays up on the outcome even though the business is no longer empty', async () => {
    const w = mountCard();
    await flushPromises();
    await w.find('[data-testid="hero-use"]').trigger('click');
    await flushPromises();
    // The import ticked the very item this card reads: the panel re-reads it and hands it down.
    await w.setProps({ status: emptyBusiness('done') });
    await flushPromises();

    expect(w.find('[data-testid="hero-outcome"]').exists()).toBe(true);
  });

  it('goes away once the outcome has been read', async () => {
    const w = await outcomeOf(mountCard());

    await w.find('[data-testid="hero-continue"]').trigger('click');
    expect(w.find('[data-testid="hero-card"]').exists()).toBe(false);
  });
});

describe('the words', () => {
  it('are Spanish for a Spanish till', async () => {
    const w = mountCard(emptyBusiness(), i18nEs);
    await flushPromises();

    expect(w.find('[data-testid="hero-title"]').text()).toBe(esCatalogue.setup.hero.title);
    expect(w.find('[data-testid="hero-use"]').text()).toContain(esCatalogue.setup.hero.use);
  });

  it('warn BEFORE the click that the owner still has to add their own details', async () => {
    const w = mountCard();
    await flushPromises();

    // «One click = configured» is a promise this card cannot keep on its own, and saying it only
    // afterwards would be saying it too late.
    expect(w.find('[data-testid="hero-body"]').text()).toBe(enCatalogue.setup.hero.body);
    expect(enCatalogue.setup.hero.body).toMatch(/still/i);
    expect(esCatalogue.setup.hero.body).toMatch(/despu[eé]s|todav[ií]a|luego/i);
  });
});

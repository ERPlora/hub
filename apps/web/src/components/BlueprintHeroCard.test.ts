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

// A real `ref`: the card reads the permission of ADR-0248 off the session the runtime resolved.
const { session } = vi.hoisted(() => ({ session: { value: null as { permissions?: string[] } | null } }));
vi.mock('../lib/session', () => ({ user: session }));
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

  it('raises the same line when every app went in but a PART of the template did not', async () => {
    importBlueprint.mockResolvedValue({
      sections: [{ section: 'hub_settings', status: { Failed: 'db down' } }],
      installed_modules: [{ id: 'pos', version: '1.0.0', status: 'installed' }],
    });
    const w = await outcomeOf(mountCard());

    expect(w.find('[data-testid="hero-failed"]').exists()).toBe(true);
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

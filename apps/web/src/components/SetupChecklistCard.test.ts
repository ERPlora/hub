// @vitest-environment happy-dom
// The configuration card of the panel (hub#372) — the first of the three surfaces of
// `hub.setup.status`. What these tests protect is not the design, it is that the card tells the
// TRUTH about what the runtime answered:
//   - the three painted states are distinguishable from each other (and the fourth — omitted — is
//     not painted at all);
//   - an `unavailable` offers NO action: sending someone to a screen where they can do nothing
//     hands them a breakdown of ours as a chore;
//   - the counter is the query's, not the number of rows that fit in the card;
//   - a hub with nothing pending shows the finished state, and an empty list does not blow up.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// HubIcon bakes its SVGs through `~icons/…?raw`, which the test environment denies (same
// workaround as ImportPanel.test.ts / files-actions.test.ts).
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

// hub#1197 — the card folds tighter on a phone. `isPhoneViewport` is the shell's ONE reactive
// answer to "is this a phone?" (`lib/viewport.ts`, same pattern `AppTopbar.compact.test.ts` mocks
// for the topbar's own breakpoint); mocked here so each test can move it without touching a real
// `matchMedia`.
const { isPhoneViewport } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return { isPhoneViewport: ref(false) };
});
vi.mock('../lib/viewport', () => ({ isPhoneViewport }));

import SetupChecklistCard from './SetupChecklistCard.vue';
import {
  MAX_VISIBLE_ROWS,
  PHONE_MAX_VISIBLE_ROWS,
  parseSetupStatus,
  type SetupStatus,
} from '../lib/setup-status';
// REAL catalogues: English is the source language and Spanish is NOT optional (binding rule of
// 2026-08-04). A card with half its strings untranslated ships as half-Spanish.
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

// REAL messages: the card's honesty reaches the user through i18n interpolation, so a mute i18n
// would hide exactly what is checked here.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      setup: {
        title: 'Finish setting up',
        progress: '{done} of {total} done',
        viewAll: 'View all',
        viewLess: 'Show less',
        configure: 'Set up',
        review: 'Review configuration',
        doneLabel: 'Done',
        levelLegal: 'Needed to invoice',
        levelFunctional: 'Important',
        levelRecommended: 'Recommended',
        unavailableLabel: 'Not available yet',
        unavailableHint: 'This one is on us. There is nothing to do here yet.',
        delegatedHint: 'An administrator of this hub sets this up.',
        completeTitle: 'Your hub is ready',
        completeBody: 'Everything on the list is done.',
        items: {
          apps: { title: 'Tus apps', description: 'Instala al menos una app.' },
          business_identity: { title: 'Los datos de tu negocio', description: 'Razón social y NIF.' },
          team: { title: 'Tu equipo', description: 'Añade a quien usará el TPV.' },
        },
      },
    },
  },
});

function item(key: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key,
    source: key.includes('.') ? 'module' : 'core',
    module_id: key.includes('.') ? key.split('.')[0] : null,
    state: 'pending',
    required: true,
    level: 'functional',
    title: `Your ${key}`,
    description: `Set up ${key}.`,
    icon: 'settings-outline',
    route: `/${key}`,
    order: 10,
    actions: ['manual'],
    ...over,
  };
}

function status(items: Record<string, unknown>[], over: Record<string, unknown> = {}): SetupStatus | null {
  const count = (state: string) => items.filter((i) => i.state === state).length;
  return parseSetupStatus([
    {
      items,
      total: items.length,
      pending: count('pending'),
      unavailable: count('unavailable'),
      blocking_pending: items.filter((i) => i.state === 'pending' && i.level === 'legal').length,
      ...over,
    },
  ]);
}

interface CardProps {
  status: SetupStatus | null;
  alreadyOnScreen?: readonly string[];
}

beforeEach(() => {
  isPhoneViewport.value = false;
});

function mountCard(props: CardProps) {
  return mount(SetupChecklistCard, {
    props,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
}

/**
 * The card with its whole list open — the way a person opens it, by TAPPING the toggle (hub#487).
 *
 * It used to be a prop (`expandedByDefault`) whose only consumer was this file: documented as
 * «used by `/setup`», a screen that never existed. Going through the real control means these
 * tests would also catch a toggle that stopped working, which the prop could never do.
 */
async function mountExpanded(props: CardProps) {
  const w = mountCard(props);
  // No toggle means there was nothing folded, so the list is already whole — which is what the
  // caller asked for. Demanding the control here would fail on the short lists instead of on the
  // thing under test.
  const toggle = w.find('[data-testid="setup-toggle"]');
  if (toggle.exists()) await toggle.trigger('click');
  return w;
}

describe('the states are distinguishable on screen', () => {
  it('done, pending and unavailable paint rows you can tell apart', async () => {
    const w = await mountExpanded({
      status: status([
        item('apps', { state: 'unavailable' }),
        item('taxes.setup', { state: 'pending' }),
        item('inventory.setup', { state: 'done' }),
      ]),
    });

    const state = (key: string) => w.find(`[data-testid="setup-item-${key}"]`).attributes('data-state');
    expect(state('apps')).toBe('unavailable');
    expect(state('taxes.setup')).toBe('pending');
    expect(state('inventory.setup')).toBe('done');
    // Three states, three different marks: if two share a mark, the user cannot tell them apart.
    expect(new Set([state('apps'), state('taxes.setup'), state('inventory.setup')]).size).toBe(3);
  });

  it('the fourth state — omitted — is not painted: what did not come in the query is not here', async () => {
    const w = await mountExpanded({ status: status([item('apps')]) });

    expect(w.findAll('[data-testid^="setup-item-"]')).toHaveLength(1);
    expect(w.find('[data-testid="setup-item-verifactu.setup"]').exists()).toBe(false);
  });

  it('each state carries its mark: pill and icon are not repeated across states', async () => {
    const w = await mountExpanded({
      status: status([
        item('apps', { state: 'unavailable' }),
        item('taxes.setup', { state: 'pending' }),
        item('inventory.setup', { state: 'done' }),
      ]),
    });

    const pill = (key: string) => w.find(`[data-testid="setup-item-${key}"] ok-status-pill`);
    const tones = ['apps', 'taxes.setup', 'inventory.setup'].map((k) => pill(k).attributes('tone'));
    expect(tones).toEqual(['info', 'warning', 'success']);

    const icon = (key: string) => w.find(`[data-testid="setup-item-${key}"] .setup-row-icon`).attributes('name');
    // The icon says the state before you read anything: done ≠ broken ≠ the item's own icon.
    expect(icon('inventory.setup')).toBe('checkmark-circle-outline');
    expect(icon('apps')).toBe('cloud-offline-outline');
    expect(icon('taxes.setup')).toBe('settings-outline');
  });

  it('⛔ and 🔴 are not painted alike: the level travels on the row as the core gave it', () => {
    const w = mountCard({
      status: status([
        item('business_identity', { level: 'legal' }),
        item('taxes.setup', { level: 'functional' }),
      ]),
    });

    expect(w.find('[data-testid="setup-item-business_identity"]').attributes('data-level')).toBe('legal');
    expect(w.find('[data-testid="setup-item-taxes.setup"]').attributes('data-level')).toBe('functional');
    // ⛔ is red because the runtime REJECTS without it; 🔴 has no gate behind it. Same colour =
    // a protection promised that does not exist.
    const tone = (key: string) => w.find(`[data-testid="setup-item-${key}"] ok-status-pill`).attributes('tone');
    expect(tone('business_identity')).toBe('danger');
    expect(tone('taxes.setup')).toBe('warning');
  });

  it('🟡 never alerts: its pill is neutral, not the one of the level that does block', () => {
    const w = mountCard({ status: status([item('team', { level: 'recommended' })]) });

    expect(w.find('[data-testid="setup-item-team"] ok-status-pill').attributes('tone')).toBe('neutral');
  });
});

describe('`unavailable` offers no action', () => {
  it('the broken row carries neither a button nor a route to send anyone to', async () => {
    const w = await mountExpanded({
      status: status([item('apps', { state: 'unavailable', route: '/apps#catalog' })]),
    });

    const row = w.find('[data-testid="setup-item-apps"]');
    expect(row.exists()).toBe(true);
    expect(w.find('[data-testid="setup-action-apps"]').exists()).toBe(false);
    // Not even a hidden link: the item's route appears nowhere in the row.
    expect(row.html()).not.toContain('/apps#catalog');
  });

  it('and it says WHY: with no explanation, a mute item looks like a broken product', async () => {
    const w = await mountExpanded({
      status: status([item('apps', { state: 'unavailable' })]),
    });

    expect(w.find('[data-testid="setup-note-apps"]').exists()).toBe(true);
    expect(w.text()).toContain('nothing to do here yet');
  });

  it('a pending one DOES carry its action, pointing at the route the query gave', () => {
    const w = mountCard({ status: status([item('taxes.setup', { route: '/m/taxes/rules' })]) });

    const cta = w.find('[data-testid="setup-action-taxes.setup"]');
    expect(cta.exists()).toBe(true);
    // The route is the one the query gave (the `ion-button` stub lowercases it to `routerlink`).
    expect(cta.html()).toContain('/m/taxes/rules');
  });

  it('what is done asks for nothing either', async () => {
    const w = await mountExpanded({ status: status([item('team', { state: 'done' })]) });

    expect(w.find('[data-testid="setup-action-team"]').exists()).toBe(false);
  });
});

describe('a wall somebody ELSE has to bring down (hub#435)', () => {
  it('offers no way in: this session would be refused on the other side', () => {
    const w = mountCard({
      status: status([item('business_identity', { level: 'legal', actionable: false, route: '/settings' })]),
    });

    const row = w.find('[data-testid="setup-item-business_identity"]');
    expect(row.exists()).toBe(true);
    expect(w.find('[data-testid="setup-action-business_identity"]').exists()).toBe(false);
    expect(row.html()).not.toContain('/settings');
  });

  it('and it says WHO can: naming nobody leaves the user with a wall and no door', () => {
    const w = mountCard({
      status: status([item('business_identity', { level: 'legal', actionable: false })]),
    });

    expect(w.find('[data-testid="setup-note-business_identity"]').exists()).toBe(true);
    expect(w.text()).toContain('administrator');
  });

  it('it keeps its ⛔ pill: it is still what the runtime is going to reject', () => {
    const w = mountCard({
      status: status([item('business_identity', { level: 'legal', actionable: false })]),
    });

    expect(w.find('[data-testid="setup-item-business_identity"] ok-status-pill').attributes('tone')).toBe('danger');
  });

  it('it is not read as our breakdown: `unavailable` says something else entirely', () => {
    // Their administrator has to type a tax id; nothing is broken on our side. Borrowing that state
    // would tell the user to wait for a fix that is never coming.
    const w = mountCard({
      status: status([item('business_identity', { level: 'legal', actionable: false })]),
    });

    expect(w.text()).not.toContain('on us');
    expect(w.find('[data-testid="setup-item-business_identity"]').attributes('data-state')).toBe('pending');
  });

  it('an actionable pending item keeps its button, of course', () => {
    const w = mountCard({
      status: status([item('business_identity', { level: 'legal', actionable: true, route: '/settings' })]),
    });

    expect(w.find('[data-testid="setup-action-business_identity"]').exists()).toBe(true);
    expect(w.find('[data-testid="setup-note-business_identity"]').exists()).toBe(false);
  });
});

describe('the counter is the query\'s', () => {
  it('counts the whole hub even when fewer rows fit on screen', () => {
    const items = [
      ...Array.from({ length: 7 }, (_, n) => item(`m${n}.setup`)),
      item('apps', { state: 'done' }),
      item('team', { state: 'done' }),
    ];
    const w = mountCard({ status: status(items) });

    expect(w.find('[data-testid="setup-progress"]').text()).toBe('2 of 9 done');
    expect(w.findAll('[data-testid^="setup-item-"]').length).toBeLessThan(9);
  });

  it('an `unavailable` does not fatten the done counter', () => {
    const w = mountCard({ status: status([item('apps', { state: 'unavailable' }), item('team', { state: 'done' })]) });

    expect(w.find('[data-testid="setup-progress"]').text()).toBe('1 of 2 done');
  });

  it('the meter measures what is DONE over the total, not what is missing', () => {
    const items = [item('apps', { state: 'done' }), item('team'), item('taxes.setup'), item('inventory.setup')];
    const w = mountCard({ status: status(items) });

    expect(w.find('[data-testid="setup-meter"]').attributes('value')).toBe('0.25');
  });
});

describe('the edges', () => {
  it('a hub with nothing pending shows the FINISHED state, not an empty list', () => {
    const w = mountCard({ status: status([item('apps', { state: 'done' }), item('team', { state: 'done' })]) });

    expect(w.find('[data-testid="setup-complete"]').exists()).toBe(true);
    expect(w.findAll('[data-testid^="setup-item-"]')).toHaveLength(0);
    expect(w.text()).toContain('Your hub is ready');
  });

  it('with something pending the ending is NOT celebrated', () => {
    const w = mountCard({ status: status([item('apps', { state: 'done' }), item('team')]) });

    expect(w.find('[data-testid="setup-complete"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-item-team"]').exists()).toBe(true);
  });

  it('a breakdown is no ending either: something is left to fix, even if not by them', () => {
    const w = mountCard({ status: status([item('apps', { state: 'unavailable' })]) });

    expect(w.find('[data-testid="setup-complete"]').exists()).toBe(false);
  });

  it('an empty list paints no card and does not blow up', () => {
    const w = mountCard({ status: status([]) });

    expect(w.find('[data-testid="setup-card"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-complete"]').exists()).toBe(false);
  });

  it('with no document yet (early boot) there is no card either', () => {
    const w = mountCard({ status: null });

    expect(w.find('[data-testid="setup-card"]').exists()).toBe(false);
  });
});

describe('what folds and what shows', () => {
  it('🟡 goes behind «view all», and shows up once expanded', async () => {
    const w = mountCard({
      status: status([item('taxes.setup'), item('printing.setup', { level: 'recommended' })]),
    });

    expect(w.find('[data-testid="setup-item-printing.setup"]').exists()).toBe(false);
    await w.find('[data-testid="setup-toggle"]').trigger('click');

    expect(w.find('[data-testid="setup-item-printing.setup"]').exists()).toBe(true);
  });

  it('with nothing folded there is no «view all» on offer', () => {
    const w = mountCard({ status: status([item('taxes.setup')]) });

    expect(w.find('[data-testid="setup-toggle"]').exists()).toBe(false);
  });
});

// hub#1197 — at 390px the desktop fold (5 rows) was, by itself, most of a screen and a half. The
// card folds tighter on a phone: progress + a couple of items that need the owner right now, «view
// all» one tap away — same trade Square/Shopify's mobile onboarding makes, and the same door
// (`setup-toggle`) desktop already had.
describe('the phone fold (hub#1197)', () => {
  const nine = Array.from({ length: 9 }, (_, n) => item(`m${n}.setup`));

  it('shows only PHONE_MAX_VISIBLE_ROWS on a phone, not the desktop MAX_VISIBLE_ROWS', () => {
    isPhoneViewport.value = true;
    const w = mountCard({ status: status(nine) });

    expect(w.findAll('[data-testid^="setup-item-"]')).toHaveLength(PHONE_MAX_VISIBLE_ROWS);
    expect(PHONE_MAX_VISIBLE_ROWS).toBeLessThan(MAX_VISIBLE_ROWS);
  });

  it('off the phone the card keeps the desktop default', () => {
    isPhoneViewport.value = false;
    const w = mountCard({ status: status(nine) });

    expect(w.findAll('[data-testid^="setup-item-"]')).toHaveLength(MAX_VISIBLE_ROWS);
  });

  it('«view all» still opens the WHOLE list on a phone, not just the desktop cap', async () => {
    isPhoneViewport.value = true;
    const w = mountCard({ status: status(nine) });

    await w.find('[data-testid="setup-toggle"]').trigger('click');

    expect(w.findAll('[data-testid^="setup-item-"]')).toHaveLength(9);
  });

  it('the counter never shrinks with the fold — it stays the query\'s', () => {
    isPhoneViewport.value = true;
    const w = mountCard({ status: status(nine) });

    expect(w.find('[data-testid="setup-progress"]').text()).toContain('9');
  });
});

describe('decision 1 and the titles', () => {
  it('with the apps card in sight, the checklist starts at item 2', () => {
    const w = mountCard({
      status: status([item('apps'), item('business_identity', { level: 'legal' })]),
      alreadyOnScreen: ['apps'],
    });

    expect(w.find('[data-testid="setup-item-apps"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-item-business_identity"]').exists()).toBe(true);
  });

  it('a core item is translated by its key; a module one uses the title that came', async () => {
    const w = await mountExpanded({
      status: status([item('team', { level: 'recommended' }), item('taxes.setup', { title: 'Your taxes' })]),
    });

    // A core item's key IS its i18n key (the English title travels as the fallback).
    expect(w.text()).toContain('Tu equipo');
    // The runtime does not localize a module's `title` yet: the manifest's is painted, never an
    // untranslated key.
    expect(w.text()).toContain('Your taxes');
    expect(w.text()).not.toContain('setup.items.taxes');
  });

  it('offers to hand the configuration to the assistant without deciding for them', async () => {
    const w = mountCard({ status: status([item('taxes.setup')]) });

    await w.find('[data-testid="setup-review"]').trigger('click');
    expect(w.emitted('review')).toHaveLength(1);
  });
});

// hub#1905 — a salon imported from a template had «Configure VeriFactu» pending and a «Set up»
// button to VeriFactu's own settings, already filled in. What was missing was the switch in
// Settings → Permissions, and the row never said so; the first sale went out with no fiscal record.
describe('an item pending on a PERMISSION (hub#1905)', () => {
  const realI18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue },
  });
  const setupEn = (enCatalogue as unknown as { setup: Record<string, string> }).setup;
  const permissionItem = item('verifactu.setup', {
    title: 'Configure VeriFactu',
    missing_capabilities: ['certificate'],
    route: '/settings?tab=permissions',
  });

  function mountReal(props: CardProps) {
    return mount(SetupChecklistCard, {
      props,
      global: { plugins: [realI18n], renderStubDefaultSlot: true },
      shallow: true,
    });
  }

  it('says that a permission is what is left, in the owner\'s words', () => {
    const w = mountReal({ status: status([permissionItem]) });

    const note = w.find('[data-testid="setup-note-verifactu.setup"]');
    expect(note.exists(), 'a row pending on a switch must say it is the switch').toBe(true);
    expect(note.text()).toBe(setupEn.missingPermissionHint);
  });

  it('its button names the consequence and goes where the permission is granted', () => {
    const w = mountReal({ status: status([permissionItem]) });

    const cta = w.find('[data-testid="setup-action-verifactu.setup"]');
    expect(cta.exists()).toBe(true);
    expect(cta.html()).toContain('/settings?tab=permissions');
    expect(cta.text()).toBe(setupEn.grantPermission);
  });

  it('a row with every permission granted keeps its own words', () => {
    const w = mountReal({ status: status([item('verifactu.setup', { missing_capabilities: [] })]) });

    expect(w.find('[data-testid="setup-note-verifactu.setup"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-action-verifactu.setup"]').text()).toBe(setupEn.configure);
  });

  it('a wall somebody else has to bring down still says WHO, not which switch', () => {
    // Not theirs to grant: pointing a waiter at Settings → Permissions sends them to a screen that
    // refuses them. The delegated hint of hub#435 wins.
    const w = mountReal({
      status: status([
        item('verifactu.setup', { level: 'legal', actionable: false, missing_capabilities: ['certificate'] }),
      ]),
    });

    expect(w.find('[data-testid="setup-note-verifactu.setup"]').text()).toBe(setupEn.delegatedHint);
  });
});

describe('the strings', () => {
  /** Every leaf key of a message block, in dot notation. */
  function leafKeys(node: unknown, prefix = ''): string[] {
    if (typeof node !== 'object' || node === null) return [prefix];
    return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
      leafKeys(v, prefix ? `${prefix}.${k}` : k),
    );
  }

  it('the whole checklist exists in English (source) and in Spanish', () => {
    const en = (enCatalogue as Record<string, unknown>).setup;
    const es = (esCatalogue as Record<string, unknown>).setup;
    expect(en, 'the `setup` block is missing from the English catalogue').toBeTruthy();

    expect(leafKeys(es).sort()).toEqual(leafKeys(en).sort());
  });

  it('every key the component paints is in the English catalogue', () => {
    // Path relative to the vitest root (apps/web): under happy-dom `import.meta.url` is not file://.
    const source = readFileSync('src/components/SetupChecklistCard.vue', 'utf8');
    const used = [...source.matchAll(/t\('(setup\.[\w.]+)'\)/g)].map((m) => m[1]);
    // The core item ones resolve through the item key (`setup.items.<key>.title`), so they are
    // checked apart: they are the three the runtime emits (`CORE_ITEMS`).
    const core = ['apps', 'business_identity', 'team'].flatMap((k) => [
      `setup.items.${k}.title`,
      `setup.items.${k}.description`,
    ]);
    const available = new Set(leafKeys({ setup: (enCatalogue as Record<string, unknown>).setup }));

    expect(used.length).toBeGreaterThan(5);
    for (const key of [...used, ...core]) {
      expect(available.has(key), `${key} is missing from the English catalogue`).toBe(true);
    }
  });
});

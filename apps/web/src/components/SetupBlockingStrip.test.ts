// @vitest-environment happy-dom
// The blocking strip (hub#374) — the third surface of `hub.setup.status`, and the only one the
// person at the till ever sees: they do not open the panel, so the checklist card cannot reach them.
//
// What these tests protect is that the strip earns the room it takes on EVERY screen:
//   - it is there when the runtime is going to reject the sale, and nowhere else;
//   - it names what is missing and every name carries its own way in;
//   - it does not repeat the panel's card on the panel's own screen.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// HubIcon bakes its SVGs through `~icons/…?raw`, which the test environment denies (same
// workaround as SetupChecklistCard.test.ts).
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

// hub#2272 — on a short screen (a phone on its side) the strip folds to one row. `isShortViewport` is
// the shell's ONE reactive answer to "is the screen short?" (`lib/viewport.ts`); mocked here so each
// test can move it without touching a real `matchMedia`.
const { isShortViewport } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return { isShortViewport: ref(false) };
});
vi.mock('../lib/viewport', () => ({ isShortViewport }));

beforeEach(() => {
  isShortViewport.value = false;
});

import SetupBlockingStrip from './SetupBlockingStrip.vue';
import { parseSetupStatus, type SetupStatus } from '../lib/setup-status';
// The REAL English catalogue: the strip's whole job is saying something true out loud, so testing
// it against invented strings would test nothing. English is the source language (2026-08-04).
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: enCatalogue },
});

function item(key: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key,
    source: key.includes('.') ? 'module' : 'core',
    module_id: key.includes('.') ? key.split('.')[0] : null,
    state: 'pending',
    required: true,
    level: 'legal',
    title: `Your ${key}`,
    description: `Set up ${key}.`,
    icon: 'settings-outline',
    route: `/${key}`,
    order: 40,
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

function mountStrip(props: { status: SetupStatus | null; checklistOnScreen?: boolean }) {
  return mount(SetupBlockingStrip, {
    props,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
    shallow: true,
  });
}

describe('it takes the room only when the runtime says no', () => {
  it('is on screen while something is ⛔ and pending', () => {
    const w = mountStrip({ status: status([item('business_identity')]) });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(true);
  });

  it('paints nothing at all when nothing blocks', () => {
    // Not an empty box, not a spacer: nothing. The strip lives above every screen of the product,
    // so «harmless when idle» is not good enough — it has to be absent.
    const w = mountStrip({
      status: status([item('apps', { level: 'functional' }), item('team', { level: 'recommended' })]),
    });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(false);
    expect(w.find('ok-inline-feedback').exists()).toBe(false);
    expect(w.text()).toBe('');
  });

  it('paints nothing before the first answer arrives', () => {
    expect(mountStrip({ status: null }).find('[data-testid="setup-strip"]').exists()).toBe(false);
  });
});

describe('it says what is missing and leads to it', () => {
  it('names every blocking item and gives each one its own way in', () => {
    // There are at most two gates (the business identity and the certificate), so there is no
    // «primary» one to pick: picking would hide the other behind a guess.
    const w = mountStrip({
      status: status([
        item('business_identity', { route: '/settings' }),
        item('verifactu.setup', { title: 'Configure VeriFactu', route: '/m/verifactu' }),
      ]),
    });

    expect(w.find('[data-testid="setup-strip-item-business_identity"]').exists()).toBe(true);
    // `routerlink` and not `router-link`: that is how the test utils flatten the prop of the stub.
    expect(w.find('[data-testid="setup-strip-action-business_identity"]').attributes('routerlink')).toBe(
      '/settings',
    );
    expect(w.find('[data-testid="setup-strip-action-verifactu.setup"]').attributes('routerlink')).toBe(
      '/m/verifactu',
    );
  });

  it('does not name what is not blocking', () => {
    const w = mountStrip({
      status: status([item('business_identity'), item('team', { level: 'recommended' })]),
    });

    expect(w.find('[data-testid="setup-strip-item-team"]').exists()).toBe(false);
  });

  it('translates a core item by its key and paints a module title as it came', () => {
    const w = mountStrip({
      status: status([item('business_identity'), item('verifactu.setup', { title: 'Configure VeriFactu' })]),
    });

    // A core item's key IS its i18n key (§6bis); the English `title` in the payload is the fallback.
    expect(w.text()).toContain('Your business details');
    // The runtime does not localize a module's `setup.title` yet: its manifest value is painted, and
    // a raw key never is.
    expect(w.text()).toContain('Configure VeriFactu');
    expect(w.text()).not.toContain('setup.items.verifactu');
  });

  it('says the consequence, not just the name of the task', () => {
    // «Your business details» on its own reads as one more chore. What makes this strip worth a band
    // across every screen is the sentence that says the hub will refuse to invoice.
    const w = mountStrip({ status: status([item('business_identity')]) });

    // The headline travels as `ok-inline-feedback`'s `heading` attribute; the body is its content.
    expect(w.find('[data-testid="setup-strip"]').attributes('heading')).toBe(enCatalogue.setup.blocking.title);
    expect(w.text()).toContain(enCatalogue.setup.blocking.body);
  });

  it('cannot be dismissed: it goes when the hub is fixed, not when it is waved away', () => {
    const w = mountStrip({ status: status([item('business_identity')]) });

    expect(w.find('[data-testid="setup-strip"]').attributes('dismissible')).toBeUndefined();
  });
});

describe('a wall the person in front of it cannot bring down (hub#435)', () => {
  it('is still up: the strip exists FOR the session that gets the sale refused', () => {
    // The cashier cannot type the tax id, but `enforce_fiscal_precondition` refuses THEIR sale all
    // the same. Hiding the band from them would leave the refusal arriving out of nowhere.
    const w = mountStrip({ status: status([item('business_identity', { actionable: false })]) });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(true);
    expect(w.find('[data-testid="setup-strip-item-business_identity"]').exists()).toBe(true);
  });

  it('but it leads nowhere: that screen would refuse them too', () => {
    const w = mountStrip({
      status: status([item('business_identity', { actionable: false, route: '/settings' })]),
    });

    expect(w.find('[data-testid="setup-strip-action-business_identity"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-strip-item-business_identity"]').html()).not.toContain('/settings');
  });

  it('and it says who can, so the band is not a dead end', () => {
    const w = mountStrip({ status: status([item('business_identity', { actionable: false })]) });

    expect(w.find('[data-testid="setup-strip-note-business_identity"]').exists()).toBe(true);
    expect(w.text()).toContain('administrator');
  });

  it('each item answers for itself: one delegated wall does not mute the other one’s way in', () => {
    const w = mountStrip({
      status: status([
        item('business_identity', { actionable: false, route: '/settings' }),
        item('verifactu.setup', { title: 'Configure VeriFactu', route: '/m/verifactu' }),
      ]),
    });

    expect(w.find('[data-testid="setup-strip-action-business_identity"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-strip-action-verifactu.setup"]').attributes('routerlink')).toBe(
      '/m/verifactu',
    );
    expect(w.find('[data-testid="setup-strip-note-verifactu.setup"]').exists()).toBe(false);
  });
});

describe('not twice on the same screen', () => {
  it('stands down where the panel already paints the whole checklist', () => {
    const w = mountStrip({ status: status([item('business_identity')]), checklistOnScreen: true });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(false);
  });

  it('is up on every other screen', () => {
    const w = mountStrip({ status: status([item('business_identity')]), checklistOnScreen: false });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(true);
  });
});

// hub#2272 — on a phone held sideways (667×375) the whole strip took ~113px of the 375 and the till's
// open ticket was left without room for one line. On a short screen it folds to ONE row: the headline
// and a way to open what is missing. What it must not lose while folded is the part that justifies
// the band: that the hub will refuse, and a way through to every missing thing.
describe('on a short screen it folds to one row (hub#2272)', () => {
  const blocking = () =>
    status([
      item('business_identity', { route: '/settings' }),
      item('verifactu.setup', { title: 'Configure VeriFactu', route: '/m/verifactu' }),
    ]);

  it('keeps the headline and offers the rest behind one toggle', () => {
    isShortViewport.value = true;
    const w = mountStrip({ status: blocking() });

    expect(w.find('[data-testid="setup-strip"]').exists()).toBe(true);
    expect(w.find('[data-testid="setup-strip-title"]').text()).toBe(enCatalogue.setup.blocking.title);
    const toggle = w.find('[data-testid="setup-strip-toggle"]');
    expect(toggle.exists()).toBe(true);
    expect(toggle.attributes('aria-expanded')).toBe('false');
    expect(toggle.text()).toBe(enCatalogue.setup.blocking.showMissing);
  });

  it('paints the headline ONCE: not as the band heading and again in the row', () => {
    isShortViewport.value = true;
    const w = mountStrip({ status: blocking() });

    expect(w.find('[data-testid="setup-strip"]').attributes('heading')).toBeUndefined();
    expect(w.html().split(enCatalogue.setup.blocking.title).length - 1).toBe(1);
  });

  it('folded, the body and the list are not there — not hidden, absent', () => {
    // Absent and not `display:none`: a folded list left in the DOM would still be read out and
    // tabbed through, two copies of every «Set up» button of which one is invisible.
    isShortViewport.value = true;
    const w = mountStrip({ status: blocking() });

    expect(w.text()).not.toContain(enCatalogue.setup.blocking.body);
    expect(w.find('.setup-strip-items').exists()).toBe(false);
    expect(w.find('[data-testid="setup-strip-action-business_identity"]').exists()).toBe(false);
  });

  it('one tap opens what is missing, each with its own way in, and a second tap folds it back', async () => {
    isShortViewport.value = true;
    const w = mountStrip({ status: blocking() });

    await w.find('[data-testid="setup-strip-toggle"]').trigger('click');

    const toggle = w.find('[data-testid="setup-strip-toggle"]');
    expect(toggle.attributes('aria-expanded')).toBe('true');
    expect(toggle.text()).toBe(enCatalogue.setup.blocking.hideMissing);
    expect(w.text()).toContain(enCatalogue.setup.blocking.body);
    expect(w.find('[data-testid="setup-strip-action-business_identity"]').attributes('routerlink')).toBe(
      '/settings',
    );
    expect(w.find('[data-testid="setup-strip-action-verifactu.setup"]').attributes('routerlink')).toBe(
      '/m/verifactu',
    );
    // The toggle says which region it opens.
    expect(toggle.attributes('aria-controls')).toBe(w.find('.setup-strip-detail').attributes('id'));

    await toggle.trigger('click');

    expect(w.find('[data-testid="setup-strip-toggle"]').attributes('aria-expanded')).toBe('false');
    expect(w.find('.setup-strip-items').exists()).toBe(false);
  });

  it('a delegated wall still says who can, once opened', async () => {
    isShortViewport.value = true;
    const w = mountStrip({ status: status([item('business_identity', { actionable: false })]) });

    await w.find('[data-testid="setup-strip-toggle"]').trigger('click');

    expect(w.find('[data-testid="setup-strip-note-business_identity"]').exists()).toBe(true);
  });

  it('turning the phone upright gives the full strip back, with no toggle left over', async () => {
    isShortViewport.value = true;
    const w = mountStrip({ status: blocking() });

    isShortViewport.value = false;
    await w.vm.$nextTick();

    expect(w.find('[data-testid="setup-strip-toggle"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-strip"]').attributes('heading')).toBe(enCatalogue.setup.blocking.title);
    expect(w.text()).toContain(enCatalogue.setup.blocking.body);
    expect(w.find('[data-testid="setup-strip-action-business_identity"]').exists()).toBe(true);
  });

  it('on a tall screen there is no fold at all', () => {
    const w = mountStrip({ status: blocking() });

    expect(w.find('[data-testid="setup-strip-toggle"]').exists()).toBe(false);
    expect(w.find('[data-testid="setup-strip-title"]').exists()).toBe(false);
  });
});

describe('the strings', () => {
  it('every key the strip paints exists in English and in Spanish', () => {
    const source = readFileSync('src/components/SetupBlockingStrip.vue', 'utf8');
    const used = [...source.matchAll(/t\('(setup\.[\w.]+)'\)/g)].map((m) => m[1]);
    expect(used.length).toBeGreaterThan(1);

    const leaf = (cat: Record<string, unknown>, key: string): unknown =>
      key.split('.').reduce<unknown>((node, k) => (node as Record<string, unknown> | undefined)?.[k], cat);

    for (const key of used) {
      expect(typeof leaf(enCatalogue as Record<string, unknown>, key), `${key} missing in English`).toBe('string');
      expect(typeof leaf(esCatalogue as Record<string, unknown>, key), `${key} missing in Spanish`).toBe('string');
    }
  });
});

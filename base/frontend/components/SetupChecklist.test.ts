// «Finish setting up your business» (BASE-G22, BASE-G130, BASE-G164; hub#372): one live read of
// `base.setup.status`, painted as the server ordered and filtered it. «Set up» only where a screen exists and
// the person can do it; a ⛔ only an administrator can do says so; folded to 5 rows (2 on a phone).
import { IonProgressBar } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SetupItem, SetupStatus } from '../operations';
import { errorFrame, flush, memoryStorage, mountBase, subId } from '../__tests__/mount-base';
import { createAssistant, installAssistant } from '../lib/assistant';
import SetupChecklist from './SetupChecklist.vue';

function item(key: string, fields: Partial<SetupItem> = {}): SetupItem {
  return {
    key,
    app: key.split('.')[0],
    state: 'pending',
    level: 'functional',
    required: true,
    actionable: true,
    title: `Title ${key}`,
    description: `About ${key}`,
    icon: 'ion:settings-outline',
    route: `/${key.replace('.', '/')}`,
    order: 50,
    ...fields,
  };
}

function status(items: SetupItem[]): SetupStatus {
  const pending = items.filter((i) => i.state === 'pending').length;
  const unavailable = items.filter((i) => i.state === 'unavailable').length;
  const blocking = items.filter((i) => i.state === 'pending' && i.level === 'legal').length;
  return { total: items.length, pending, unavailable, blocking_pending: blocking, items };
}

async function setup(options: { routes?: string[]; locale?: 'en' | 'es' } = {}) {
  const m = await mountBase(SetupChecklist, options);
  const call = await m.live();
  const show = (data: SetupStatus, rev?: number) => m.result(call, 'base.setup.status', data, rev);
  const rows = () => m.wrapper.findAll('[data-testid="setup-row"]');
  return { ...m, call, show, rows };
}

afterEach(() => vi.unstubAllGlobals());

describe('SetupChecklist', () => {
  it('follows base.setup.status live, with no parameters', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.setup.status').map((sub) => sub.params)).toEqual([{}]);
    expect(s.wrapper.get('[data-testid="setup-card"]').attributes('aria-busy')).toBe('true');
  });

  it('heads the card with how much is done and a bar of it', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(status([item('a.one', { state: 'done' }), item('a.two'), item('a.three'), item('a.four')]));
    expect(s.wrapper.get('h2').text()).toBe('Termina de configurar tu negocio');
    expect(s.wrapper.get('[data-testid="setup-progress"]').text()).toBe('1 de 4 hechos');
    expect(s.wrapper.getComponent(IonProgressBar).props('value')).toBe(0.25);
  });

  it('paints each row with its icon, title, description and the pill of its level', async () => {
    const s = await setup({ locale: 'es', routes: ['/a/legal', '/a/func', '/a/rec'] });
    await s.show(
      status([item('a.legal', { level: 'legal' }), item('a.func'), item('a.rec', { level: 'recommended' })]),
    );
    expect(s.rows().map((row) => row.get('[data-testid="setup-pill"]').text())).toEqual([
      'Necesario para facturar',
      'Importante',
    ]);
    expect(s.rows()[0].text()).toContain('Title a.legal');
    expect(s.rows()[0].text()).toContain('About a.legal');
    expect(s.rows()[0].get('[data-testid="setup-pill"]').attributes('data-tone')).toBe('danger');
  });

  it('«Set up» opens the screen of the step (BASE-G130)', async () => {
    const s = await setup({ routes: ['/a/one'] });
    await s.show(status([item('a.one')]));
    const configure = s.wrapper.get('[data-testid="setup-configure-a.one"]');
    expect(configure.text()).toBe('Set up');
    await configure.trigger('click');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/a/one');
  });

  it('has no «Set up» while the screen does not exist yet: a button to the 404 is worse than none', async () => {
    const s = await setup();
    await s.show(status([item('a.one')]));
    expect(s.wrapper.find('[data-testid="setup-configure-a.one"]').exists()).toBe(false);
  });

  it('a pending step this person cannot do says an administrator has to, with no button (BASE-G164)', async () => {
    const s = await setup({ locale: 'es', routes: ['/invoice/business_identity'] });
    await s.show(status([item('invoice.business_identity', { level: 'legal', actionable: false })]));
    expect(s.wrapper.find('[data-testid="setup-configure-invoice.business_identity"]').exists()).toBe(false);
    expect(s.wrapper.get('[data-testid="setup-note-invoice.business_identity"]').text()).toBe(
      'Esto lo tiene que configurar un administrador.',
    );
  });

  it('a step that is ours to fix says so, never as a task', async () => {
    const s = await setup({ locale: 'es', routes: ['/a/ours'] });
    await s.show(status([item('a.ours', { state: 'unavailable' })]));
    const row = s.rows()[0];
    expect(row.get('[data-testid="setup-pill"]').text()).toBe('Todavía no disponible');
    expect(row.text()).toContain('Esto es cosa nuestra');
    expect(row.find('[data-testid="setup-configure-a.ours"]').exists()).toBe(false);
  });

  it('folds to five rows on a desk, «View all» shows every step (done ones too) and «Show less» folds back', async () => {
    const s = await setup();
    const items = [item('base.apps'), ...['1', '2', '3', '4', '5', '6'].map((n) => item(`a.s${n}`)), item('a.ok', { state: 'done' })];
    await s.show(status(items));
    // «Your apps» is the «My apps» card's: not repeated in the folded list.
    expect(s.rows().map((row) => row.attributes('data-key'))).toEqual(['a.s1', 'a.s2', 'a.s3', 'a.s4', 'a.s5']);
    await s.wrapper.get('[data-testid="setup-toggle"]').trigger('click');
    expect(s.rows()).toHaveLength(8);
    expect(s.wrapper.get('[data-testid="setup-toggle"]').text()).toBe('Show less');
    await s.wrapper.get('[data-testid="setup-toggle"]').trigger('click');
    expect(s.rows()).toHaveLength(5);
  });

  it('folds to two rows on a phone', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: () => {}, removeEventListener: () => {} }));
    const s = await setup();
    await s.show(status([item('a.s1'), item('a.s2'), item('a.s3')]));
    expect(s.rows()).toHaveLength(2);
    expect(s.wrapper.get('[data-testid="setup-toggle"]').text()).toBe('View all');
  });

  it('with nothing left: «Your business is ready», no rows', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(status([item('a.one', { state: 'done' })]));
    expect(s.wrapper.get('h2').text()).toBe('Tu negocio está listo');
    expect(s.wrapper.get('[data-testid="setup-complete"]').text()).toBe('No queda nada pendiente en la checklist.');
    expect(s.rows()).toHaveLength(0);
  });

  it('with no step at all, paints nothing (silence is not «ready»)', async () => {
    const s = await setup();
    await s.show(status([]));
    expect(s.wrapper.find('[data-testid="setup-card"]').exists()).toBe(false);
  });

  it('a new result (a step done anywhere in the business) updates the card in place', async () => {
    const s = await setup({ routes: ['/a/one', '/a/two'] });
    await s.show(status([item('a.one'), item('a.two')]));
    await s.show(status([item('a.one', { state: 'done' }), item('a.two')]), 2);
    expect(s.wrapper.get('[data-testid="setup-progress"]').text()).toBe('1 of 2 done');
    expect(s.rows().map((row) => row.attributes('data-key'))).toEqual(['a.two']);
  });

  it('a failed read says so, with «Retry»', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'base.setup.status'), 'internal'));
    await flush();
    const error = s.wrapper.get('[data-testid="setup-error"]');
    expect(error.text()).toContain('Could not load what is left to set up');
    expect(error.find('[data-testid="setup-retry"]').exists()).toBe(true);
  });
  // BASE-G121 (gh:hub#373): «Ask the assistant» opens its panel on the setup; every step keeps its own «Set up».
  it('«Ask the assistant» opens the assistant on the setup, while something is left', async () => {
    const assistant = createAssistant({ storage: memoryStorage(), openStorage: memoryStorage(), post: async () => undefined });
    installAssistant(assistant);
    try {
      const s = await setup({ locale: 'es' });
      await s.show(status([item('base.business', { state: 'pending' }), item('base.team', { state: 'done' })]));
      const ask = s.wrapper.get('[data-testid="setup-review"]');
      expect(ask.text()).toBe('Pedírselo al asistente');
      await ask.trigger('click');
      expect([assistant.state.open, assistant.state.thread.setup]).toEqual([true, true]);
      await s.show(status([item('base.business', { state: 'done' })]), 2);
      expect(s.wrapper.find('[data-testid="setup-review"]').exists()).toBe(false);
    } finally {
      installAssistant(undefined);
    }
  });
});

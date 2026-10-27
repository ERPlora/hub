// «Start with a business like yours» on the Home (BASE-G131, BASE-F02; PLAN-HUB round 2026-10-21): to who administers
// the hub, while the business has nothing a template brings, up to four templates with «Use this one», «See all
// templates» (Settings › Data) and «Not now» (remembered on this device). «Use this one» loads it in one go and says
// how it went in the card — ready, not all of it (what, with «See the report»), not started (with why and «Try
// again») or cut halfway —; once seen, the card stays until «Continue» or «Not now».
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { load, template } from '../__tests__/data-fixtures';
import { EMPLOYEE, errorFrame, flush, memoryStorage, mountBase, subId } from '../__tests__/mount-base';
import BlueprintCard from './BlueprintCard.vue';

const TEMPLATES = ['restaurant.es', 'hair_salon.es', 'restaurant.en', 'hair_salon.en', 'bakery.es'].map((key) => template(key));

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

async function card(answer: () => Response = () => Response.json(load()), list = { templates: TEMPLATES, empty: true }) {
  const bodies: unknown[] = [];
  const m = await mountBase(BlueprintCard, {
    routes: ['/settings'],
    onApi: ({ init }) => {
      bodies.push(JSON.parse(String(init.body)));
      return answer();
    },
  });
  const call = await m.live();
  await m.result(call, 'base.blueprint.list', list);
  return { ...m, call, bodies };
}

const offered = (m: Awaited<ReturnType<typeof card>>) =>
  m.wrapper.findAll('[data-testid="blueprint-card-template"]').map((row) => row.attributes('data-id'));

describe('BlueprintCard', () => {
  it('offers up to four templates of the catalogue, one per kind of business, in its order, to an administrator of an empty business', async () => {
    const m = await card();
    expect(m.wrapper.get('h2').text()).toBe('Start with a business like yours');
    expect(offered(m)).toEqual(['restaurant.es', 'hair_salon.es', 'bakery.es']);
    expect(m.wrapper.get('[data-id="restaurant.es"]').text()).toContain('A restaurant.es ready to use');
  });

  it('is not there for a business that already has what a template brings, nor without templates', async () => {
    const full = await card(undefined, { templates: TEMPLATES, empty: false });
    expect(full.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
    full.wrapper.unmount();
    const none = await card(undefined, { templates: [], empty: true });
    expect(none.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
  });

  it('is not there for who does not administer the hub, which does not even ask', async () => {
    const m = await mountBase(BlueprintCard, { session: EMPLOYEE });
    await settle();
    expect(m.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
    expect(m.client.stream.subscriptions('base.blueprint.list')).toEqual([]);
  });

  it('«Not now» closes it on this device; «See all templates» opens Settings › Data', async () => {
    const m = await card();
    await m.wrapper.get('[data-testid="blueprint-card-all"]').trigger('click');
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/settings#data');
    await m.wrapper.get('[data-testid="blueprint-card-later"]').trigger('click');
    await settle();
    expect(m.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
    m.wrapper.unmount();
    const again = await card();
    expect(again.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
  });

  it('«Use this one» loads it in one go, says it is preparing, and then that the apps are ready; it stays until «Continue»', async () => {
    let release!: (response: Response) => void;
    const m = await card(() => new Promise<Response>((resolve) => (release = resolve)) as unknown as Response);
    await m.wrapper.get('[data-testid="blueprint-card-use-restaurant.es"]').trigger('click');
    await settle();
    expect(m.bodies).toEqual([{ template: 'restaurant.es' }]);
    expect(m.wrapper.get('[data-testid="blueprint-card-busy"]').text()).toBe('Preparing «Restaurant»…');
    release(Response.json(load()));
    await settle();
    // The business is no longer empty: the card stays to tell how it went.
    await m.result(m.call, 'base.blueprint.list', { templates: TEMPLATES, empty: false }, 2);
    expect(m.wrapper.get('[data-testid="blueprint-card-outcome"]').text()).toContain('Your apps and your catalogue are ready');
    await m.wrapper.get('[data-testid="blueprint-card-continue"]').trigger('click');
    await settle();
    expect(m.wrapper.find('[data-testid="blueprint-card"]').exists()).toBe(false);
  });

  it('a load that did not go in whole says what did not, with «See the report»', async () => {
    const partial = load({
      status: 'partial',
      report: { status: 'partial', dropped: [], apps: [{ id: 'table', label: 'Tables', status: 'failed', datasets: [] }] },
    });
    const m = await card(() => Response.json(partial));
    await m.wrapper.get('[data-testid="blueprint-card-use-restaurant.es"]').trigger('click');
    await settle();
    const outcome = m.wrapper.get('[data-testid="blueprint-card-outcome"]').text();
    expect(outcome).toContain('Not everything went in');
    expect(outcome).toContain('These did not go in: Tables.');
    await m.wrapper.get('[data-testid="blueprint-card-report"]').trigger('click');
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/settings#data');
  });

  it('promises to turn the template\'s apps on, never that they are on already (round 2026-10-27)', async () => {
    const m = await card(() => Response.json(load()));
    expect(m.wrapper.get('[data-testid="blueprint-card"]').text()).toContain(
      'Choose the one most like yours: we turn on its apps and load its catalogue in one go.',
    );
  });

  it('a template that could not be opened says nothing changed, why, and tries again', async () => {
    const m = await card(() => Response.json({ error: { code: 'base.blueprint_source', message: 'It is not in the catalogue.' } }, { status: 422 }));
    await m.wrapper.get('[data-testid="blueprint-card-use-hair_salon.es"]').trigger('click');
    await settle();
    const outcome = m.wrapper.get('[data-testid="blueprint-card-outcome"]').text();
    expect(outcome).toContain('That template could not be opened');
    expect(outcome).toContain('Nothing has changed in your business: It is not in the catalogue.');
    await m.wrapper.get('[data-testid="blueprint-card-again"]').trigger('click');
    await settle();
    expect(m.bodies).toEqual([{ template: 'hair_salon.es' }, { template: 'hair_salon.es' }]);
  });

  it('a load cut halfway says part may be in already, and offers no retry', async () => {
    const m = await card(() => Promise.reject(new TypeError('Failed to fetch')) as unknown as Response);
    await m.wrapper.get('[data-testid="blueprint-card-use-restaurant.es"]').trigger('click');
    await settle();
    expect(m.wrapper.get('[data-testid="blueprint-card-outcome"]').text()).toContain('Part of it may be in already.');
    expect(m.wrapper.find('[data-testid="blueprint-card-again"]').exists()).toBe(false);
  });

  it('says when the templates could not be loaded, and loads them again', async () => {
    const m = await mountBase(BlueprintCard, {});
    const call = await m.live();
    call.push(errorFrame(subId(m.client, 'base.blueprint.list'), 'internal'));
    await settle();
    expect(m.wrapper.get('[data-testid="blueprint-card"]').text()).toContain('The templates to start with could not be loaded.');
    expect(m.wrapper.find('[data-testid="blueprint-card-retry"]').exists()).toBe(true);
  });
});

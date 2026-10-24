// «Devices» of Settings › General (BASE-G63…G66; the old hub's DevicesCard): the devices someone entered this hub on,
// named by the business or by what they are, with the one in hand marked, how it asks, when it was used and who entered
// last; «Name it», «Remove this device» (a question with its consequence, the own one ends the session) and «Remove the
// devices unused for 30 days». Never the device's identifier. Settings mounts it only for who runs the hub; a failure
// is never an empty list.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { DeviceRow } from '../operations';
import DevicesCard from './DevicesCard.vue';

const access = vi.hoisted(() => ({ leaveTo: vi.fn() }));
vi.mock('../lib/access', async (original) => ({ ...(await original<typeof import('../lib/access')>()), ...access }));

const NOW = '2026-10-24T10:00:00Z';
const BAR: DeviceRow = {
  id: '0192d5c4-0000-7000-8000-000000000001',
  name: 'Bar',
  agent: 'Chrome · Android',
  mode: 'shared',
  current: true,
  in_use: true,
  session_until: '2026-10-24T22:00:00Z',
  last_entry_at: NOW,
  last_user: 'Ana López',
  created_at: '2026-09-01T09:00:00Z',
  unused: false,
};
const OLD: DeviceRow = {
  ...BAR,
  id: '0192d5c4-0000-7000-8000-000000000002',
  name: '',
  agent: 'Safari · iPad',
  mode: 'personal',
  current: false,
  in_use: false,
  session_until: null,
  last_entry_at: '2026-08-01T09:00:00Z',
  last_user: 'Bea',
  unused: true,
};

type Answer = (url: string, body: Record<string, unknown> | undefined) => Response;
const fine: Answer = (url) => {
  if (url.startsWith('/api/devices/rename')) return Response.json({ id: BAR.id });
  if (url.startsWith('/api/devices/remove')) return Response.json({ removed: 1, yours: false });
  if (url.startsWith('/api/devices/prune')) return Response.json({ removed: 1 });
  return Response.json({});
};

async function card(devices: DeviceRow[] | null = [BAR, OLD], options: Parameters<typeof mountBase>[1] = {}, answer = fine) {
  const mounted = await mountBase(DevicesCard, {
    ...options,
    onApi: ({ url, init }) => answer(url, init.body ? JSON.parse(String(init.body)) : undefined),
  });
  const call = await mounted.live();
  if (devices) await mounted.result(call, 'base.device.list', { devices, unused: devices.filter((d) => d.unused).length });
  const sent = (path: string) =>
    mounted.net.api.filter((c) => c.url.startsWith(path)).map((c) => (c.init.body ? JSON.parse(String(c.init.body)) : undefined));
  const row = (index: number) => mounted.wrapper.findAll('[data-testid="device-row"]')[index];
  const click = async (testid: string, index = 0) => {
    await mounted.wrapper.findAll(`[data-testid="${testid}"]`)[index].trigger('click');
    await flush();
  };
  return { ...mounted, call, sent, row, click };
}

beforeEach(() => access.leaveTo.mockReset());
afterEach(() => {
  document.body.innerHTML = '';
});

describe('DevicesCard — the list', () => {
  it('names each device, marks the one in hand, says how it asks and who entered last; never its identifier', async () => {
    const { wrapper, row } = await card();
    expect(row(0).text()).toContain('Bar');
    expect(row(0).text()).toContain('The one you are using');
    expect(row(0).text()).toContain('Asks for a PIN');
    expect(row(0).text()).toContain('In use right now');
    expect(row(0).text()).toContain('Its session stays open until');
    expect(row(0).text()).toContain('Last entered: Ana López');
    expect(row(1).text()).toContain('Unnamed device');
    expect(row(1).text()).toContain('Safari · iPad');
    expect(row(1).text()).toContain('Stays open');
    expect(row(1).text()).toContain('Last used');
    expect(wrapper.text()).not.toContain(BAR.id);
  });

  it('an empty list says nobody entered yet', async () => {
    const { wrapper } = await card([]);
    expect(wrapper.get('[data-testid="devices-empty"]').text()).toBe('Nobody has entered from any device yet.');
  });

  it('a list that cannot be read is never an empty list', async () => {
    const { wrapper, call, client } = await card(null);
    call.push(errorFrame(subId(client, 'base.device.list'), 'unexpected'));
    await flush();
    expect(wrapper.get('[data-testid="devices-load-error"]').text()).toContain('Could not load the devices.');
    expect(wrapper.find('[data-testid="devices-empty"]').exists()).toBe(false);
  });
});

describe('DevicesCard — name, remove, prune', () => {
  it('«Name it» opens a field under the row; «Save» sends the name', async () => {
    const { wrapper, sent, click } = await card();
    await click('device-rename', 1);
    const field = wrapper.get('[data-testid="device-name"]');
    (field.element as HTMLInputElement & { value: string }).value = 'Kitchen';
    field.element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Kitchen' } }));
    await flush();
    await click('device-name-save');
    expect(sent('/api/devices/rename')).toEqual([{ id: OLD.id, name: 'Kitchen' }]);
    expect(wrapper.find('[data-testid="device-name"]').exists()).toBe(false);
  });

  it('a name the Hub refuses (too long) keeps the field open with its sentence', async () => {
    const refuse: Answer = (url, body) =>
      url.startsWith('/api/devices/rename')
        ? Response.json({ error: { code: 'invalid_payload', message: 'That name is too long.' } }, { status: 422 })
        : fine(url, body);
    const { wrapper, click } = await card([BAR, OLD], {}, refuse);
    await click('device-rename', 1);
    await click('device-name-save');
    expect(wrapper.find('[data-testid="device-name"]').exists()).toBe(true);
    expect(wrapper.get('[data-testid="device-name-error"]').text()).toContain('That name is too long.');
  });

  it('«Remove this device» asks first, with the consequence; «Leave it» changes nothing', async () => {
    const { wrapper, sent, click } = await card();
    await click('device-remove', 1);
    const ask = wrapper.get('[data-testid="device-remove-ask"]');
    expect(ask.text()).toContain('Remove this device?');
    expect(ask.text()).toContain('Its session closes at once.');
    await click('device-remove-keep');
    expect(sent('/api/devices/remove')).toEqual([]);
    await click('device-remove', 1);
    await click('device-remove-confirm');
    expect(sent('/api/devices/remove')).toEqual([{ id: OLD.id }]);
  });

  it('removing the one in hand warns it ends the session, and then goes to the way in', async () => {
    const yours: Answer = (url, body) =>
      url.startsWith('/api/devices/remove') ? Response.json({ removed: 1, yours: true }) : fine(url, body);
    const { wrapper, click } = await card([BAR, OLD], {}, yours);
    await click('device-remove', 0);
    expect(wrapper.get('[data-testid="device-remove-ask"]').text()).toContain('It is the device you are using');
    await click('device-remove-confirm');
    expect(access.leaveTo).toHaveBeenCalledWith('/');
  });

  it('a removal the Hub refuses says so and leaves the row', async () => {
    const refuse: Answer = (url, body) =>
      url.startsWith('/api/devices/remove')
        ? Response.json({ error: { code: 'not_found', message: 'gone' } }, { status: 404 })
        : fine(url, body);
    const { wrapper, click, row } = await card([BAR, OLD], {}, refuse);
    await click('device-remove', 1);
    await click('device-remove-confirm');
    expect(wrapper.get('[data-testid="device-remove-error"]').text()).toContain('Could not remove this device.');
    expect(row(1).exists()).toBe(true);
  });

  it('«Remove the device unused for 30 days» asks how many and removes them', async () => {
    const { wrapper, sent, click } = await card();
    expect(wrapper.get('[data-testid="devices-prune"]').text()).toBe('Remove the device unused for 30 days');
    await click('devices-prune');
    expect(wrapper.get('[data-testid="devices-prune-ask"]').text()).toContain('Remove the device nobody has used for 30 days?');
    await click('devices-prune-confirm');
    expect(sent('/api/devices/prune')).toEqual([{}]);
  });

  it('nothing unused, no prune button', async () => {
    const { wrapper } = await card([BAR]);
    expect(wrapper.find('[data-testid="devices-prune"]').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const { row } = await card([BAR, OLD], { locale: 'es' });
    expect(row(0).text()).toContain('El que estás usando');
    expect(row(1).text()).toContain('Dispositivo sin nombre');
  });
});

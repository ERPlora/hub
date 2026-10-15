// The gallery (WORKBOOK FLOW-F04, F05, F08): ready-made automations by sector; a card opens (one at a
// time) to say what it will do, what you decide and what it will ask permission to do; «Use this one»
// creates it paused and ungranted; a card the business already has says how it is and offers «See it»;
// a card whose apps are missing is hidden and named below; a link can open one.
import { describe, expect, it } from 'vitest';

import type { CatalogOut, FlowOut } from '../operations';
import { click, mountFlow, settle } from '../__tests__/mount-flow';
import FlowGallery from './FlowGallery.vue';

const ALL_EVENTS = [
  'customer.customer.created',
  'sale.sale.completed',
  'staff.member.created',
  'cash_register.session.closed',
  'verifactu.record.rejected',
  'appointment.appointment.marked_no_show',
  'reservation.reservation.created',
];
const catalog = (events = ALL_EVENTS, actions = ['task.task.create', 'customer.note.add']): CatalogOut => ({
  events: events.map((name) => ({ name, app: name.split('.')[0], app_name: name.split('.')[0] })),
  actions: actions.map((name) => ({ name, kind: 'command', app: name.split('.')[0], app_name: name.split('.')[0], description: '', fields: [], outputs: [] })),
});
const CREATED = { id: 'f9', name: 'Welcome a new customer', enabled: false } as FlowOut;

async function setup(props: Record<string, unknown> = {}, answer: [number, unknown] = [201, CREATED]) {
  return mountFlow(FlowGallery, { props: { catalog: catalog(), flows: [], openCard: null, ...props }, answers: { '/api/flow/flows': answer } });
}

describe('Gallery', () => {
  it('shows the cards by sector, each with its name and its line', async () => {
    const m = await setup();
    expect(m.find('flow-gallery-sector-any').text()).toContain('Any business');
    expect(m.find('flow-gallery-sector-beauty').text()).toContain('Hair and beauty');
    expect(m.find('flow-gallery-sector-food').text()).toContain('Bars and restaurants');
    expect(m.wrapper.findAll('[data-testid^="flow-card-open-"]')).toHaveLength(10);
    expect(m.find('flow-card-open-welcome').text()).toContain('Welcome a new customer');
    expect(m.find('flow-card-open-welcome').text()).toContain('A day after a customer card is created');
  });

  it('a card opens, one at a time, to say what it does, what you decide and what it asks', async () => {
    const m = await setup();
    await click(m.find('flow-card-open-welcome').element);
    const panel = m.find('flow-card-panel-welcome');
    expect(panel.text()).toContain('When a customer card is created, it waits one day');
    expect(panel.text()).toContain('How long to wait');
    expect(panel.text()).toContain('Create a task');
    expect(panel.text()).toContain('To leave the task on the list.');
    await click(m.find('flow-card-open-noShow').element);
    expect(m.find('flow-card-panel-welcome').exists()).toBe(false);
    expect(m.find('flow-card-panel-noShow').text()).toContain('There is nothing to fill in. It is ready as it is.');
  });

  it('«Use this one» creates it paused and ungranted, and hands it over', async () => {
    const m = await setup();
    await click(m.find('flow-card-open-welcome').element);
    await click(m.find('flow-card-use-welcome').element);
    await settle();
    const [call] = m.sent();
    expect(call.path).toBe('/api/flow/flows');
    expect(call.body).toMatchObject({ name: 'Welcome a new customer', trigger: { kind: 'event', event: 'customer.customer.created' } });
    // Born paused: the switch is not even sent.
    expect(call.body).not.toHaveProperty('enabled');
    expect(m.wrapper.emitted('created')).toEqual([[CREATED]]);
  });

  it('a card the business already has says how it is and offers «See it»; another on the same event warns', async () => {
    const mine = { id: 'f1', name: 'Mine', enabled: true, trigger: { kind: 'event', event: 'customer.customer.created' }, steps: [{ id: 's2', kind: 'command', operation: 'task.task.create', params: {} }], grants: [], missing_grants: ['task.task.create'] } as unknown as FlowOut;
    const m = await setup({ flows: [mine] });
    expect(m.find('flow-card-open-welcome').text()).toContain('Unfinished');
    await click(m.find('flow-card-open-welcome').element);
    expect(m.find('flow-card-panel-welcome').text()).toContain('Careful: «Mine» already starts with the same thing.');
    await click(m.find('flow-card-see-welcome').element);
    expect(m.wrapper.emitted('openFlow')).toEqual([[mine]]);
  });

  it('hides the cards whose apps are not here and names them', async () => {
    const m = await setup({ catalog: catalog(ALL_EVENTS, ['customer.note.add']) });
    expect(m.wrapper.findAll('[data-testid^="flow-card-open-"]').map((el) => el.attributes('data-testid'))).toEqual(['flow-card-open-bigSaleNote']);
    expect(m.find('flow-gallery-hidden').text()).toBe('Some automations are hidden: they need Tasks.');
  });

  it('a link opens its card; the guide button asks for the guide', async () => {
    const m = await setup({ openCard: 'bigParty' });
    expect(m.find('flow-card-panel-bigParty').exists()).toBe(true);
    await click(m.find('flow-gallery-guide').element);
    expect(m.wrapper.emitted('guide')).toHaveLength(1);
  });

  it('a refusal is said inside the card and nothing is created', async () => {
    const m = await setup({}, [422, { error: { code: 'invalid_payload', message: 'That does not happen in this business.' } }]);
    await click(m.find('flow-card-open-welcome').element);
    await click(m.find('flow-card-use-welcome').element);
    await settle();
    expect(m.find('flow-card-error-welcome').text()).toContain('That does not happen in this business.');
    expect(m.wrapper.emitted('created')).toBeUndefined();
  });
});

// The foot of a kitchen card: the main step across it («Ready» while it cooks with dishes to do, «Served» once ready)
// and, at its right, «⋮», which opens an Ionic popover with the other steps the card offers today: «Mark rush» /
// «Remove rush» and «Recall», each with its icon and its words, on the same states and permissions as before. With no
// other step there is no «⋮», and with no step at all there is no foot.
import { describe, expect, it } from 'vitest';

import { item, ticket } from '../__tests__/kitchen';
import { click, flush, mountKitchen, PopoverStub, said } from '../__tests__/mount-kitchen';
import type { TicketOut } from '../operations/tickets';
import KdsTicketActions from './KdsTicketActions.vue';

async function setup(t: TicketOut, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicketActions, {
    props: { ticket: t, canChange: true, canServe: true, ...props },
    stubs: { IonPopover: PopoverStub },
    locale,
  });
  const id = t.id;
  const has = (step: string) => m.find(`kitchen-card-${id}-${step}`).exists();
  const open = () => click(m.find(`kitchen-card-${id}-more`).element);
  return { ...m, has, open, emitted: () => m.wrapper.emitted() };
}

const cooking = (fields: Partial<TicketOut> = {}) => ticket('t1', { status: 'preparing', items: [item('i1'), item('i2', { status: 'ready' })], ...fields });

describe('KdsTicketActions', () => {
  it('a ticket that cooks has «Ready» across the foot and «⋮» with «Mark rush» and «Recall»', async () => {
    const s = await setup(cooking());
    const ready = s.find('kitchen-card-t1-bump');
    expect(ready.element.tagName.toLowerCase()).toBe('ion-button');
    expect(ready.text()).toBe('Ready');
    const more = s.find('kitchen-card-t1-more');
    expect(more.element.tagName.toLowerCase()).toBe('ion-button');
    expect(more.attributes('aria-label')).toBe('More actions');
    expect(more.attributes('aria-haspopup')).toBe('menu');
    expect(s.has('rush')).toBe(false);
    await s.open();
    expect(s.find('kitchen-card-t1-menu').element.tagName.toLowerCase()).toBe('ion-list');
    const rush = s.find('kitchen-card-t1-rush');
    expect(rush.element.tagName.toLowerCase()).toBe('ion-item');
    expect(said(rush.element)).toBe('Mark rush');
    expect(rush.find('ion-icon').exists()).toBe(true);
    expect(said(s.find('kitchen-card-t1-recall').element)).toBe('Recall');
  });

  it('«Ready» marks every dish on screen; the menu sends rush and recall, and closes', async () => {
    const s = await setup(cooking());
    await click(s.find('kitchen-card-t1-bump').element);
    await s.open();
    await click(s.find('kitchen-card-t1-rush').element);
    expect(s.has('menu')).toBe(false);
    await s.open();
    await click(s.find('kitchen-card-t1-recall').element);
    expect(s.emitted().bump).toEqual([[]]);
    expect(s.emitted().rush).toEqual([[true]]);
    expect(s.emitted().recall).toEqual([[]]);
  });

  it('closes when Ionic dismisses the popover', async () => {
    const s = await setup(cooking());
    await s.open();
    expect(s.has('menu')).toBe(true);
    s.wrapper.findComponent(PopoverStub).vm.$emit('didDismiss');
    await flush();
    expect(s.has('menu')).toBe(false);
  });

  it('a rush ticket offers «Remove rush»; a VIP one does not offer rush, and with nothing else there is no «⋮»', async () => {
    const rush = await setup(cooking({ priority: 'rush' }));
    await rush.open();
    expect(said(rush.find('kitchen-card-t1-rush').element)).toBe('Remove rush');
    await click(rush.find('kitchen-card-t1-rush').element);
    expect(rush.emitted().rush).toEqual([[false]]);

    const vip = await setup(cooking({ priority: 'vip' }));
    await vip.open();
    expect([vip.has('rush'), vip.has('recall')]).toEqual([false, true]);

    const alone = await setup(ticket('t1', { priority: 'vip', items: [item('i1')] }));
    expect([alone.has('bump'), alone.has('more')]).toEqual([true, false]);
  });

  it('a ticket with no dish done offers no «Recall»', async () => {
    const s = await setup(ticket('t1', { items: [item('i1')] }));
    await s.open();
    expect([s.has('rush'), s.has('recall')]).toEqual([true, false]);
  });

  it('a ready ticket has «Served» across the foot and «Recall» in «⋮»', async () => {
    const s = await setup(ticket('t1', { status: 'ready', items: [item('i1', { status: 'ready' })] }));
    expect(s.has('bump')).toBe(false);
    expect(s.find('kitchen-card-t1-served').text()).toBe('Served');
    await click(s.find('kitchen-card-t1-served').element);
    expect(s.emitted().serve).toHaveLength(1);
    await s.open();
    expect([s.has('rush'), s.has('recall')]).toEqual([false, true]);
  });

  it('keeps each step to its permission: «Served» to who may hand over, the rest to who may change', async () => {
    const ready = ticket('t1', { status: 'ready', items: [item('i1', { status: 'ready' })] });
    const cook = await setup(ready, { canServe: false });
    expect([cook.has('served'), cook.has('more')]).toEqual([false, true]);
    const waiter = await setup(ready, { canChange: false });
    expect([waiter.has('served'), waiter.has('more')]).toEqual([true, false]);
    const viewer = await setup(cooking(), { canChange: false, canServe: false });
    expect(viewer.has('foot')).toBe(false);
  });

  it('a ticket served or cancelled has no foot', async () => {
    expect((await setup(ticket('t1', { status: 'served' }))).has('foot')).toBe(false);
    expect((await setup(ticket('t1', { status: 'cancelled' }))).has('foot')).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup(cooking(), {}, 'es');
    expect(s.find('kitchen-card-t1-bump').text()).toBe('Listo');
    expect(s.find('kitchen-card-t1-more').attributes('aria-label')).toBe('Más acciones');
    await s.open();
    expect([said(s.find('kitchen-card-t1-rush').element), said(s.find('kitchen-card-t1-recall').element)]).toEqual(['Marcar urgente', 'Recuperar']);
    const ready = await setup(ticket('t2', { status: 'ready', items: [item('i1', { status: 'ready' })] }), {}, 'es');
    expect(ready.find('kitchen-card-t2-served').text()).toBe('Servida');
  });
});

// The head of a kitchen card: at the left, the type of order as an icon in its box, the label (or the type) and
// «Waiter: …»; at the right, the clock, the wait in words with its icon («On time», «Warning», «Late», from the
// semaphore, never colour alone) and «#0012». Under it, the ticket's status, its Rush/VIP and its round as pills.
// A tap on it marks every dish on screen, when the card lets it.
import { describe, expect, it } from 'vitest';

import { NOW, SETTINGS, ticket } from '../__tests__/kitchen';
import { click, mountKitchen } from '../__tests__/mount-kitchen';
import type { TicketOut } from '../operations';
import KdsTicketHeader from './KdsTicketHeader.vue';

async function setup(t: TicketOut, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(KdsTicketHeader, {
    props: { ticket: t, elapsed: 65_000, settings: SETTINGS, sem: 'ok', tappable: true, ...props },
    locale,
  });
  return { ...m, emitted: () => m.wrapper.emitted() };
}

describe('KdsTicketHeader', () => {
  it('puts the type, the label and the waiter at the left, and the clock, the wait and the number at the right', async () => {
    const s = await setup(ticket('t1', { received_at: NOW.toISOString() }));
    const head = s.find('kitchen-card-t1-head');
    expect(head.element.tagName.toLowerCase()).toBe('ion-item');
    expect(head.find('ion-thumbnail').attributes('slot')).toBe('start');
    expect(head.find('ion-note').attributes('slot')).toBe('end');
    expect(s.find('kitchen-card-t1-label').text()).toBe('Table 4');
    expect(s.find('kitchen-card-t1-waiter').text()).toBe('Waiter: luis');
    expect(s.find('kitchen-card-t1-timer').text()).toBe('1:05');
    expect(s.find('kitchen-card-t1-wait').text()).toBe('On time');
    expect(s.find('kitchen-card-t1-number').text()).toBe('#0012');
  });

  it('says the wait in words and with an icon from the semaphore, and nothing when the colours are off', async () => {
    const words = async (sem: string) => (await setup(ticket('t1'), { sem })).find('kitchen-card-t1-wait');
    expect((await words('warning')).text()).toBe('Warning');
    expect((await words('critical')).text()).toBe('Late');
    expect((await words('critical')).find('ion-icon').exists()).toBe(true);
    expect((await words('off')).exists()).toBe(false);
    const noClock = await setup(ticket('t1'), { sem: 'warning', settings: { ...SETTINGS, show_timer: false } });
    expect(noClock.find('kitchen-card-t1-timer').exists()).toBe(false);
    expect(noClock.find('kitchen-card-t1-wait').text()).toBe('Warning');
  });

  it('says the status of every ticket, its Rush or VIP and its round as pills', async () => {
    const pill = async (fields: Partial<TicketOut>, testid: string) => (await setup(ticket('t1', fields))).find(`kitchen-card-t1-${testid}`);
    expect((await pill({ status: 'pending' }, 'status')).text()).toBe('To prepare');
    expect((await pill({ status: 'preparing' }, 'status')).attributes('data-tone')).toBe('info');
    expect((await pill({ status: 'ready' }, 'status')).text()).toBe('Ready');
    expect((await pill({ status: 'ready' }, 'status')).attributes('data-tone')).toBe('success');
    expect((await pill({ priority: 'rush' }, 'priority')).text()).toBe('Rush');
    expect((await pill({ priority: 'rush' }, 'priority')).attributes('data-tone')).toBe('danger');
    expect((await pill({ priority: 'vip' }, 'priority')).text()).toBe('VIP');
    expect((await pill({ priority: 'normal' }, 'priority')).exists()).toBe(false);
    expect((await pill({ round_no: 2 }, 'round')).text()).toBe('Round 2');
    expect((await pill({ round_no: 1 }, 'round')).exists()).toBe(false);
  });

  it('says the type when there is no label, and names the type icon when a label hides it', async () => {
    const bare = await setup(ticket('t1', { label: '', order_type: 'takeaway' }));
    expect(bare.find('kitchen-card-t1-label').text()).toBe('Takeaway');
    expect(bare.find('kitchen-card-t1-head').find('ion-thumbnail ion-icon').attributes('aria-hidden')).toBe('true');
    const named = await setup(ticket('t2', { label: 'Juan', order_type: 'delivery' }));
    expect(named.find('kitchen-card-t2-head').find('ion-thumbnail ion-icon').attributes('aria-label')).toBe('Delivery');
  });

  it('a tap on it marks every dish on screen when the card lets it, and is a button only then', async () => {
    const s = await setup(ticket('t1'));
    expect(s.find('kitchen-card-t1-head').attributes('title')).toBe('Mark every dish on screen ready');
    await click(s.find('kitchen-card-t1-head').element);
    expect(s.emitted().bumpAll).toHaveLength(1);

    const still = await setup(ticket('t2'), { tappable: false });
    await click(still.find('kitchen-card-t2-head').element);
    expect(still.emitted().bumpAll).toBeUndefined();
    expect(still.find('kitchen-card-t2-head').attributes('aria-disabled')).toBe('true');
    expect((still.find('kitchen-card-t2-head').element as HTMLElement & { button?: boolean }).button).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup(ticket('t1', { priority: 'rush', round_no: 3, status: 'preparing' }), { sem: 'critical' }, 'es');
    expect(s.find('kitchen-card-t1-waiter').text()).toBe('Camarero: luis');
    expect(s.find('kitchen-card-t1-wait').text()).toBe('Retraso');
    expect([s.find('kitchen-card-t1-status').text(), s.find('kitchen-card-t1-priority').text(), s.find('kitchen-card-t1-round').text()]).toEqual([
      'En preparación',
      'Urgente',
      'Ronda 3',
    ]);
    expect((await setup(ticket('t2'), { sem: 'ok' }, 'es')).find('kitchen-card-t2-wait').text()).toBe('En tiempo');
    expect((await setup(ticket('t3'), { sem: 'warning' }, 'es')).find('kitchen-card-t3-wait').text()).toBe('Aviso');
  });
});

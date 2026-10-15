// SERVICE-F19 «Ver los movimientos de un bono»: the sheet «Voucher movements» of a package follows
// `service.movement.list` live, the most recent first: each session Delivered (with its service, or «No
// service on the line»), each Courtesy and Correction (with what moved, who and why), the date, the
// customer and the sale.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { MovementOut } from '../operations';
import { mountService, page, settle } from '../__tests__/mount-service';
import { PACKAGE } from '../__tests__/package';
import MovementsSheet from './MovementsSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.movement.list';
const movement = (id: string, over: Partial<MovementOut> = {}): MovementOut => ({
  id,
  kind: 'consumed',
  at: '2026-10-10T10:00:00Z',
  grant_id: 'g1',
  customer_id: 'cust-1',
  customer_name: 'Lucía Pérez',
  service_id: 's1',
  service_name: 'Cut',
  sale_id: null,
  appointment_id: null,
  note: '',
  actor: 'ana',
  uses_delta: -1,
  days_delta: 0,
  reason: '',
  ...over,
});
const ROWS = [
  movement('m3', { kind: 'corrected', uses_delta: -1, service_id: null, service_name: null, actor: 'boss', reason: 'typo' }),
  movement('m2', { kind: 'adjusted', uses_delta: 2, days_delta: 30, service_id: null, service_name: null, actor: 'boss', reason: 'closed' }),
  movement('m1', { sale_id: 'sale-9' }),
  movement('m0', { service_id: null, service_name: null, customer_name: null, customer_id: 'cust-2' }),
];

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountService(MovementsSheet, { props: { open: true, pkg: PACKAGE }, locale });
  await settle();
  await m.live();
  const text = (id: string) => m.inDoc(`service-movements-row-${id}`)?.textContent ?? '';
  return { ...m, text, show: (data: unknown) => m.result(OP, data) };
}

describe('MovementsSheet', () => {
  it('follows the movements of the package, 20 first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ package_id: 'p1', limit: 20, offset: 0 }]);
    expect(s.inDoc('service-movements-title')?.textContent).toContain('Voucher movements — Bono 5 cortes');
  });

  it('paints each session and each adjustment with its label, what moved, who and why', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const labels = s.wrapper.findAllComponents(StatusPill).map((p) => p.props('label'));
    expect(labels).toEqual(['Correction', 'Courtesy', 'Delivered', 'Delivered']);
    expect(s.text('m3')).toContain('−1 session(s) · +0 day(s)');
    expect(s.text('m3')).toContain('Corrected by boss');
    expect(s.text('m3')).toContain('typo');
    expect(s.text('m2')).toContain('+2 session(s) · +30 day(s)');
    expect(s.text('m2')).toContain('Given by boss');
    expect(s.text('m1')).toContain('Cut');
    expect(s.text('m1')).toContain('Customer: Lucía Pérez');
    expect(s.text('m1')).toContain('Sale: sale-9');
    expect(s.text('m1')).toContain('Oct 10, 2026');
    expect(s.text('m0')).toContain('No service on the line');
    expect(s.text('m0')).toContain('Customer: cust-2');
  });

  it('paints every step of a session of the till: held, released, expired and given back with who and why', async () => {
    const s = await setup();
    await s.show(
      page([
        movement('r4', { kind: 'returned', uses_delta: 0, sale_id: 'sale-7', actor: 'boss', reason: 'did not come' }),
        movement('r3', { kind: 'expired', uses_delta: 0, actor: 'system' }),
        movement('r2', { kind: 'released', uses_delta: 0, actor: 'ana' }),
        movement('r1', { kind: 'held', uses_delta: -1 }),
      ]),
    );
    const labels = s.wrapper.findAllComponents(StatusPill).map((p) => p.props('label'));
    expect(labels).toEqual(['Given back', 'Expired', 'Released', 'Held']);
    expect(s.text('r4')).toContain('Cut');
    expect(s.text('r4')).toContain('Sale: sale-7');
    expect(s.text('r4')).toContain('Given back by boss — did not come');
    expect(s.text('r2')).toContain('Released by ana');
    expect(s.text('r3')).not.toContain('by');
    expect(s.text('r1')).toContain('Cut');
  });

  it('says the steps of a session in Spanish (WORKBOOK «Pantallas»)', async () => {
    const s = await setup('es');
    await s.show(page([movement('r1', { kind: 'held' }), movement('r2', { kind: 'released' }), movement('r3', { kind: 'expired' }), movement('r4', { kind: 'returned' })]));
    const labels = s.wrapper.findAllComponents(StatusPill).map((p) => p.props('label'));
    expect(labels).toEqual(['Reservada', 'Liberada', 'Caducada', 'Devuelta']);
  });

  it('says when the voucher was never used', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.inDoc('service-movements-empty')?.textContent).toContain('This voucher has not been used yet.');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.show(page(ROWS));
    expect(s.wrapper.findAllComponents(StatusPill).map((p) => p.props('label'))).toEqual([
      'Corrección',
      'Cortesía',
      'Entregada',
      'Entregada',
    ]);
  });
});

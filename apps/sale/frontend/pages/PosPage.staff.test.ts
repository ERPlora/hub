// Sales & POS → Sell: the professional under a line (SALE-F16, SALE-F26). A check the till did not build here
// (an appointment's, charged from the agenda) brings lines with their professional; the line names her as
// Staff names her, not as «the assigned professional».
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { mountSale, settle } from '../__tests__/mount-sale';
import { line, memoryStorage, order, settings } from '../components/pos/__tests__/fixtures';
import PosPage from './PosPage.vue';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => vi.unstubAllGlobals());

const HAIRCUT = line({ id: 'l7', product_id: null, is_service: true, service_id: 'sv1', name: 'Haircut', staff_id: 's9' });
const APPOINTMENT_CHECK = order({ id: 'o7', label: 'Lucía · APT-20261121-0001', appointment_id: 'a1', lines: [HAIRCUT] });
const LUCIA = { id: 's9', first_name: 'Lucia', last_name: 'Garcia', full_name: 'Lucia Garcia' };

async function openAppointmentCheck(staffAnswer: [number, unknown], locale: 'en' | 'es' = 'en') {
  const m = await mountSale(PosPage, { path: '/sale/pos?order=o7', locale });
  await m.live();
  m.answerBy({
    '/api/sale/orders/detail': [200, APPOINTMENT_CHECK],
    '/api/customer/orders/customer': [200, { order_id: 'o7', customer_id: null }],
    '/api/staff/members/detail': staffAnswer,
  });
  await m.result('sale.pos_settings.get', settings());
  await settle();
  await m.reopen();
  await m.result('sale.order.get', APPOINTMENT_CHECK);
  await settle();
  const staffReads = () => m.sent().filter((call) => call.path === '/api/staff/members/detail');
  return { ...m, staffReads };
}

describe('PosPage: the professional of a line the till did not pick', () => {
  it('names the professional of the appointment’s line as Staff names her', async () => {
    const s = await openAppointmentCheck([200, LUCIA]);
    expect(s.find('pos-line-l7-staff').text()).toBe('Lucia Garcia');
    expect(s.staffReads().map((call) => call.query)).toEqual([{ id: 's9' }]);
  });

  it('when Staff cannot say who she is, the line still says it has a professional, with no error on screen', async () => {
    const s = await openAppointmentCheck([403, { error: { code: 'permission_denied', message: 'No.' } }], 'es');
    expect(s.find('pos-line-l7-staff').text()).toBe('el profesional asignado');
    expect(toastError).not.toHaveBeenCalled();
  });
});

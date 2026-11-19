import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MANAGER, mountSale, settle } from '../__tests__/mount-sale';
import LineNoteSheet from '../components/pos/LineNoteSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import { line, memoryStorage, order, product, settings } from '../components/pos/__tests__/fixtures';
import PosPage from './PosPage.vue';

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));

const WITH_KITCHEN = { ...MANAGER, apps: [{ label: 'kitchen', state: 'on' as const }] };
const ALLERGIC = line({ id: 'l1', notes: 'No salt', allergy: ['gluten'] });
const CHECK = order({ id: 'o1', lines: [ALLERGIC] });

async function noteSheetOf(session: typeof MANAGER) {
  const m = await mountSale(PosPage, { session });
  await m.live();
  await m.result('sale.pos_settings.get', settings());
  m.net.onApi(() => Response.json(CHECK));
  m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
  await settle();
  await m.reopen();
  m.wrapper.findComponent(PosCart).vm.$emit('note', ALLERGIC);
  await settle();
  const sheet = m.wrapper.findComponent(LineNoteSheet);
  const lineWrites = () =>
    m
      .sent()
      .filter((call) => call.path !== '/api/sale/orders')
      .map((call) => [call.path, call.body]);
  return { sheet, lineWrites };
}

describe('PosPage: the note sheet and the customer allergy', () => {
  it('with Kitchen on, opens with the allergy the line already has and saves the note and the allergy', async () => {
    const s = await noteSheetOf(WITH_KITCHEN);
    expect(s.sheet.props()).toMatchObject({ open: true, note: 'No salt', allergyEnabled: true, allergy: ['gluten'] });
    s.sheet.vm.$emit('save', { note: 'No salt', allergy: ['gluten', 'milk'] });
    await settle();
    expect(s.lineWrites()).toEqual([
      ['/api/sale/orders/update_line', { order_id: 'o1', line_id: 'l1', notes: 'No salt' }],
      ['/api/sale/orders/set_line_allergy', { order_id: 'o1', line_id: 'l1', allergy: ['gluten', 'milk'] }],
    ]);
  });

  it('without Kitchen, the sheet has no allergy block and saving writes only the note', async () => {
    const s = await noteSheetOf(MANAGER);
    expect(s.sheet.props('allergyEnabled')).toBe(false);
    s.sheet.vm.$emit('save', { note: 'Rare' });
    await settle();
    expect(s.lineWrites()).toEqual([['/api/sale/orders/update_line', { order_id: 'o1', line_id: 'l1', notes: 'Rare' }]]);
  });
});

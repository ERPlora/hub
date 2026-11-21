import { describe, expect, it } from 'vitest';
import { shallowRef } from 'vue';

import { mountComposable, settle } from '../../__tests__/mount-sale';
import { line } from '../../components/pos/__tests__/fixtures';
import type { OrderLineOut } from '../../operations';
import { useStaffNames } from './useStaffNames';

const MEMBERS: Record<string, string> = { s1: 'Marta Ruiz', s9: 'Lucia Garcia' };

async function setup(status = 200) {
  const lines = shallowRef<OrderLineOut[]>([]);
  let names!: ReturnType<typeof useStaffNames>;
  const m = await mountComposable(() => {
    names = useStaffNames(() => lines.value);
  });
  m.net.onApi(({ url }) => {
    const id = new URL(url, 'http://a.localhost').searchParams.get('id') ?? '';
    if (status !== 200) return Response.json({ error: { code: 'staff_unavailable', message: 'No.' } }, { status });
    return Response.json({ id, full_name: MEMBERS[id] });
  });
  async function show(next: OrderLineOut[]): Promise<void> {
    lines.value = next;
    await settle();
  }
  const asked = () => m.sent().map((call) => [call.path, call.query]);
  return { show, asked, names: () => names };
}

describe('useStaffNames', () => {
  it('asks Staff once for each professional it does not know, and names her', async () => {
    const s = await setup();
    await s.show([line({ id: 'a', staff_id: 's9' }), line({ id: 'b', staff_id: 's9' }), line({ id: 'c', staff_id: 's1' })]);
    await s.show([line({ id: 'a', staff_id: 's9' }), line({ id: 'c', staff_id: 's1' })]);
    expect(s.names().names.value).toEqual({ s9: 'Lucia Garcia', s1: 'Marta Ruiz' });
    expect(s.asked()).toEqual([
      ['/api/staff/members/detail', { id: 's9' }],
      ['/api/staff/members/detail', { id: 's1' }],
    ]);
  });

  it('names the professionals of a check already on screen when the till mounts', async () => {
    let names!: ReturnType<typeof useStaffNames>;
    const lines = [line({ staff_id: 's9' })];
    await mountComposable(
      () => {
        names = useStaffNames(() => lines);
      },
      { answer: { status: 200, body: { id: 's9', full_name: 'Lucia Garcia' } } },
    );
    await settle();
    expect(names.names.value).toEqual({ s9: 'Lucia Garcia' });
  });

  it('a professional picked on this screen is named as picked, without asking', async () => {
    const s = await setup();
    s.names().remember('s1', 'Marta');
    await s.show([line({ staff_id: 's1' }), line({ id: 'b', staff_id: null })]);
    expect(s.names().names.value).toEqual({ s1: 'Marta' });
    expect(s.asked()).toEqual([]);
  });

  it('a professional Staff cannot name stays unnamed and is not asked again on the next change of the check', async () => {
    const s = await setup(409);
    await s.show([line({ staff_id: 's9' })]);
    await s.show([line({ staff_id: 's9', quantity: '2.000' })]);
    expect(s.names().names.value).toEqual({});
    expect(s.asked()).toEqual([['/api/staff/members/detail', { id: 's9' }]]);
  });
});

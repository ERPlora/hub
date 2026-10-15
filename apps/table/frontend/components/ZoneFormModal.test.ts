// A zone's dialog (WORKBOOK «Zonas», «Plano de sala»; TABLE-F01, F06): in Zones, Name, Description,
// Colour (Blue, Cyan, Purple, Green, Amber, Red, Grey) and Order, «Add zone»; editing adds «Active» and
// «Save changes». From the plan's pencil, «Edit zone» with Name and Description, «Delete zone» and «Save».
// A zone with tables cannot be deleted: «Delete zone» is off and says why.
import { describe, expect, it, vi } from 'vitest';

import { click, ionChecked, ionValue, mountTable, settle } from '../__tests__/mount-table';
import { zoneRow } from '../__tests__/tables';
import type { ZoneOut } from '../operations';
import ZoneFormModal from './ZoneFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean };

async function form(zone: ZoneOut | null, more: Record<string, unknown> = {}, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(ZoneFormModal, { props: { open: false, zone, ...more }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`table-zone-form-${name}`) as Control;
  return { ...m, field, closed: () => m.wrapper.props('open') === false };
}

describe('ZoneFormModal', () => {
  it('a new zone asks Name, Description, Colour and Order, and comes back as created', async () => {
    const created = zoneRow({ id: 'z9', name: 'Terrace' });
    const f = await form(null, {}, { '/api/table/zones': [201, created] });
    expect(f.inDoc('table-zone-form')?.getAttribute('aria-label')).toBe('New zone');
    expect(f.field('submit').disabled).toBe(true);
    await ionValue(f.field('name'), ' Terrace ', 'ionInput');
    await ionValue(f.field('color'), 'success');
    await ionValue(f.field('sort_order'), '3', 'ionInput');
    expect(f.field('active')).toBeNull();
    await click(f.field('submit'));
    expect(f.sent()).toEqual([{ method: 'POST', path: '/api/table/zones', query: {}, body: { name: 'Terrace', description: '', color: 'success', sort_order: 3 } }]);
    expect(f.wrapper.emitted('saved')?.[0]?.[0]).toEqual(created);
    expect(f.closed()).toBe(true);
  });

  it('editing sends only what changed, «Active» included', async () => {
    const f = await form(zoneRow({ name: 'Bar', color: 'warning' }), {}, { '/api/table/zones/update': [200, zoneRow()] });
    expect(f.inDoc('table-zone-form')?.getAttribute('aria-label')).toBe('Edit zone');
    expect(f.field('submit').textContent?.trim()).toBe('Save changes');
    await ionChecked(f.field('active'), false);
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.body)).toEqual([{ id: 'z1', is_active: false }]);
  });

  it('from the plan: Name and Description, «Delete zone» and «Save»', async () => {
    const f = await form(zoneRow({ name: 'Bar' }), { variant: 'plan', canDelete: true }, { '/api/table/zones/delete': [200, { id: 'z1' }] });
    expect(f.field('color')).toBeNull();
    expect(f.field('sort_order')).toBeNull();
    expect(f.field('submit').textContent?.trim()).toBe('Save');
    await click(f.field('delete'));
    await click(f.inDoc('table-zone-form-delete-confirm-submit'));
    expect(f.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/zones/delete', { id: 'z1' }]]);
    expect(f.closed()).toBe(true);
  });

  it('a zone with tables cannot be deleted, and says why', async () => {
    const f = await form(zoneRow({ table_count: 3 }), { variant: 'plan', canDelete: true });
    await click(f.field('delete'));
    expect(f.inDoc('table-zone-form-delete-confirm')?.textContent).toContain(
      '3 tables in this zone. A zone with tables cannot be deleted: move or delete its tables first.',
    );
    expect((f.inDoc('table-zone-form-delete-confirm-submit') as Control).disabled).toBe(true);
  });

  it('speaks Spanish: the colours of the old panel', async () => {
    const f = await form(null, {}, {}, 'es');
    const options = [...(f.field('color').querySelectorAll('ion-select-option') ?? [])].map((o) => o.textContent?.trim());
    expect(options).toEqual(['Azul', 'Cian', 'Morado', 'Verde', 'Ámbar', 'Rojo', 'Gris']);
  });
});

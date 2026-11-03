// «Delete zone?» (WORKBOOK «Zonas»; TABLE-F06): «N tables in this zone. A zone with tables cannot be
// deleted: move or delete its tables first.», always said; with tables, «Delete zone» is off. Deleting
// tells the page (`deleted`); a refusal stays in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { click, mountTable, settle } from '../__tests__/mount-table';
import { zoneRow } from '../__tests__/tables';
import type { ZoneOut } from '../operations';
import ZoneDeleteDialog from './ZoneDeleteDialog.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

async function dialog(zone: ZoneOut, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(ZoneDeleteDialog, { props: { open: true, zone, testid: 'zones-delete' }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const submit = () => m.inDoc('zones-delete-submit') as HTMLElement & { disabled?: boolean };
  return { ...m, submit, closed: () => m.wrapper.props('open') === false };
}

describe('ZoneDeleteDialog', () => {
  it('deletes an empty zone and tells the page', async () => {
    const d = await dialog(zoneRow(), { '/api/table/zones/delete': [200, { id: 'z1' }] });
    expect(d.inDoc('zones-delete')?.getAttribute('aria-label')).toBe('Delete zone?');
    expect(d.inDoc('zones-delete')?.textContent).toContain('0 tables in this zone.');
    await click(d.submit());
    expect(d.sent().map((call) => [call.path, call.body])).toEqual([['/api/table/zones/delete', { id: 'z1' }]]);
    expect(d.wrapper.emitted('deleted')).toHaveLength(1);
    expect(d.closed()).toBe(true);
  });

  it('a zone with tables cannot be deleted', async () => {
    const d = await dialog(zoneRow({ table_count: 2 }), {}, 'es');
    expect(d.inDoc('zones-delete')?.textContent).toContain(
      '2 mesas en esta zona. Una zona con mesas no se puede borrar: mueve o borra antes sus mesas.',
    );
    expect(d.submit().disabled).toBe(true);
  });

  it.each([
    ['en', '1 table in this zone. A zone with tables cannot be deleted: move or delete it first.'],
    ['es', '1 mesa en esta zona. Una zona con mesas no se puede borrar: muévela o bórrala antes.'],
  ] as const)('a zone with one table says it in the singular (%s, hub#462)', async (locale, impact) => {
    const d = await dialog(zoneRow({ table_count: 1 }), {}, locale);
    expect(d.inDoc('zones-delete')?.textContent).toContain(impact);
    expect(d.submit().disabled).toBe(true);
  });

  it('a refusal stays in the dialog', async () => {
    const refusal = { error: { code: 'table.zone_has_tables', message: 'That zone still has tables.' } };
    const d = await dialog(zoneRow(), { '/api/table/zones/delete': [409, refusal] });
    await click(d.submit());
    expect(d.inDoc('zones-delete-error')?.textContent).toContain('That zone still has tables.');
    expect(d.closed()).toBe(false);
  });
});

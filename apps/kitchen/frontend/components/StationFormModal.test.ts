// A station's dialog (WORKBOOK «Pantallas · Estaciones»; KITCHEN-F01, F02): Name («e.g. Grill»), Colour,
// Destination (screen and paper, screen only, paper only), Printer function (Kitchen, Bar), Printer
// (optional) and Active; «Create station» or, editing, «Save» with only what changed. A refusal (a name
// taken) shows in the dialog.
import { describe, expect, it, vi } from 'vitest';

import { station } from '../__tests__/kitchen';
import { click, ionChecked, ionValue, mountKitchen, settle } from '../__tests__/mount-kitchen';
import type { StationOut } from '../operations';
import StationFormModal from './StationFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean; placeholder?: string };

async function form(current: StationOut | null, answers: Record<string, [number, unknown]> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountKitchen(StationFormModal, { props: { open: false, station: current }, answers, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`kitchen-station-form-${name}`) as Control;
  return { ...m, field, closed: () => m.wrapper.props('open') === false };
}

describe('StationFormModal', () => {
  it('a new station asks its name and how it prints, and comes back created', async () => {
    const created = station('st-9', { name: 'Bar' });
    const f = await form(null, { '/api/kitchen/stations': [201, created] });
    expect(f.inDoc('kitchen-station-form')?.getAttribute('aria-label')).toBe('Add station');
    expect(f.field('name').placeholder).toBe('e.g. Grill');
    expect(f.field('submit').disabled).toBe(true);
    await ionValue(f.field('name'), ' Bar ', 'ionInput');
    await ionValue(f.field('color'), '#1971C2');
    await ionValue(f.field('destination'), 'printer');
    await ionValue(f.field('printer_usage'), 'bar');
    await ionValue(f.field('printer_name'), 'Bar printer', 'ionInput');
    expect(f.field('submit').textContent?.trim()).toBe('Create station');
    await click(f.field('submit'));
    expect(f.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/kitchen/stations',
        query: {},
        body: { name: 'Bar', color: '#1971C2', destination: 'printer', printer_usage: 'bar', printer_name: 'Bar printer', is_active: true },
      },
    ]);
    expect(f.wrapper.emitted('saved')?.[0]?.[0]).toEqual(created);
    expect(f.closed()).toBe(true);
  });

  it('editing says which station and sends only what changed', async () => {
    const f = await form(station('st-1', { name: 'Grill' }), { '/api/kitchen/stations/update': [200, station('st-1')] });
    expect(f.inDoc('kitchen-station-form')?.getAttribute('aria-label')).toBe('Edit station · Grill');
    expect(f.field('submit').textContent?.trim()).toBe('Save');
    await ionChecked(f.field('is_active'), false);
    await click(f.field('submit'));
    expect(f.sent().map((call) => call.body)).toEqual([{ station_id: 'st-1', is_active: false }]);
  });

  it('keeps a colour that is not one of the palette', async () => {
    const f = await form(station('st-1', { color: '#123456' }));
    const options = [...f.field('color').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(options).toContain('Custom (#123456)');
  });

  it('a taken name shows in the dialog and nothing closes', async () => {
    const refusal = { error: { code: 'kitchen.station_name_taken', message: 'There is already a station with that name. Choose a different name.' } };
    const f = await form(null, { '/api/kitchen/stations': [409, refusal] });
    await ionValue(f.field('name'), 'Grill', 'ionInput');
    await click(f.field('submit'));
    expect(f.inDoc('kitchen-station-form-error')?.textContent).toContain('There is already a station with that name.');
    expect(f.closed()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const f = await form(null, {}, 'es');
    expect(f.field('name').placeholder).toBe('p. ej. Plancha');
    const destinations = [...f.field('destination').querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(destinations).toEqual(['Pantalla y papel', 'Solo pantalla', 'Solo papel']);
  });
});
